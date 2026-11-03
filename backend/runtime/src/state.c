#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdlib.h>
#include <stdbool.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "state.h"

#define PERMS (O_WRONLY | O_CREAT | O_TRUNC)
#define MAX_LAUNCH_BYTES (1024 * 1024)
#define MAX_LAUNCH_ARGS 256

static int dir_if_missing(const char *path, mode_t mode){

    if(mkdir(path,mode) == 0 || errno == EEXIST){
        return 0;
    }

    return -1;
}

static int launch_path(const char *name, char *path, size_t size){

     if (name == NULL || name[0] == '\0' ||
        strcmp(name, ".") == 0 || strcmp(name, "..") == 0 ||
        strspn(name,
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "abcdefghijklmnopqrstuvwxyz"
            "0123456789_.-") != strlen(name)) {
        errno = EINVAL;
        return -1;
    }

    int length = snprintf(path, size,
        "/var/lib/vcontainer/containers/%s/launch.argv", name);

    if (length < 0 || (size_t)length >= size) {
        errno = ENAMETOOLONG;
        return -1;
    }
    
    return 0;
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


int state_save_launch(const char *name, int argc, char *const argv[]) {

    char path[4096];
    char temp[4120];
    size_t total = 0;

    if (argc < 1 || argc > MAX_LAUNCH_ARGS || 
        argv == NULL || argv[0] == NULL ||
        strcmp(argv[0], "run") != 0) {
        
            errno = EINVAL;
            return -1;
    }

    for (int i = 0; i < argc; ++i){
        if(argv[i] == NULL) {
            errno = EINVAL;
            return -1;
        }

        size_t length = strlen(argv[i]) + 1;

        if (length > MAX_LAUNCH_BYTES - total) {
            errno = E2BIG;
            return -1;
        }

        total += length;
    }

    if (launch_path(name, path, sizeof(path)) != 0)
        return -1;

    snprintf(temp, sizeof(temp), "%s.XXXXXX", path);

    int fd = mkstemp(temp);
    if (fd < 0) {
        return -1;
    }

    FILE *file = fdopen(fd, "wb");
    if (file == NULL) {
        int saved_errno = errno;
        close(fd);
        unlink(temp);
        errno = saved_errno;
        return -1;
    }

    bool failed  = false;

    for (int i = 0; i < argc; ++i) {
        size_t length = strlen(argv[i]) + 1;

        if(fwrite(argv[i], 1, length, file) != length) {
            failed = true;
            break;
        }
    }
    
    
    if (!failed && fflush(file) != 0)
        failed = true;

    if (!failed && fsync(fd) != 0)
        failed = true;

    if (fclose(file) != 0)
        failed = true;

    if (failed) {
        unlink(temp);
        errno = EIO;
        return -1;
    }

    if (rename(temp, path) != 0) {
        int saved_errno = errno;
        unlink(temp);
        errno = saved_errno;
        return -1;
    }

    return 0;
}

void state_free_launch(int argc, char **argv)
{
    if (argv == NULL)
        return;

    for (int i = 0; i < argc; ++i)
        free(argv[i]);

    free(argv);
}

int state_load_launch(const char *name, int *argc, char ***argv ){
    
    char path[4096];


     if (argc == NULL || argv == NULL) {
        errno = EINVAL;
        return -1;
    }

    *argc = 0;
    *argv = NULL;

    if (launch_path(name, path, sizeof(path)) != 0)
        return -1;

    FILE *file = fopen(path, "rb");
    if (file == NULL)
        return -1;

    char *buffer = malloc(MAX_LAUNCH_BYTES + 1);
    if (buffer == NULL){
        fclose(file);
        return -1;
    }

    size_t size = fread(buffer, 1, MAX_LAUNCH_BYTES + 1, file);
    bool failed = ferror(file);

    if (fclose(file) != 0){
        failed = true;
    }

    if (failed || size == 0 || size > MAX_LAUNCH_BYTES ||
        buffer[size -1] != '\0') {
            free(buffer);
            errno = failed ? EIO : EINVAL;
            return -1;
    }

    char **loaded = calloc(MAX_LAUNCH_ARGS + 2, sizeof(*loaded));
    if (loaded == NULL) {
        free(buffer);
        return -1;
    }

    int count = 0;
    loaded[count] = strdup("vcontainer");

    if (loaded[count] == NULL){
        goto fail;
    }

    ++count;

    for (size_t offset = 0; offset < size;) {
        if (count >= MAX_LAUNCH_ARGS + 1) {
            errno = E2BIG;
            goto fail;
        }

        loaded[count] = strdup(buffer + offset);
        if (loaded[count] == NULL){
            goto fail;
        }

        ++count;
        offset += strlen(buffer + offset) + 1;
    }

    if (count < 2 || strcmp(loaded[1], "run") != 0) {
        errno = EINVAL;
        goto fail;
    }

    free(buffer);
    *argc = count;
    *argv = loaded;
    return 0;

fail:
    {
        int saved_errno = errno;
        free(buffer);
        state_free_launch(count, loaded);
        errno = saved_errno;
        return -1;
    }

}
