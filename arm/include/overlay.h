#ifndef VCONTAINER_OVERLAY_H
#define VCONTAINER_OVERLAY_H


#include <stddef.h>

int overlay_mount_rootfs(const char *lowerdir, const char *container_name,
    char *merged_path, size_t merged_path_size);

#endif
