#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "network.h"

int network_setup_bridge(const char *name, pid_t child,
                         const char *ip_address)
{
    char child_pid[32];
    pid_t helper;
    int status;

    if (snprintf(child_pid, sizeof(child_pid), "%ld", (long)child) >=
        (int)sizeof(child_pid)) {
        errno = EOVERFLOW;
        return -1;
    }

    helper = fork();
    if (helper < 0)
        return -1;

    if (helper == 0) {
        execl("/tmp/vcontainer-work/network.sh",
              "network.sh", "setup", name, child_pid, ip_address,
              (char *)NULL);
        _exit(127);
    }

    if (waitpid(helper, &status, 0) != helper)
        return -1;

    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        errno = EIO;
        return -1;
    }

    return 0;
}

int network_configure_resolver(void)
{
    static const char contents[] = "nameserver 1.1.1.1\n";
    static const char temporary[] = "/etc/.vcontainer-resolv.conf";
    int fd = open(temporary, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC,
                  0644);
    if (fd < 0)
        return -1;

    if (write(fd, contents, sizeof(contents) - 1) !=
        (ssize_t)(sizeof(contents) - 1)) {
        int saved_errno = errno;
        close(fd);
        errno = saved_errno ? saved_errno : EIO;
        return -1;
    }

    if (close(fd) != 0)
        return -1;

    return rename(temporary, "/etc/resolv.conf");
}
