#define _POSIX_C_SOURCE 200809L

#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/errno.h>
#include <seccomp.h>
#include <sys/prctl.h>
#include <errno.h>
#include <stddef.h>

#include "seccomp.h"

int seccomp_config(bool enabled, const char *const denied[],
    size_t denied_count){

    if (!enabled)
        return 0;

    scmp_filter_ctx filter = seccomp_init(SCMP_ACT_ALLOW);
    if(filter == NULL){
        return -1;
    }

    int blocked[] = {
        SCMP_SYS(mount),
        SCMP_SYS(umount2),
        SCMP_SYS(pivot_root),
        SCMP_SYS(reboot),
        SCMP_SYS(init_module),
        SCMP_SYS(finit_module),
        SCMP_SYS(delete_module),
        SCMP_SYS(ptrace),
        SCMP_SYS(unshare),
        SCMP_SYS(setns),
    };

    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        goto fail;
    }

    size_t length_of_block = sizeof(blocked) / sizeof(blocked[0]);
    size_t i;

    for(i = 0; i < length_of_block; ++i ){
        if(seccomp_rule_add(filter, SCMP_ACT_ERRNO(EPERM), blocked[i], 0) != 0){
            errno = EINVAL;
            goto fail;
        }
    }

    for (size_t i = 0; i < denied_count; ++i) {
        char *list = strdup(denied[i]);
        if (list == NULL) {
            goto fail;
        }

        char *save_pointer = NULL;
        char *name = strtok_r(list, ",", &save_pointer); // demm its like link list concpet

        if(name == NULL){
            free(list);
            errno = EINVAL;
            goto fail;
        }

        while (name != NULL){
            int syscall_number = seccomp_syscall_resolve_name(name);

            if (syscall_number < 0 ||
                seccomp_rule_add(filter, SCMP_ACT_ERRNO(EPERM),
                    syscall_number, 0) != 0) {

                free(list);
                errno = EINVAL;
                goto fail;
            }

            name = strtok_r(NULL, ",", &save_pointer);
        }

        free(list);
    }

    if (seccomp_load(filter) != 0){
        goto fail;
    }

    seccomp_release(filter);
    return 0;

    fail:
        seccomp_release(filter);
        return -1;

}
