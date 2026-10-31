#ifndef VCONTAINER_NETWORK_H
#define VCONTAINER_NETWORK_H

#include <sys/types.h>

int network_setup_bridge(const char *name, pid_t child,
                         const char *ip_address);
int network_configure_resolver(void);

#endif
