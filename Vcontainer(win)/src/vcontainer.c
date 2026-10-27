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

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
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
#include "log.h"
#include "state.h"
#include "overlay.h"
#include "network.h"

#define STACK_SIZE (1024 * 1024)
#define MAX_SECCOMP_DENIES 32
#define MAX_VOLUMES 16
#define MAX_ENVIRONMENT 128

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
    int sync_write_fd;
    int startup_read_fd;
    int startup_write_fd;
    bool use_userns;
    bool detach;
    bool bridge_network;

    bool seccomp_enabled;
    const char *seccomp_denies[MAX_SECCOMP_DENIES];
    size_t seccomp_deny_count;

    struct container_volume volumes[MAX_VOLUMES];
    size_t volume_count;

    const char *environment[MAX_ENVIRONMENT];
    size_t environment_count;

    int log_fd;

    const char *container_name;
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
        "[--cpu-max QUOTA PERIOD] [--volume SOURCE:TARGET] "
        "[--network bridge --ip ADDRESS] [--env NAME=VALUE] "
        "[--detach] [--log] "
        "-- COMMAND [ARGS...]\n",
            program);
}

static bool valid_environment_assignment(const char *assignment)
{
    const char *equals = assignment == NULL ? NULL : strchr(assignment, '=');
    if (equals == NULL || equals == assignment || strlen(equals + 1) > 8192)
        return false;

    unsigned char first = (unsigned char)assignment[0];
    if (first != '_' && !isalpha(first))
        return false;

    for (const char *cursor = assignment + 1; cursor < equals; ++cursor) {
        unsigned char character = (unsigned char)*cursor;
        if (character != '_' && !isalnum(character))
            return false;
    }
    return true;
}

static int mkdir_if_missing(const char *path, mode_t mode)
{
    if (mkdir(path, mode) == 0 || errno == EEXIST)
        return 0;
    return -1;
}

static int set_up_rootfs(const char *rootfs, const char *container_name,
    const struct container_volume *volumes, size_t volume_count)
{
    char merged_rootfs[4096];
    char oldroot[4096];

    /* Do not propagate mounts back into the Lima host namespace. */
    if (mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) != 0) {
        die("make mounts private");
        return -1;
    }
    /*if (mount(rootfs, rootfs, NULL, MS_BIND | MS_REC, NULL) != 0) {
        die("bind mount rootfs");
        return -1;
    }*/
    if (overlay_mount_rootfs(rootfs, container_name,
                             merged_rootfs, sizeof(merged_rootfs)) != 0) {
        die("mount overlay rootfs");
        return -1;
    }

    if (snprintf(oldroot, sizeof(oldroot), "%s/.oldroot", merged_rootfs) >=
        (int)sizeof(oldroot)) {
        fprintf(stderr, "vcontainer: overlay rootfs path is too long\n");
        return -1;
    }
    if (mkdir_if_missing(oldroot, 0700) != 0) {
        die("create .oldroot");
        return -1;
    }
    if (chdir(merged_rootfs) != 0 ||
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
              MS_NOSUID | MS_NOEXEC, "mode=755") != 0) {
        die("mount /dev");
        return -1;
    }

    const char *devices[] = {
        "null", "zero", "full", "random", "urandom", "tty"
    };
    for (size_t i = 0; i < sizeof(devices) / sizeof(devices[0]); ++i) {
        char source[64];
        char target[64];
        if (snprintf(source, sizeof(source), "/.oldroot/dev/%s", devices[i]) >=
                (int)sizeof(source) ||
            snprintf(target, sizeof(target), "/dev/%s", devices[i]) >=
                (int)sizeof(target)) {
            errno = ENAMETOOLONG;
            return -1;
        }
        int device_fd = open(target, O_WRONLY | O_CREAT | O_CLOEXEC, 0666);
        if (device_fd < 0 || close(device_fd) != 0 ||
            chmod(target, 0666) != 0 ||
            mount(source, target, NULL, MS_BIND, NULL) != 0) {
            if (device_fd >= 0)
                close(device_fd);
            die("mount standard device");
            return -1;
        }
    }

    if (mkdir_if_missing("/dev/pts", 0755) != 0 ||
        mount("devpts", "/dev/pts", "devpts",
              MS_NOSUID | MS_NOEXEC,
              "newinstance,ptmxmode=0666,mode=0620,gid=0") != 0) {
        die("mount /dev/pts");
        return -1;
    }

    if (mkdir_if_missing("/dev/shm", 01777) != 0 ||
        mount("tmpfs", "/dev/shm", "tmpfs",
              MS_NOSUID | MS_NODEV,
              "mode=1777") != 0) {
        die("mount /dev/shm");
        return -1;
    }

    if (mkdir_if_missing("/dev/mqueue", 0755) != 0 ||
        mount("mqueue", "/dev/mqueue", "mqueue",
              MS_NOSUID | MS_NOEXEC | MS_NODEV, NULL) != 0) {
        die("mount /dev/mqueue");
        return -1;
    }

    const struct {
        const char *target;
        const char *linkpath;
    } descriptor_links[] = {
        { "/proc/self/fd", "/dev/fd" },
        { "/proc/self/fd/0", "/dev/stdin" },
        { "/proc/self/fd/1", "/dev/stdout" },
        { "/proc/self/fd/2", "/dev/stderr" },
        { "pts/ptmx", "/dev/ptmx" },
    };
    for (size_t i = 0;
         i < sizeof(descriptor_links) / sizeof(descriptor_links[0]); ++i) {
        if (symlink(descriptor_links[i].target,
                    descriptor_links[i].linkpath) != 0) {
            die("create standard device link");
            return -1;
        }
    }

    if (umount2("/.oldroot", MNT_DETACH) != 0 || rmdir("/.oldroot") != 0) {
        die("unmount old root");
        return -1;
    }

    return 0;
}

