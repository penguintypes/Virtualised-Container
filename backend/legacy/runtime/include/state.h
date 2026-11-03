#ifndef VCONTAINER_STATE_H
#define VCONTAINER_STATE_H

#include <stdbool.h>
#include <stddef.h>

struct container_volume {
    const char *source;
    const char *target;
};

int state_write(const char *name, const char *image, const char *rootfs,
    bool detach, const char *memory_max, const char *pids_max,
    const char *cpu_quota, const char *cpu_period,
    const struct container_volume volumes[], size_t volume_count,
    char *const command[]);

int state_save_launch(const char *name, int argc, char *const argv[]);

int state_load_launch(const char *name, int *argc, char ***argv);

void state_free_launch(int argc, char **argv);

#endif
