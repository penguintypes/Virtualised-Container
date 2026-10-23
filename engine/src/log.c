#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
//#include <sys/_types/_mode_t.h>
#include <sys/stat.h>

#include "log.h"

#define PERMS (O_WRONLY | O_CREAT | O_APPEND)

static int dir_if_missing(const char *path, mode_t mode){
    if(mkdir(path,mode) == 0 || errno == EEXIST){
        return 0;
    }

    return -1;
}


int log_open(const char *container_name){

    char container_dir[4096];
    char log_path[4096];

    if (container_name == NULL || container_name[0] == '\0' ||
        strspn(container_name,
                       "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                       "abcdefghijklmnopqrstuvwxyz"
                       "0123456789_.-") != strlen(container_name)) {

            errno = EINVAL;
            return -1;
    }

    if (dir_if_missing("/var/lib/vcontainer", 0755) != 0 ||
        dir_if_missing("/var/lib/vcontainer/containers", 0755) != 0){
            return -1;
    }

    if (snprintf(container_dir, sizeof(container_dir),
        "/var/lib/vcontainer/containers/%s", container_name) >=
        (int)sizeof(container_dir) ||
        snprintf(log_path, sizeof(log_path),
                        "%s/container.log", container_dir) >=
                        (int)sizeof(log_path)) {

        errno = ENAMETOOLONG;
        return -1;
    }

    if (dir_if_missing(container_dir, 0755) != 0){
        return -1;
    }

    return open(log_path, PERMS, 0644);
}
