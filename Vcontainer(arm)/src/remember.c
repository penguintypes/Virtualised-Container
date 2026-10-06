#define _GNU_SOURCE

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
//#include <unistd.h>
//
//
#include "remember.h"

static int is_safe_absolute_path(const char *path){

    if (path == NULL || path[0] != '/' || path[1] == '\0' ||
        path[strlen(path) - 1] == '/') {
            return 0;
    }

    const char *part = path + 1;

    while (*part != '\0') {
        const char *slash = strchr(part, '/');
        size_t length = slash == NULL ? strlen(part) :
            (size_t)(slash - part);

        if (length == 0 ||
            (length == 1 && part[0] == '.')||
            (length == 2 && part[0] == '.' && part[1] == '.'))
        {
            return 0;
        }

        if (slash == NULL){
            break;
        }

        part = slash + 1;
    }

    return 1;
}

static int mkdir_tree(const char *path)
{
    char copy[4096];
    struct stat status;

    if (snprintf(copy, sizeof(copy), "%s", path) >= (int)sizeof(copy)) {
        errno = ENAMETOOLONG;
        return -1;
    }

    for (char *cursor = copy + 1; *cursor != '\0'; ++cursor) {
        if (*cursor != '/')
            continue;

        *cursor = '\0';

        if (mkdir(copy, 0755) != 0 && errno != EEXIST)
            return -1;

        if (lstat(copy, &status) != 0 || !S_ISDIR(status.st_mode)) {
            errno = ENOTDIR;
            return -1;
        }

        *cursor = '/';
    }

    if (mkdir(copy, 0755) != 0 && errno != EEXIST)
        return -1;

    if (lstat(copy, &status) != 0 || !S_ISDIR(status.st_mode)) {
        errno = ENOTDIR;
        return -1;
    }

    return 0;
}

int remember_mount(const char *source, const char *target)
{
    struct stat source_status;

    if (!is_safe_absolute_path(source) ||
        !is_safe_absolute_path(target)) {
        errno = EINVAL;
        return -1;
    }

    if (stat(source, &source_status) != 0 ||
        !S_ISDIR(source_status.st_mode)) {
        return -1;
    }

    if (mkdir_tree(target) != 0)
        return -1;

    return mount(source, target, NULL, MS_BIND | MS_REC, NULL);
}
