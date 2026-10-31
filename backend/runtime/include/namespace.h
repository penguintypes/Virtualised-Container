#ifndef VCONTAINER_NAMESPACE_H
#define VCONTAINER_NAMESPACE_H

#include <stdbool.h>

/* Returns clone(2) flags for the container's isolated kernel views. */
int namespace_clone_flags(bool use_userns,bool use_network_namespace);

#endif
