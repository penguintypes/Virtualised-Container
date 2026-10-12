#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "state.h"

#define PERMS (O_WRONLY | O_CREAT | O_TRUNC)

static int dir_if_missing(const char *path, mode_t mode){

    if(mkdir(path,mode) == 0 || errno == EEXIST){
        return 0;
    }

    return -1;
}

int state_write(const char *name, const char *image, const char *rootfs,
    bool detach, const char *memory_max, const char *pids_max,
    const char *cpu_quota, const char *cpu_period,
    const struct container_volume volumes[], size_t volume_count,
    char *const command[]){

    char container_dir[4096];
    char config_path[4096];
    char temp_path[4096];


    if (dir_if_missing("/var/lib/vcontainer", 0755) != 0 ||
        dir_if_missing("/var/lib/vcontainer/containers", 0755) != 0) {
            return -1;
    }


    if (snprintf(container_dir, sizeof(container_dir),
        "/var/lib/vcontainer/containers/%s", name) >=
        (int)sizeof(container_dir) ||
        snprintf(config_path, sizeof(config_path),
            "%s/config", container_dir) >= (int)sizeof(config_path) ||
        snprintf(temp_path, sizeof(temp_path),
            "%s.tmp", config_path) >= (int)sizeof(temp_path)) {

        errno = ENAMETOOLONG;
        return  -1;
    }

    if (dir_if_missing(container_dir, 0755) != 0){
        return -1;
    }

    int fd = open(temp_path, PERMS, 0644);
    if (fd < 0){
        return -1;
    }

    FILE *file = fdopen(fd, "w");
    if (file == NULL){
        close(fd);
        return -1;
    }

    fprintf(file, "name=%s\n", name);
    fprintf(file, "image=%s\n", image == NULL ? "" : image);
    fprintf(file, "rootfs=%s\n", rootfs);
    fprintf(file, "detach=%s\n", detach ? "true" : "false");
    fprintf(file, "memory_max=%s\n", memory_max);
    fprintf(file, "pids_max=%s\n", pids_max);
    fprintf(file, "cpu_max=%s %s\n", cpu_quota, cpu_period);

    for (size_t i = 0; i < volume_count; ++i){
        fprintf(file, "volume=%s:%s\n",
            volumes[i].source, volumes[i].target);
    }

    for (size_t i = 0; command[i] != NULL; i++){
        fprintf(file, "command_arg=%s\n", command[i]);
    }

    if(fflush(file) != 0 || fsync(fd) != 0 || fclose(file) != 0){
        unlink(temp_path);
        return -1;
    }

    if (rename(temp_path, config_path) != 0){
        unlink(temp_path);
        return -1;
    }

    return 0;
}
