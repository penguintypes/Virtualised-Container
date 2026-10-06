/*
* Containerization is just an idea of isolating the process with no knowledge of other processes.
*
* It requires prior knowledge in linux, namespaces and cgroup. So the idea of containerization is
*
* giving a space completely separated from its other siblings, isolated in thier basement performing its own job, spawning
*
* their own children and completely unaware of other siblings, but the parent is completely aware of their isolated offspring.
*
* A parent can isolate many of their children but those isolated children could not interact with their own
*
* isolated siblings . Isn't it dark right?hmm maybe,  but who cares we are the masters, we tell parent to spawn a child, isolate them from the rest and give them a specific
*
* task to perfrom.
*
* But hey! it's just an example for our clear understanding. Heheh who knows? maybe I am one of those masters and it could be your turn too
*
* only you have to do is contribute our work and just go out have fun live the life and come back again, hehehe.
*
* Also do make sure to endorse and share our project !
 */

#define _GNU_SOURCE

#include <stddef.h>

#include <errno.h>
#include <sched.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/mman.h>
#include <unistd.h>

#include "cgroup.h"
#include "namespace.h"
#include "seccomp.h"
#include "remember.h"

#define STACK_SIZE (1024 * 1024)
#define MAX_SECCOMP_DENIES 32
#define MAX_VOLUMES 16

struct volume_mount {
    const char *source;
    const char *target;
};

/* rootfs - Image which will bootup the isloated offspring
 * hostname - Name of the child
 * command -  run_container [COMMAND] like run, --memory-max, etc
 * sync_fd - it is child process's read end of  a sychronisation pipe sync_pipe
 * what is file descriptor?
 * ->
 *        |  PROCESS 1                          |
 *        | ----------------------------------  |
 *        |  FD TABLE                           |
 *        | ----------------------------------- |
 *        |  0  stdin                           | -> creates metadata for each process in seperate table
 *        |  1  stdout                          |
 *        |  2  stderr                          |
 *        |  3  file.txt                        |
 *        |  4  file1.txt                       |
 *
 * use_userns - a switch enabling the creation of isolated child , when true the child can appear as UID(userid) 0 (root)
 */

struct config {
    const char *rootfs;
    const char *hostname;
    char **command;
    int sync_fd;
    bool use_userns;
    bool detach;

    bool seccomp_enabled;
    const char *seccomp_denies[MAX_SECCOMP_DENIES];
    size_t seccomp_deny_count;

    struct volume_mount volumes[MAX_VOLUMES];
    size_t volume_count;
};

static void die(const char *message)
{
    fprintf(stderr, "vcontainer: %s: %s\n", message, strerror(errno));
}

static void usage(const char *program)
{
    fprintf(stderr,
        "Usage: %s run (--rootfs DIRECTORY | --image NAME) --name NAME [--hostname NAME] "
        "[--memory-max VALUE] [--pids-max COUNT] "
        "[--cpu-max QUOTA PERIOD] [--volume SOURCE:TARGET] -- COMMAND [ARGS...]\n",
            program);
}

static int mkdir_if_missing(const char *path, mode_t mode)
{
    if (mkdir(path, mode) == 0 || errno == EEXIST)
        return 0;
    return -1;
}