static _Noreturn void child_fail(struct config *config)
{
    int error = errno ? errno : EIO;
    ssize_t written = write(config->startup_write_fd, &error, sizeof(error));
    (void)written;
    _exit(127);
}

static int child_main(void *argument)
{
    struct config *config = argument;
    char ready;

    close(config->sync_write_fd);
    close(config->startup_read_fd);

    if (read(config->sync_fd, &ready, 1) != 1 || ready != '1') {
            child_fail(config);
    }
    close(config->sync_fd);

    /* Root the cgroup namespace after the parent attaches this process. */
    if (unshare(CLONE_NEWCGROUP) != 0) {
        die("create cgroup namespace");
        child_fail(config);
    }
    if (config->log_fd >= 0) {
        if (dup2(config->log_fd, STDOUT_FILENO) < 0 ||
            dup2(config->log_fd, STDERR_FILENO) < 0) {
            die("redirect container log");
            child_fail(config);
        }
        if (config->log_fd > STDERR_FILENO)
            close(config->log_fd);
    }
    if (sethostname(config->hostname, strlen(config->hostname)) != 0) {
        die("set hostname");
        child_fail(config);
    }
    if (set_up_rootfs(config->rootfs,
                      config->container_name,
                      config->volumes,
                      config->volume_count) != 0) {
        child_fail(config);
    }

    if (config->bridge_network && network_configure_resolver() != 0) {
        die("configure container resolver");
        child_fail(config);
    }

    if (seccomp_config(config->seccomp_enabled,
        config->seccomp_denies,
        config->seccomp_deny_count) != 0){
        die("load seccomp filter");
        child_fail(config);
    }

    if (config->detach && setsid() == -1) {
        die("detach session");
        child_fail(config);
    }

    for (size_t i = 0; i < config->environment_count; ++i) {
        char *assignment = strdup(config->environment[i]);
        if (assignment == NULL)
            child_fail(config);

        char *equals = strchr(assignment, '=');
        if (equals == NULL) {
            free(assignment);
            errno = EINVAL;
            child_fail(config);
        }
        *equals = '\0';
        if (setenv(assignment, equals + 1, 1) != 0) {
            free(assignment);
            child_fail(config);
        }
        free(assignment);
    }

    execvp(config->command[0], config->command);
    die("exec command");
    child_fail(config);
}

static int write_text_file(const char *path, const char *text)
{
    FILE *file = fopen(path, "w");
    if (file == NULL)
        return -1;
    int result = fputs(text, file) == EOF || fclose(file) != 0 ? -1 : 0;
    return result;
}

