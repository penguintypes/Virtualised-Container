# Vcontainer layout

- `src/`: runtime C sources and runtime helper scripts.
- `include/`: public internal headers shared by C sources.
- `tests/`: test programs.
- `examples/`: runnable command examples.
- `build/`: generated local binaries; not source code.

Persistent named volumes live in the Lima VM at
`/var/lib/vcontainer/volumes/<name>/_data`.
