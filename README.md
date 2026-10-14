# Virtualised-Container

A learning project and also a minor project of our college blah blah blah.
still working on the engine ....

peace


01. stop fails with rmdir: failed to remove '/sys/fs/cgroup/vcontainer/test': Device or resource busy. The cgroup is removed while processes are still in it.
02. stop test fails but stop test <pid> succeeds. Stop behaves differently depending on the extra PID argument.
03. After a failed stop, the processes are gone from ps but the cgroup directory is left behind (stale state).
04. ps shows two PIDs per container (e.g. 509 514) with no explanation, and no status or command.
05. The rootfs lives in /tmp, so it is missing after a WSL restart.
06. run tries chroot before checking that the image exists, which produces the “cannot change root directory” error on every first run.
07. The image is re-pulled on every run after /tmp is wiped. list then shows no images.
08. run rebuilds the binary every time (rm -f build/vcontainer followed by cc).
09. sudo asks for a password on every command.
10. delete is not a valid command, but it gives no “unknown command” error, just silent output.
11. The no-argument usage output is malformed. It shows full /mnt/c/... paths instead of a short command name, and the “Run this script inside your WSL 2...” line and the [--network bridge --ip ADDRESS] line are appended oddly at the end.
12. The wrapper prints Arguments: and Command: debug lines on every call.
13. stop with no container name only prints usage and takes no useful action. The usage also doesn’t mention the optional PID argument that stop accepts.
14. run printed “container started” even when the earlier command (/bash/sh) was invalid, because it never checks whether the child exec succeeded. This was seen in the previous log.

