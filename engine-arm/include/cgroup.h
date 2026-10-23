#ifndef CGROUP_H
#define CGROUP_H

#include <sys/types.h>

int cgroup_call(const char *action, const char *id,
    const char *memory_max, const char *pid_max,
    const char *cpu_quota, const char *cpu_period,
    pid_t container_pid);

#endif
