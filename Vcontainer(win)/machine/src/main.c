#include <stdio.h>
#include <string.h>

#include "machine.h"
#include "wsl_process.h"


static void usage(void)
{
    puts(
        "Usage: vcontainer-machine COMMAND\n"
        "  list\n"
        "  create NAME DIRECTORY ROOTFS_ARCHIVE\n"
        "  stop NAME\n"
        "  help"
    );
}


int main(int argc, char **argv)
{
    int result;

    if (argc == 1 || strcmp(argv[1], "help") == 0) {
        usage();
        return 0;
    }

    if (strcmp(argv[1], "list") == 0) {
        if (argc != 2) {
            fprintf(stderr, "Usage: vcontainer-machine list\n");
            return 2;
        }

        const char *arguments[] = {
            "--list",
            "--verbose",
            NULL
        };

        result = wsl_run(arguments);
    }
    else if (strcmp(argv[1], "create") == 0) {
        if (argc != 5) {
            fprintf(stderr,
                "Usage: vcontainer-machine create "
                "NAME DIRECTORY ROOTFS_ARCHIVE\n");
            return 2;
        }

        result = machine_create(argv[2], argv[3], argv[4]);
    }
    else if (strcmp(argv[1], "stop") == 0) {
        if (argc != 3) {
            fprintf(stderr,
                "Usage: vcontainer-machine stop NAME\n");
            return 2;
        }

        result = machine_stop(argv[2]);
    }
    else {
        fprintf(stderr, "Unknown command: %s\n", argv[1]);
        usage();
        return 2;
    }

    return result < 0 ? 1 : result;
}