static int set_up_rootfs(const char *rootfs,
    const struct volume_mount *volumes, size_t volume_count)
{
    char oldroot[4096];
    if (snprintf(oldroot, sizeof(oldroot), "%s/.oldroot", rootfs) >=
        (int)sizeof(oldroot)) {
        fprintf(stderr, "vcontainer: rootfs path is too long\n");
        return -1;
    }

    /* Do not propagate mounts back into the Lima host namespace. */
    if (mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) != 0) {
        die("make mounts private");
        return -1;
    }
    if (mount(rootfs, rootfs, NULL, MS_BIND | MS_REC, NULL) != 0) {
        die("bind mount rootfs");
        return -1;
    }
    if (mkdir_if_missing(oldroot, 0700) != 0) {
        die("create .oldroot");
        return -1;
    }
    if (chdir(rootfs) != 0 ||
        syscall(SYS_pivot_root, ".", ".oldroot") != 0 || chdir("/") != 0) {
        die("pivot_root");
        return -1;
    }

    for (size_t i = 0; i < volume_count; ++i) {
        char old_volume_source[4096];

        if (snprintf(old_volume_source, sizeof(old_volume_source),
                     "/.oldroot%s", volumes[i].source) >=
            (int)sizeof(old_volume_source)) {
            fprintf(stderr, "vcontainer: volume source path is too long\n");
            return -1;
        }

        if (remember_mount(old_volume_source, volumes[i].target) != 0) {
            die("mount persistent volume");
            return -1;
        }
    }

    if (mkdir_if_missing("/proc", 0555) != 0 ||
        mkdir_if_missing("/sys", 0555) != 0 ||
        mkdir_if_missing("/dev", 0755) != 0) {
        die("create virtual filesystem mount points");
        return -1;
    }
    if (mount("proc", "/proc", "proc",
              MS_NOSUID | MS_NOEXEC | MS_NODEV, NULL) != 0) {
        die("mount /proc");
        return -1;
    }

    if (mount("tmpfs", "/dev", "tmpfs",
              MS_NOSUID | MS_NODEV, "mode=755") != 0) {
        die("mount /dev");
        return -1;
    }

    if (umount2("/.oldroot", MNT_DETACH) != 0 || rmdir("/.oldroot") != 0) {
        die("unmount old root");
        return -1;
    }

    return 0;
}

static int child_main(void *argument)
{
    struct config *config = argument;
    char ready;

    if (read(config->sync_fd, &ready, 1) != 1 || ready != '1') {
            _exit(127);
    }
    close(config->sync_fd);
    if (sethostname(config->hostname, strlen(config->hostname)) != 0) {
        die("set hostname");
        _exit(127);
    }
    if (set_up_rootfs(config->rootfs,
                      config->volumes,
                      config->volume_count) != 0) {
        _exit(127);
    }

    if (seccomp_config(config->seccomp_enabled,
        config->seccomp_denies,
        config->seccomp_deny_count) != 0){
        die("load seccomp filter");
        _exit(127);
    }

    if (config->detach && setsid() == -1) {
        die("detach session");
        _exit(127);
    }

    execvp(config->command[0], config->command);
    die("exec command");
    _exit(127);
}

static int write_text_file(const char *path, const char *text)
{
    FILE *file = fopen(path, "w");
    if (file == NULL)
        return -1;
    int result = fputs(text, file) == EOF || fclose(file) != 0 ? -1 : 0;
    return result;
}

static int map_user_and_group(pid_t pid)
{
    char path[128];
    char map[128];
    uid_t uid = getuid();
    gid_t gid = getgid();

    snprintf(path, sizeof(path), "/proc/%ld/setgroups", (long)pid);
    if (write_text_file(path, "deny\n") != 0 && errno != ENOENT) {
        die("disable supplementary groups");
        return -1;
    }
    snprintf(path, sizeof(path), "/proc/%ld/uid_map", (long)pid);
    snprintf(map, sizeof(map), "0 %lu 1\n", (unsigned long)uid);
    if (write_text_file(path, map) != 0) {
        die("write uid_map");
        return -1;
    }
    snprintf(path, sizeof(path), "/proc/%ld/gid_map", (long)pid);
    snprintf(map, sizeof(map), "0 %lu 1\n", (unsigned long)gid);
    if (write_text_file(path, map) != 0) {
        die("write gid_map");
        return -1;
    }
    return 0;
}

