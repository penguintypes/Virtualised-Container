# vContainer runtime layout

- `src/`: runtime C sources and runtime helper scripts.
- `include/`: public internal headers shared by C sources.
- `tests/`: test programs.
- `examples/`: runnable command examples.
- `build/`: generated local binaries; not source code.

Persistent named volumes live on the Ubuntu (WSL2) host at
`/var/lib/vcontainer/volumes/<name>/_data`.
