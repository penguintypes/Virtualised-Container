#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stddef.h>

#include  "wsl_process.h"

#define MAX_COMMAND_BYTES (128 * 1024)
#define MAX_COMMAND_WCHARS 32767

static int append_char(char *command, size_t *used, char value){

    if(*used >= MAX_COMMAND_BYTES - 1){
        return -1;
    }

    command[(*used)++] = value;
    command[*used] = '\0';

    return 0;
}

static int append_argument(
    char *command,
    size_t *used,
    const char *argument)
{
    /* WSL scans its leading options directly; leave simple tokens unquoted. */
    if (*argument != '\0' && strpbrk(argument, " \t\r\n\v\f\"") == NULL) {
        while (*argument != '\0') {
            if (append_char(command, used, *argument++) != 0)
                return -1;
        }
        return 0;
    }

    if (append_char(command, used, '"') != 0)
        return -1;

    while (*argument != '\0') {
        size_t slashes = 0;

        while (*argument == '\\') {
            if (++slashes >= MAX_COMMAND_BYTES)
                return -1;

            ++argument;
        }

        /*
         * Backslashes before a quote or the closing quote
         * must be doubled.
         */
        if (*argument == '"' || *argument == '\0') {
            slashes *= 2;

            if (*argument == '"')
                ++slashes;
        }

        for (size_t i = 0; i < slashes; ++i) {
            if (append_char(command, used, '\\') != 0)
                return -1;
        }

        if (*argument == '\0')
            break;

        if (append_char(command, used, *argument++) != 0)
            return -1;
    }

    return append_char(command, used, '"');
}

int wsl_run(const char *const arguments[])
{
    if (arguments == NULL) {
        fprintf(stderr, "WSL arguments are required\n");
        return -1;
    }

    /*
     * Resolve the actual Windows executable instead of searching
     * the current directory for an executable named wsl.exe.
     */
    wchar_t executable[MAX_PATH + 16];
    BOOL wow64 = FALSE;
    if (!IsWow64Process(GetCurrentProcess(), &wow64)) {
        fprintf(stderr, "Could not determine Windows process architecture\n");
        return -1;
    }

    UINT length = wow64
        ? GetWindowsDirectoryW(executable, MAX_PATH)
        : GetSystemDirectoryW(executable, MAX_PATH);

    if (length == 0 || length >= MAX_PATH) {
        fprintf(stderr, "Could not locate Windows system directory\n");
        return -1;
    }

    /* Bypass System32 redirection when built with a 32-bit compiler. */
    wcscat(executable, wow64 ? L"\\Sysnative\\wsl.exe" : L"\\wsl.exe");

    char *command = calloc(MAX_COMMAND_BYTES, 1);
    if (command == NULL) {
        fprintf(stderr, "Could not allocate command buffer\n");
        return -1;
    }

    size_t used = 0;

    /* First command-line argument is the executable name. */
    if (append_argument(command, &used, "wsl.exe") != 0)
        goto too_long;

    for (size_t i = 0; arguments[i] != NULL; ++i) {
        if (append_char(command, &used, ' ') != 0 ||
            append_argument(command, &used, arguments[i]) != 0) {
            goto too_long;
        }
    }

    /* Convert the UTF-8 command into Windows UTF-16. */
    int wide_size = MultiByteToWideChar(
        CP_UTF8,
        MB_ERR_INVALID_CHARS,
        command,
        -1,
        NULL,
        0
    );

    if (wide_size == 0 || wide_size > MAX_COMMAND_WCHARS) {
        fprintf(stderr, "Command is invalid UTF-8 or too long\n");
        free(command);
        return -1;
    }

    wchar_t *wide_command = malloc(
        (size_t)wide_size * sizeof(*wide_command)
    );

    if (wide_command == NULL) {
        free(command);
        return -1;
    }

    if (MultiByteToWideChar(
            CP_UTF8, MB_ERR_INVALID_CHARS,
            command, -1, wide_command, wide_size) == 0) {
        fprintf(stderr, "Could not convert command to UTF-16\n");
        free(command);
        free(wide_command);
        return -1;
    }

    free(command);

    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};

    startup.cb = sizeof(startup);

    /* Let WSL use the caller's terminal or redirected streams. */
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);

    BOOL started = CreateProcessW(
        executable,
        wide_command,
        NULL,
        NULL,
        TRUE,
        0,
        NULL,
        NULL,
        &startup,
        &process
    );

    free(wide_command);

    if (!started) {
        fprintf(stderr, "Could not launch WSL: Windows error %lu\n",
            (unsigned long)GetLastError());
        return -1;
    }

    CloseHandle(process.hThread);

    if (WaitForSingleObject(process.hProcess, INFINITE)
            != WAIT_OBJECT_0) {
        fprintf(stderr, "Could not wait for WSL: Windows error %lu\n",
            (unsigned long)GetLastError());

        CloseHandle(process.hProcess);
        return -1;
    }

    DWORD exit_code;

    if (!GetExitCodeProcess(process.hProcess, &exit_code)) {
        fprintf(stderr, "Could not read WSL exit code\n");
        CloseHandle(process.hProcess);
        return -1;
    }

    CloseHandle(process.hProcess);

    return exit_code <= INT_MAX ? (int)exit_code : 1;

too_long:
    fprintf(stderr, "WSL command is too long\n");
    free(command);
    return -1;
}
