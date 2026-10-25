#include <stdio.h>
#include <string.h>
#include <sys/errno.h>
#include <sys/mount.h>
#include <sys/stat.h>

#include "overlay.h"

static int dir_directory(const char *path){

    struct stat status;

    if(mkdir(path, 0755) == 0){
        return 0;
    }

    if(errno != EEXIST){
        return -1;
    }

    if (stat(path, &status) != 0 || !S_ISDIR(status.st_mode))  {
        errno = ENOTDIR;
        return -1;
    }

    return 0;
}

int overlay_mount_rootfs(const char *lowerdir, const char *container_name,
    char *merged_path, size_t merged_path_size){

        char container_dir[4096];
        char overlay_dir[4096];
        char upper_dir[4096];
        char work_dir[4096];
        char options[12288];


        if (lowerdir == NULL || lowerdir[0] != '/' ||
               container_name == NULL || container_name[0] == '\0' ||
               strspn(container_name,
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                      "abcdefghijklmnopqrstuvwxyz"
                      "0123456789_.-") != strlen(container_name)) {
               errno = EINVAL;
               return -1;
           }

           if (dir_directory("/var/lib/vcontainer") != 0 ||
               dir_directory("/var/lib/vcontainer/containers") != 0) {
               return -1;
           }

           if(snprintf(container_dir, sizeof(container_dir),
                        "/var/lib/vcontainer/containers/%s",
                        container_name) >= (int)sizeof(container_dir) ||
              snprintf(overlay_dir, sizeof(overlay_dir),
                        "%s/overlay", container_dir) >= (int)sizeof(overlay_dir) ||
              snprintf(upper_dir, sizeof(upper_dir),
                        "%s/upper", overlay_dir) >= (int)sizeof(upper_dir) ||
              snprintf(work_dir, sizeof(work_dir),
                        "%s/work", overlay_dir) >= (int)sizeof(work_dir) ||
              snprintf(merged_path, merged_path_size,
                        "%s/merged", overlay_dir) >= (int)merged_path_size) {
                      errno = ENAMETOOLONG;
                      return -1;
            }

            if(dir_directory(container_dir) != 0 ||
                dir_directory(overlay_dir) != 0 ||
                dir_directory(upper_dir) != 0 ||
                dir_directory(work_dir) != 0 ||
                dir_directory(merged_path) != 0) {
                return -1;
            }

            if (snprintf(options, sizeof(options),
                "lowerdir=%s,upperdir=%s,workdir=%s",
                lowerdir, upper_dir, work_dir) >= (int)sizeof(options)) {

                errno = ENAMETOOLONG;
                return -1;
            }

            return mount("overlay", merged_path, "overlay", 0, options);
}