static int subordinate_start(const char *path, const char *user,
                             unsigned long *start)
{
    FILE *file = fopen(path, "r");
    char line[256];

    if (file == NULL)
        return -1;

    while (fgets(line, sizeof(line), file) != NULL) {
        char owner[128];
        unsigned long first;
        unsigned long count;

        if (sscanf(line, "%127[^:]:%lu:%lu", owner, &first, &count) == 3 &&
            strcmp(owner, user) == 0 && count >= 65535) {
            *start = first;
            fclose(file);
            return 0;
        }
    }

    fclose(file);
    errno = ENOENT;
    return -1;
}

static int map_user_and_group(pid_t pid)
{
    char path[128];
    char map[256];
    uid_t uid = getuid();
    gid_t gid = getgid();
    unsigned long subuid = 0;
    unsigned long subgid = 0;
    bool use_subids = uid == 0;

    if (use_subids) {
        const char *owner = getenv("SUDO_USER");
        if (owner == NULL || owner[0] == '\0' ||
            subordinate_start("/etc/subuid", owner, &subuid) != 0 ||
            subordinate_start("/etc/subgid", owner, &subgid) != 0) {
            die("find subordinate UID/GID ranges");
            return -1;
        }
    }

    if (!use_subids) {
        snprintf(path, sizeof(path), "/proc/%ld/setgroups", (long)pid);
        if (write_text_file(path, "deny\n") != 0 && errno != ENOENT) {
            die("disable supplementary groups");
            return -1;
        }
    }
    snprintf(path, sizeof(path), "/proc/%ld/uid_map", (long)pid);
    if (use_subids)
        snprintf(map, sizeof(map), "0 0 1\n1 %lu 65535\n", subuid);
    else
        snprintf(map, sizeof(map), "0 %lu 1\n", (unsigned long)uid);
    if (write_text_file(path, map) != 0) {
        die("write uid_map");
        return -1;
    }
    snprintf(path, sizeof(path), "/proc/%ld/gid_map", (long)pid);
    if (use_subids)
        snprintf(map, sizeof(map), "0 0 1\n1 %lu 65535\n", subgid);
    else
        snprintf(map, sizeof(map), "0 %lu 1\n", (unsigned long)gid);
    if (write_text_file(path, map) != 0) {
        die("write gid_map");
        return -1;
    }
    return 0;
}

