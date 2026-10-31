/*#define WIN32_LEAN_AND_MEAN
#include <windows.h>*/

#include <stdio.h>
#include <string.h>
#include <stddef.h>

#include "machine.h"
#include "wsl_process.h"


#define MAX_MACHINE_NAME 63
#define MAX_DISTRO_NAME 96

static int valid_name(const char *name){

    if(name == NULL)
        return 0;

    size_t length = strlen(name);

    if (length == 0 || length > MAX_MACHINE_NAME) {
        return 0;
    }

    if(strspn(name, 
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789") == 0) {
        return 0;
    }


    return strspn(name,
         "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789_-") == length;

}

static int distribution_name(
       const char *name,
       char *output,
       size_t capacity 
) {

    if (!valid_name(name)) {
        fprintf(stderr, "Invalid machine name\n");
        return -1;
    }

    int length = snprintf(
        output, capacity, "vcontainer-%s", name
    );

    if (length < 0 || (size_t)length >= capacity) {
        fprintf(stderr, "Machine name is too long\n");
        return -1;
    }

    return 0;
}

int machine_create(
    const char *name,
    const char *dir,
    const char *rootfs
) {

    char distribution[MAX_DISTRO_NAME];

    if (distribution_name(
        name, distribution, sizeof(distribution)) != 0) {
            return -1;
    }

    if (dir == NULL || dir[0] == '\0' ||
        rootfs == NULL || rootfs[0] == '\0') {

            fprintf(stderr, "Install directory and rootfs are required\n");
            return -1;
    }

    const char *arguments[] = {
        "--import",
        distribution,
        dir,
        rootfs,
        "--version",
        "2",
        NULL
    };

    int result = wsl_run(arguments);

    if (result != 0) {
        fprintf(stderr, "Machine import failed: %s\n", name);
        return result;
    }

    printf("Machine imported: %s\n", name);
    return 0;

}

int machine_stop(const char *name) {

    char distribution[MAX_DISTRO_NAME];

    if (distribution_name(
        name, distribution, sizeof(distribution)
    ) != 0) {
        return -1;
    }

    const char *arguments[] = {
        "--terminate",
        distribution,
        NULL
    };

    int result = wsl_run(arguments);

    if (result != 0) {
        fprintf(stderr, "Could not stop machine: %s\n", name);
        return result;
    }

    printf("Machine stopped: %s\n", name);
    return 0;
}
