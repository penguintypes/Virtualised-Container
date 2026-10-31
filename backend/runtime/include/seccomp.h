#ifndef VCONTAINER_SECCOMP_H
#define VCONTAINER_SECCOMP_H

#include <stdbool.h>
#include <stddef.h>

int seccomp_config(bool enabled, const char *const denied[],
    size_t denied_count);

#endif