static int run_container(int argc, char **argv, char **saved_argv, const char *start_name)
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
    bool log_output = false;
    bool bridge_network = false;
    const char *network_ip = NULL;
    struct container_volume volumes[MAX_VOLUMES] = { 0 };
    size_t volume_count = 0;
    const char *environment[MAX_ENVIRONMENT] = { 0 };
    size_t environment_count = 0;
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
        else if (strcmp(argv[index], "--network") == 0 && index + 1 < argc) {
            if (strcmp(argv[index + 1], "bridge") != 0) {
                fprintf(stderr, "vcontainer: only --network bridge is supported\n");
                return EXIT_FAILURE;
            }

            bridge_network = true;
            index += 2;
        }
        else if (strcmp(argv[index], "--ip") == 0 && index + 1 < argc) {
            network_ip = argv[index + 1];
            index += 2;
        }
        else if (strcmp(argv[index], "--detach") == 0) {
            detach = true;
            ++index;
        }
        else if (strcmp(argv[index], "--log") == 0) {
            log_output = true;
            ++index;
        }
        else if ((strcmp(argv[index], "--env") == 0 ||
                  strcmp(argv[index], "-e") == 0) && index + 1 < argc) {
            if (environment_count == MAX_ENVIRONMENT ||
                !valid_environment_assignment(argv[index + 1])) {
                fprintf(stderr, "vcontainer: --env requires a valid NAME=VALUE\n");
                return EXIT_FAILURE;
            }
            environment[environment_count++] = argv[index + 1];
            index += 2;
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

            volumes[volume_count++] = (struct container_volume) {
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

        if (snprintf(image_rootfs, sizeof(image_rootfs), "/var/lib/vcontainer/images/%s/rootfs", image) >=
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

    if (cgroup_id == NULL || strcmp(cgroup_id, ".") == 0 ||
        strcmp(cgroup_id, "..") == 0 || cgroup_id[0] == '\0' ||
        strspn(cgroup_id,
               "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "abcdefghijklmnopqrstuvwxyz"
               "0123456789_.-") != strlen(cgroup_id)) {
        fprintf(stderr, "vcontainer: --name must use letters, numbers, _, -, or .\n");
        return EXIT_FAILURE;
    }

    if (start_name != NULL && strcmp(cgroup_id, start_name) != 0) {
        fprintf(stderr, "vcontainer: saved container name does not match\n");
        return EXIT_FAILURE;
    }

    if (bridge_network && network_ip == NULL) {
        fprintf(stderr,
                "vcontainer: --network bridge requires --ip ADDRESS\n");
        return EXIT_FAILURE;
    }

    if (!bridge_network && network_ip != NULL) {
        fprintf(stderr,
                "vcontainer: --ip requires --network bridge\n");
        return EXIT_FAILURE;
    }

    int log_fd = -1;

    if (detach || log_output) {
        log_fd = log_open(cgroup_id);
        if (log_fd < 0) {
            die("open container log");
            return EXIT_FAILURE;
        }
    }

    if (cgroup_call("create", cgroup_id, memory_max, pids_max,
        cpu_quota, cpu_period, 0) != 0) {
            fprintf(stderr, "vcontainer: could not create cgroup\n");
            return EXIT_FAILURE;
    }

    if (state_write(cgroup_id, image, rootfs, detach,
                    memory_max, pids_max, cpu_quota, cpu_period,
                    volumes, volume_count, &argv[index + 1]) != 0) {
        die("write container state");

        if (log_fd >= 0)
            close(log_fd);

        cgroup_call("destroy", cgroup_id, memory_max, pids_max,
                    cpu_quota, cpu_period, 0);
        return EXIT_FAILURE;
    }

    int startup_pipe[2];
    if (pipe2(startup_pipe, O_CLOEXEC) != 0) {
        die("create startup pipe");
        cgroup_call("destroy", cgroup_id, memory_max, pids_max,
                    cpu_quota, cpu_period, 0);
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
        .sync_write_fd = sync_pipe[1],
        .startup_read_fd = startup_pipe[0],
        .startup_write_fd = startup_pipe[1],
        .detach = detach,
        .bridge_network = bridge_network,
        .use_userns = use_userns,
        .seccomp_enabled = seccomp_enabled,
        .seccomp_deny_count = seccomp_deny_count,
        .seccomp_denies = { 0 },
        .volume_count = volume_count,
        .environment_count = environment_count,
        .log_fd = log_fd,
        .container_name = cgroup_id,
    };

    for (size_t i = 0; i < seccomp_deny_count; ++i){
        config.seccomp_denies[i] = seccomp_denies[i];
    }
    for (size_t i = 0; i < volume_count; ++i) {
        config.volumes[i] = volumes[i];
    }
    for (size_t i = 0; i < environment_count; ++i) {
        config.environment[i] = environment[i];
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
    close(startup_pipe[1]);

    bool child_ready = true;

    if(use_userns && map_user_and_group(child) != 0){
        child_ready = false;
    }

    if(child_ready && cgroup_call("attach", cgroup_id, memory_max,
            pids_max, cpu_quota, cpu_period, child) != 0) {
                fprintf(stderr, "vcontainer: could not attach child to cgroup\n");
                child_ready = false;
    }

    if (child_ready && bridge_network &&
        network_setup_bridge(cgroup_id, child, network_ip) != 0) {
        die("set up bridge network");
        child_ready = false;
    }

    if (child_ready && write(sync_pipe[1], "1", 1) != 1) {
        die("release child");
        child_ready = false;
    }

    close(sync_pipe[1]);

    if (child_ready) {
        struct pollfd startup = { .fd = startup_pipe[0], .events = POLLIN };
        int ready;
        do {
            ready = poll(&startup, 1, 30000);
        } while (ready < 0 && errno == EINTR);
        int exec_error = 0;
        ssize_t count = ready > 0 ? read(startup_pipe[0], &exec_error,
                                        sizeof(exec_error)) : -1;
        if (count != 0) {
            fprintf(stderr, "vcontainer: startup failed: %s\n",
                    count > 0 ? strerror(exec_error) : "startup timeout or pipe error");
            kill(child, SIGKILL);
            child_ready = false;
        }
    }
    close(startup_pipe[0]);

    if (child_ready) {
        char pid_path[4096];
        char pid_text[32];

        int length = snprintf(pid_path, sizeof(pid_path),   
            "/var/lib/vcontainer/containers/%s/init.pid", cgroup_id);

        snprintf(pid_text, sizeof(pid_text), "%ld\n", (long)child);


        if(length < 0 || length >= (int)sizeof(pid_path) ||
            write_text_file(pid_path, pid_text) != 0) {
                fprintf(stderr, "vcontainer: could not save container PID\n");
                kill(child, SIGKILL);
                child_ready = false;
            }
    }

    if (child_ready &&
        state_save_launch(cgroup_id, argc - 1, saved_argv + 1) != 0) {
        die("save launch arguments");
        kill(child, SIGKILL);
        child_ready = false;
    }

    if (!child_ready) {
        int failed_status;
        waitpid(child, &failed_status, 0);
        cgroup_call("destroy", cgroup_id, memory_max, pids_max,
                    cpu_quota, cpu_period, 0);
        if (log_fd >= 0)
            close(log_fd);
        munmap(mapping, mapping_size);
        return EXIT_FAILURE;
    }

    if (detach) {
        printf("container %s started: host PID %ld\n",
            cgroup_id, (long)child);
        munmap(mapping, mapping_size);
        return EXIT_SUCCESS;
    }

    int result = EXIT_FAILURE;
    int status;

    if(waitpid(child, &status, 0) == child) {
        if (WIFEXITED(status))
            result = WEXITSTATUS(status);
        else if (WIFSIGNALED(status))
            result = 128 + WTERMSIG(status);
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


int main(int argc, char **argv) {
    char **loaded_argv = NULL;
    int loaded_argc = 0;
    const char *start_name = NULL;

    if (argc >= 2 && strcmp(argv[1], "start") == 0) {
        if (argc != 3) {
            fprintf(stderr, "Usage: vcontainer start NAME\n");
            return EXIT_FAILURE;
        }

        start_name = argv[2];
        if (state_load_launch(start_name, &loaded_argc, &loaded_argv) != 0) {
            die("load saved launch arguments");
            return EXIT_FAILURE;
        }

        char group[4096];
        int length = snprintf(group, sizeof(group),
            "/sys/fs/cgroup/vcontainer/%s", start_name);
        if (length < 0 || length >= (int)sizeof(group)) {
            fprintf(stderr, "vcontainer: container path too long\n");
            state_free_launch(loaded_argc, loaded_argv);
            return EXIT_FAILURE;
        }

        if (access(group, F_OK) == 0) {
            fprintf(stderr,
                "vcontainer: container has an existing cgroup; "
                "run stop %s before starting it\n", start_name);
            state_free_launch(loaded_argc, loaded_argv);
            return EXIT_FAILURE;
        }
        if (errno != ENOENT) {
            die("check container cgroup");
            state_free_launch(loaded_argc, loaded_argv);
            return EXIT_FAILURE;
        }

        argc = loaded_argc;
        argv = loaded_argv;
    }

    char **saved_argv = calloc((size_t)argc + 1, sizeof(*saved_argv));
    if (saved_argv == NULL){
        die("allocate launch arguments");
        state_free_launch(loaded_argc, loaded_argv);
        return EXIT_FAILURE;
    }

    for (int i = 0; i < argc; ++i) {
        saved_argv[i] = strdup(argv[i]);

        if(saved_argv[i] == NULL){
            die("copy launch argument");
            state_free_launch(i, saved_argv);
            state_free_launch(loaded_argc, loaded_argv);
            return EXIT_FAILURE;
        }
    }

    int result = run_container(argc, argv, saved_argv, start_name);

    state_free_launch(argc, saved_argv);
    state_free_launch(loaded_argc, loaded_argv);
    return result;
}
