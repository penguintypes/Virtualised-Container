#include "cgroup.h"

#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

int cgroup_call(const char *action, const char *id,
    const char *memory_max, const char *pids_max,
    const char *cpu_quota, const char *cpu_period,
    pid_t container_pid)
{
    char pid_text[32];
    snprintf(pid_text, sizeof(pid_text), "%ld", (long)container_pid);

    pid_t bash_pid = fork();

    if(bash_pid == -1) {
        perror("fork");
        return -1;
    }

    if (bash_pid == 0){
        char *args[] = {
            "/bin/bash",
            "/opt/vcontainer/libexec/cgroup.sh",
            (char *)action,
            (char *)id,
            (char *)memory_max,
            (char *)pids_max,
            (char *)cpu_quota,
            (char *)cpu_period,
            pid_text,
            NULL
        };
        execv("/bin/bash", args);
        perror("execv");
        _exit(127);
    }

    int status;

    if(waitpid(bash_pid, &status, 0) == -1) {
        perror("waitpid");
        return -1;
    }

    return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -1;
}
