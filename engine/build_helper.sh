#!/usr/bin/env bash
set -euo pipefail

# Security: resolve symlinks and ensure path is within safe boundaries
safe_path() {
    local p
    p=$(realpath -m "$1")
    if [[ "$p" != /var/lib/vcontainer/* ]] && [[ "$p" != /tmp/* ]]; then
        echo "Unsafe path: $1 ($p)" >&2
        exit 1
    fi
    echo "$p"
}

cmd="${1:-}"
shift || true

case "$cmd" in
    install)
        [ "$1" = "-D" ] && [ "$2" = "-m" ] && [ "$3" = "644" ] || exit 1
        src=$(realpath -m "$4")
        dst=$(safe_path "$5")
        exec install -D -m 644 "$src" "$dst"
        ;;
    cp)
        [ "$1" = "-a" ] || exit 1
        raw="$2"
        src=$(realpath -m "$raw")
        [[ "$src" == /var/lib/vcontainer/* ]] || { echo "Unsafe source: $raw ($src)" >&2; exit 1; }
        [[ "$raw" == */. ]] && src="$src/."
        dst=$(safe_path "$3")
        exec cp -a "$src" "$dst"
        ;;
    tar)
        [ "$1" = "-C" ] || exit 1
        dir=$(safe_path "$2")
        [ "$3" = "-cf" ] || exit 1
        archive=$(safe_path "$4")
        shift 4
        # Security: block injected flags like --checkpoint-action
        for arg in "$@"; do
            if [[ "$arg" == -* ]]; then
                echo "Forbidden tar flag: $arg" >&2
                exit 1
            fi
        done
        exec tar -C "$dir" -cf "$archive" "$@"
        ;;
    du)
        [ "$1" = "-sb" ] || exit 1
        dir=$(safe_path "$2")
        exec du -sb "$dir"
        ;;
    mkdir)
        [ "$1" = "-p" ] || exit 1
        dir=$(safe_path "$2")
        exec mkdir -p "$dir"
        ;;
    rm)
        [ "$1" = "-rf" ] || exit 1
        dir=$(safe_path "$2")
        exec rm -rf "$dir"
        ;;
    write_file)
        # Security wrapper replacing raw tee
        dst=$(safe_path "$1")
        exec cat > "$dst"
        ;;
    run_chroot)
        # Security wrapper replacing raw chroot
        dir=$(safe_path "$1")
        shift
        exec chroot "$dir" "$@"
        ;;
    *)
        echo "Forbidden build command: $cmd" >&2
        exit 1
        ;;
esac
