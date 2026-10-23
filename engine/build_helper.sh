#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
shift || true

case "$cmd" in
    install)
        [ "$1" = "-D" ] && [ "$2" = "-m" ] && [ "$3" = "644" ] || exit 1
        exec install "$@"
        ;;
    chroot|tee)
        exec "$cmd" "$@"
        ;;
    cp)
        [ "$1" = "-a" ] || exit 1
        exec cp "$@"
        ;;
    tar)
        [ "$1" = "-C" ] || exit 1
        exec tar "$@"
        ;;
    du)
        [ "$1" = "-sb" ] || exit 1
        exec du "$@"
        ;;
    mkdir)
        [ "$1" = "-p" ] || exit 1
        exec mkdir "$@"
        ;;
    rm)
        [ "$1" = "-rf" ] || exit 1
        # Security constraint: only allow recursive rm in safe directories
        if [[ "$2" == /tmp/* ]] || [[ "$2" == /var/lib/vcontainer/* ]]; then
            exec rm "$@"
        fi
        echo "Unsafe rm path: $2" >&2
        exit 1
        ;;
    *)
        echo "Forbidden build command: $cmd" >&2
        exit 1
        ;;
esac
