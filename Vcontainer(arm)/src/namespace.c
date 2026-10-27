#define _GNU_SOURCE

#include <sched.h>

#include "namespace.h"

int namespace_clone_flags(bool use_userns,bool use_network_namespace)
{
    int flags = CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWIPC |
                CLONE_NEWUTS | CLONE_NEWCGROUP;

    if (use_userns)
        flags |= CLONE_NEWUSER;
    if (use_network_namespace)
        flags |= CLONE_NEWNET;

    return flags;
}
