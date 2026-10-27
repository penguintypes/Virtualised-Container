#ifndef VCONTAINER_MACHINE_H
#define VCONTAINER_MACHINE_H

#include <string.h>

int machine_create(
    const char *name,
    const char *directory,
    const char *rootfs
);

int machine_stop(const char *name);

#endif