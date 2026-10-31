#ifndef VCONTAINER_WSL_PROCESS_H
#define VCONTAINER_WSL_PROCESS_H

#include <string.h>

/* Launch the wsl.exe */

int wsl_run(const char *const arguments[]);

#endif