int main(int argc, char **argv)
{
    const char *rootfs = NULL;
    const char *image = NULL;
    char image_rootfs[4096];
    const char *hostname = "vcontainer";
    bool use_userns = true;
    bool seccomp_enabled = false;
    const char *seccomp_denies[MAX_SECCOMP_DENIES];
    size_t seccomp_deny_count = 0;
    bool detach = false;
    struct volume_mount volumes[MAX_VOLUMES] = { 0 };
    size_t volume_count = 0;
    int index = 1;

    const char *cgroup_id = NULL;
    const char *memory_max = "250M";
    const char *pids_max = "64";
    const char *cpu_quota = "50000";
    const char *cpu_period = "100000";

    if (argc < 2 || strcmp(argv[index++], "run") != 0) {
        usage(argv[0]);
        return EXIT_FAILURE;
    }
    while (index < argc && strcmp(argv[index], "--") != 0) {
        if (strcmp(argv[index], "--rootfs") == 0 && ++index < argc) {
            rootfs = argv[index++];
        }
        else if (strcmp(argv[index], "--hostname") == 0 && ++index < argc){
            hostname = argv[index++];
        }
        else if (strcmp(argv[index], "--name") == 0) {
            if (index + 1 >= argc) {
                usage(argv[0]);
                return EXIT_FAILURE;
            }

            cgroup_id = argv[index + 1];
            index += 2;
        }
        else if (strcmp(argv[index], "--detach") == 0) {
            detach = true;
            ++index;
        }
        else if (strcmp(argv[index], "--userns") == 0) {
            use_userns = true;
            ++index;
        }
        else if (strcmp(argv[index], "--seccomp") == 0) {
            seccomp_enabled = true;
            ++index;
        }
        else if (strcmp(argv[index], "--deny") == 0) {
            if (!seccomp_enabled || index + 1 >= argc ||
                seccomp_deny_count == MAX_SECCOMP_DENIES) {
                usage(argv[0]);
                return EXIT_FAILURE;
            }

            seccomp_denies[seccomp_deny_count++] = argv[index + 1];
            index += 2;
        }
        else if (strcmp(argv[index], "--volume") == 0 && index + 1 < argc) {
            char *separator = strchr(argv[index + 1], ':');

            if (separator == NULL || separator == argv[index + 1] ||
                separator[1] != '/') {
                fprintf(stderr, "vcontainer: --volume requires SOURCE:TARGET\n");
                return EXIT_FAILURE;
            }

            *separator = '\0';
            if (volume_count == MAX_VOLUMES) {
                fprintf(stderr, "vcontainer: at most %d volumes are supported\n",
                    MAX_VOLUMES);
                return EXIT_FAILURE;
            }

            for (size_t i = 0; i < volume_count; ++i) {
                if (strcmp(volumes[i].target, separator + 1) == 0) {
                    fprintf(stderr, "vcontainer: duplicate volume target: %s\n",
                        separator + 1);
                    return EXIT_FAILURE;
                }
            }

            volumes[volume_count++] = (struct volume_mount) {
                .source = argv[index + 1],
                .target = separator + 1,
            };
            index += 2;
        }
        else if (strcmp(argv[index], "--image") == 0) {
            if (index + 1 >= argc) {
                usage(argv[0]);
                return EXIT_FAILURE;
            }
            image = argv[index + 1];
            index += 2;
        }
        else if (strcmp(argv[index], "--memory-max") == 0){
            if(index + 1 >= argc) {
                usage(argv[0]);
                return EXIT_FAILURE;
            }
            memory_max = argv[index + 1];
            index += 2;
        }
        else if (strcmp(argv[index], "--pids-max") == 0){
            if(index + 1 >= argc) {
                usage(argv[0]);
                return EXIT_FAILURE;
            }
            pids_max = argv[index + 1];
            index += 2;
        }
        else if (strcmp(argv[index], "--cpu-max") == 0){
            if(index + 2 >= argc) {
                usage(argv[0]);
                return EXIT_FAILURE;
            }
            cpu_quota= argv[index + 1];
            cpu_period = argv[index + 2];
            index += 3;
        }

        else {
            usage(argv[0]);
            return EXIT_FAILURE;
        }
    }
    if (image != NULL) {
        if (rootfs != NULL) {
            fprintf(stderr, "vcontainer: use --image or --rootfs, not both\n");
            return EXIT_FAILURE;
        }

        if (snprintf(image_rootfs, sizeof(image_rootfs), "/tmp/vcontainer-images/%s/rootfs", image) >=
            (int)sizeof(image_rootfs)) {
                fprintf(stderr,"vcontainer: image path is too long\n");
                return EXIT_FAILURE;
        }

        rootfs = image_rootfs;

    }
    if (rootfs == NULL || index + 1 >= argc || strcmp(argv[index], "--") != 0) {
        usage(argv[0]);
        return EXIT_FAILURE;
    }
    if (access(rootfs, R_OK | X_OK) != 0) {
        die("access rootfs");
        return EXIT_FAILURE;
    }

    if (cgroup_id == NULL || cgroup_id[0] == '\0' ||
        strspn(cgroup_id,
               "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "abcdefghijklmnopqrstuvwxyz"
               "0123456789_.-") != strlen(cgroup_id)) {
        fprintf(stderr, "vcontainer: --name must use letters, numbers, _, -, or .\n");
        return EXIT_FAILURE;
    }

    if (cgroup_call("create", cgroup_id, memory_max, pids_max,
        cpu_quota, cpu_period, 0) != 0) {
            fprintf(stderr, "vcontainer: could not create cgroup\n");
            return EXIT_FAILURE;
    }

    int sync_pipe[2] = {-1, -1};
    if (pipe(sync_pipe) != 0) {
        die("create sync pipe");
        return EXIT_FAILURE;
    }

    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0) {
        die("get page size");
        return EXIT_FAILURE;
    }

    size_t mapping_size = STACK_SIZE + page_size;

    //char *stack = malloc(STACK_SIZE);
    void *mapping = mmap(NULL, mapping_size, PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANONYMOUS | MAP_STACK,
        -1, 0);

    if (mapping == MAP_FAILED) {
        die("mmap stack");
        return EXIT_FAILURE;
    }

    if (mprotect(mapping, page_size, PROT_NONE) == -1) {
        die("mprotect stack guard");
        munmap(mapping, mapping_size);
        return EXIT_FAILURE;
    }
    /*if (stack == NULL) {
        die("allocate child stack");
        return EXIT_FAILURE;
    }*/

    struct config config = {
        .rootfs = rootfs,
        .hostname = hostname,
        .command = &argv[index + 1],
        .sync_fd = sync_pipe[0],
        .detach = detach,
        .use_userns = use_userns,
        .seccomp_enabled = seccomp_enabled,
        .seccomp_deny_count = seccomp_deny_count,
        .seccomp_denies = { 0 },
        .volume_count = volume_count,
    };

    for (size_t i = 0; i < seccomp_deny_count; ++i){
        config.seccomp_denies[i] = seccomp_denies[i];
    }
    for (size_t i = 0; i < volume_count; ++i) {
        config.volumes[i] = volumes[i];
    }

    int flags = namespace_clone_flags(use_userns, true) | SIGCHLD;
    void *child_stack = (char *)mapping + mapping_size;
    pid_t child = clone(child_main, child_stack, flags, &config);
    if (child < 0) {
        die("clone namespaces");
        munmap(mapping, mapping_size);
        return EXIT_FAILURE;
    }

    close(sync_pipe[0]);

    bool child_ready = true;

    if(use_userns && map_user_and_group(child) != 0){
        child_ready = false;
    }

    if(child_ready && cgroup_call("attach", cgroup_id, memory_max,
            pids_max, cpu_quota, cpu_period, child) != 0) {
                fprintf(stderr, "vcontainer: could not attach child to cgroup\n");
                child_ready = false;
    }

    if (child_ready && write(sync_pipe[1], "1", 1) != 1) {
        die("release child");
        child_ready = false;
    }

    close(sync_pipe[1]);

    if (detach) {
        printf("container %s started: host PID %ld\n",
            cgroup_id, (long)child);
        munmap(mapping, mapping_size);
        return EXIT_SUCCESS;
    }

    int result = EXIT_FAILURE;
    int status;

    if(waitpid(child, &status, 0) == child) {
        result = WIFEXITED(status) ? WEXITSTATUS(status) : EXIT_FAILURE;
    } else {
        die("wait for container");
    }

    cgroup_call("stats", cgroup_id, memory_max, pids_max,
        cpu_quota, cpu_period, 0);

    cgroup_call("destroy", cgroup_id, memory_max, pids_max,
        cpu_quota, cpu_period, 0);

    /*bool child_ready = !use_userns ||
                       (map_user_and_group(child) == 0 &&
                        write(sync_pipe[1], "1", 1) == 1);
    if (child_ready) {
        int status;
        if (waitpid(child, &status, 0) == child) {
            result = WIFEXITED(status) ? WEXITSTATUS(status) : EXIT_FAILURE;
        } else {
            die("wait for container");
        }
    }
    if (use_userns)
    close(sync_pipe[1]);*/
    //free(stack);
    munmap(mapping, mapping_size);
    return result;
}
