#!/usr/bin/env bash

set -euo pipefail

# The Windows launcher enters WSL as root; direct Linux use retains sudo.
if [ "$(id -u)" -eq 0 ]; then
    sudo() { "$@"; }
    export -f sudo
fi
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

usage() {
    cat >&2 <<'USAGE'
Usage: vcontainer COMMAND
  run IMAGE --name NAME [--detach] [--volume NAME:/TARGET]
      [--bind /HOST/DIRECTORY:/TARGET]
      [--network bridge --ip ADDRESS] [RESOURCE OPTIONS] -- COMMAND [ARGS...]
  pull LOCAL_NAME [REMOTE_REFERENCE]
  list
  delete IMAGE
  ps                         Show status, host PIDs and saved command
  inspect CONTAINER
  logs [-f] CONTAINER
  exec CONTAINER -- COMMAND [ARGS...]
  start CONTAINER             Run the saved command using existing container files
  stop CONTAINER             Kill all processes and wait for cgroup cleanup
  rm CONTAINER               Remove a stopped container's metadata
  volume {create|list|inspect|remove} [NAME]
  help
USAGE
}
fail() { echo "vcontainer: $*" >&2; exit 2; }

action="${1:-help}"

case "$action" in
    help|--help|-h) usage; exit 0 ;;
    pull)
        [ "$#" -ge 2 ] && [ "$#" -le 3 ] || usage
        image="$2"
        case "$image" in
            ""|.|..|*[!A-Za-z0-9_.-]*)
                echo "invalid local image name: $image" >&2
                exit 2
                ;;
        esac
        reference="${3:-docker.io/library/$image:latest}"

        sudo bash /opt/vcontainer/libexec/image.sh pull "$image" "$reference"
        exit 0
        ;;
    volume)
        volume_action="${2:-}"
        volume_name="${3:-}"

        case "$volume_action" in
            create|inspect|remove)
                [ "$#" -eq 3 ] || {
                    echo "Usage: $0 volume $volume_action NAME" >&2
                    exit 2
                }
                ;;
            list)
                [ "$#" -eq 2 ] || {
                    echo "Usage: $0 volume list" >&2
                    exit 2
                }
                ;;
            *)
                echo "Usage: $0 volume {create|list|inspect|remove} [NAME]" >&2
                exit 2
                ;;
        esac
        case "$volume_name" in
            ""|.|..|*[!A-Za-z0-9_.-]*)
                if [ "$volume_action" != "list" ]; then
                    echo "invalid volume name: $volume_name" >&2
                    exit 2
                fi
                ;;
        esac

        bash -c '
            set -eu

            action="$1"
            name="$2"
            base="/var/lib/vcontainer/volumes"
            volume_dir="$base/$name"
            data_dir="$volume_dir/_data"

             case "$action" in
                create)
                    if sudo test -e "$volume_dir"; then
                        echo "volume already exists: $name" >&2
                        exit 1
                    fi

                    sudo install -d -m 0755 "$data_dir"
                    echo "created: $name"
                    ;;

                list)
                    [ -d "$base" ] || exit 0

                    for directory in "$base"/*; do
                        [ -d "$directory/_data" ] || continue
                        basename "$directory"
                    done
                    ;;

                inspect)
        [ "$#" -eq 2 ] || fail "Usage: vcontainer inspect CONTAINER"
                    if ! sudo test -d "$data_dir"; then
                        echo "volume not found: $name" >&2
                        exit 1
                    fi

                    echo "name=$name"
                    echo "mount_source=$data_dir"
                    ;;

                remove)
                    if ! sudo test -d "$data_dir"; then
                        echo "volume not found: $name" >&2
                        exit 1
                    fi

                    for group in /sys/fs/cgroup/vcontainer/*; do
                        [ -d "$group" ] || continue

                        for pid in $(sudo cat "$group/cgroup.procs"); do
                            if sudo grep -F -q -- "$data_dir" \
                                "/proc/$pid/mountinfo" 2>/dev/null; then
                                echo "volume is in use by container: ${group##*/}" >&2
                                exit 1
                            fi
                        done
                    done

                    # rmdir refuses non-empty volumes: no user data is deleted.
                    sudo rmdir "$data_dir"
                    sudo rmdir "$volume_dir"
                    echo "removed: $name"
                    ;;
            esac
        ' vcontainer-volume "$volume_action" "$volume_name"

        exit 0
        ;;
    list)
        [ "$#" -eq 1 ] || fail "Usage: vcontainer list"
        sudo /usr/local/sbin/vcontainer-read images | python3 -c '
import json, sys
print("IMAGE            ROOTFS")
for image in json.load(sys.stdin):
    print("{:<16} {}".format(image["name"], image["rootfs"]))'
        exit 0
        ;;
    run)
        [ "$#" -ge 3 ] || usage
        image="$2"
        case "$image" in
            ""|.|..|*[!A-Za-z0-9_.-]*) echo "invalid image name: $image" >&2; exit 2 ;;
        esac
        shift 2

        resolved_args=()

        while [ "$#" -gt 0 ]; do
            case "$1" in
                --)
                    resolved_args+=("$@")
                    break
                    ;;
                --volume)
                    [ "$#" -ge 2 ] || {
                        echo "--volume requires NAME:TARGET" >&2
                        exit 2
                    }

                    volume_spec="$2"
                    volume_name="${volume_spec%%:*}"
                    volume_target="${volume_spec#*:}"

                    case "$volume_name" in
                        ""|.|..|*[!A-Za-z0-9_.-]*)
                            echo "invalid volume name: $volume_name" >&2
                            exit 2
                            ;;
                    esac

                    case "$volume_target" in
                        /*) ;;
                        *)
                            echo "volume target must start with /" >&2
                            exit 2
                            ;;
                    esac

                    resolved_args+=(
                        "--volume"
                        "/var/lib/vcontainer/volumes/$volume_name/_data:$volume_target"
                    )
                    shift 2
                    ;;
                --bind)
                    [ "$#" -ge 2 ] || fail "--bind requires SOURCE:TARGET"
                    bind_spec="$2"
                    bind_source="${bind_spec%%:*}"
                    bind_target="${bind_spec#*:}"

                    [ -d "$bind_source" ] || fail \
                        "bind source not found: $bind_source"
                    case "$bind_source" in
                        /mnt/*) ;;
                        *) fail "bind source must be under /mnt" ;;
                    esac
                    case "$bind_target" in
                        /*) ;;
                        *) fail "bind target must be absolute" ;;
                    esac

                    resolved_args+=("--volume" "$bind_source:$bind_target")
                    shift 2
                    ;;
                *)
                    resolved_args+=("$1")
                    shift
                    ;;
            esac
        done

        set -- "${resolved_args[@]}"
        ;;
    delete)
        [ "$#" -eq 2 ] || fail "Usage: vcontainer delete IMAGE"
        image="${2:-}"

        case "$image" in
            ""|.|..|*[!A-Za-z0-9_.-]*) echo "invalid image name: $image" >&2; exit 2 ;;
        esac
        if [ -z "$image" ]; then
                echo "Usage: $0 delete <image>"
                exit 1
        fi

        bash -c '
            set -eu
            image="$1"
            sudo test -d "/var/lib/vcontainer/images/$image" || {
                echo "image not found: $image" >&2; exit 1;
            }
            if sudo grep -rlFx "image=$image" /var/lib/vcontainer/containers/*/config >/dev/null 2>&1; then
                echo "image is referenced by a container; remove its metadata first" >&2
                exit 1
            fi
            sudo rm -rf -- \
                "/var/lib/vcontainer/images/$image" \
                "/var/lib/vcontainer/oci/$image"
        ' vcontainer-delete "$image"
        exit 0
        ;;
    logs)
        follow=false

        if [ "${2:-}" = "-f" ]; then
            follow=true
            name="${3:-}"
            [ "$#" -eq 3 ] ||usage
        else
            name="${2:-}"
            [ "$#" -eq  2 ] || usage
        fi

        case "$name" in
            ""|.|..|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 logs [-f] CONTAINER" >&2
                exit 2
                ;;
        esac

        bash -c '
            set -eu

            follow="$1"
            name="$2"
            log="/var/lib/vcontainer/containers/$name/container.log"

            [ -f "$log" ] || {
                echo "no logs found for container: $name" >&2
                exit 1
            }

            if [ "$follow" = true ]; then
                sudo tail -n +1 -f "$log"
            else
                sudo cat "$log"
            fi
        ' vcontainer-logs "$follow" "$name"

        exit 0
        ;;
    inspect)
        [ "$#" -eq 2 ] || fail "Usage: vcontainer inspect CONTAINER"
        name="${2:-}"

        case "$name" in
            ""|.|..|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 inspect CONTAINER" >&2
                exit 2
                ;;
        esac

        bash -c '
            set -eu

            name="$1"
            group="/sys/fs/cgroup/vcontainer/$name"
            log="/var/lib/vcontainer/containers/$name/container.log"
            config="/var/lib/vcontainer/containers/$name/config"

            echo "name=$name"

            if sudo test -f "$config"; then
                echo "config:"
                sudo sed "s/^/ /" "$config"
            else
                echo "config="
            fi

            if [ -d "$group" ]; then
                pids=$(sudo cat "$group/cgroup.procs")

                if [ -n "$pids" ]; then
                    status="running"
                    pid=$(printf "%s\n" "$pids" | sed -n "1p")
                else
                    status="stopped"
                    pid=""
                fi

                echo "status=$status"
                echo "pids=$(printf "%s\n" "$pids" | tr "\n" " ")"
                echo "memory_max=$(sudo cat "$group/memory.max")"
                echo "memory_current=$(sudo cat "$group/memory.current")"
                echo "pids_max=$(sudo cat "$group/pids.max")"
                echo "pids_current=$(sudo cat "$group/pids.current")"
                echo "cpu_max=$(sudo cat "$group/cpu.max")"

                if [ -n "$pid" ]; then
                    echo "volumes:"

                    sudo awk '"'"'
                        $4 ~ /\/var\/lib\/vcontainer\/volumes\// {
                            volume = $4
                            sub("^.*/volumes/", "", volume)
                            sub("/_data$", "", volume)
                            printf "  %s:%s\n", volume, $5
                        }
                    '"'"' "/proc/$pid/mountinfo"
                fi
            else
                if sudo test -f "$config"; then
                    echo "status=stopped"
                else
                    echo "status=unknown"
                    echo "note=no saved container state exists"
                fi
            fi
            if sudo test -f "$log"; then
                echo "log=$log"
            else
                echo "log="
            fi
        ' vcontainer-inspect "$name"

        exit 0
        ;;
    ps)
        [ "$#" -eq 1 ] || fail "Usage: vcontainer ps"
        sudo /usr/local/sbin/vcontainer-read ps | python3 -c '
import json, sys, shlex
print("{:<20} {:<10} {:<20} {}".format("CONTAINER", "STATUS", "HOST PIDS", "COMMAND"))
for item in json.load(sys.stdin):
    print("{:<20} {:<10} {:<20} {}".format(item["name"], item["status"], ",".join(map(str, item["host_pids"])) or "-", shlex.join(item.get("command", []))))
print("Host PIDs include the main process and its child processes.")'
        exit 0
        ;;
    exec)
       name="${2:-}"

      case "$name" in
         ""|.|..|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 exec CONTAINER -- COMMAND [ARGS...]" >&2
                exit 2
                ;;
      esac

      [ "${3:-}" = "--" ] && [ "$#" -ge 4 ] ||{
          echo "Usage: $0 exec CONTAINER -- COMMAND [ARGS...]" >&2
          exit 2
      }

      shift 3

      bash -c '
        set -eu

        name="$1"
        shift
        group="/sys/fs/cgroup/vcontainer/$name"

        [ -d "$group" ] || {
            echo "container not found: $name" >&2
            exit 1
        }

        pid=$(sudo head -n 1 "$group/cgroup.procs")
        [ -n "$pid" ] || {
            echo "container is not running: $name" >&2
            exit 1
        }

        sudo sh -c '"'"'
            pid="$1"
            group="$2"
            shift 2

            printf "%s\n" "$$" > "$group/cgroup.procs"

            exec nsenter \
                --target "$pid" \
                --mount --uts --ipc --net --pid --user \
                --root="/proc/$pid/root" \
                --wd=/ \
                -- "$@"
            '"'"' sh "$pid" "$group" "$@"
      ' vcontainer-exec "$name" "$@"

      exit 0
      ;;
    rm)
        [ "$#" -eq 2 ] || fail "Usage: vcontainer rm CONTAINER"
        name="${2:-}"

         case "$name" in
            ""|.|..|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 rm CONTAINER" >&2
                exit 2
                ;;
        esac

        bash -c '
            set -eu

            name="$1"
            group="/sys/fs/cgroup/vcontainer/$name"
            state_dir="/var/lib/vcontainer/containers/$name"

            if [ -d "$group" ]; then
                pids=$(sudo cat "$group/cgroup.procs")

                if [ -n "$pids" ]; then
                    echo "container is running; $name " >&2
                    echo "stop it first: run_container.sh stop $name" >&2
                    exit 1
                fi

                sudo rmdir "$group"
            fi

            if ! sudo test -d "$state_dir"; then
                echo "container metadata not found: $name" >&2
                exit 1
            fi

            sudo rm -rf -- "$state_dir"
            echo "removed: $name"
        ' vcontainer-rm "$name"

        exit 0
        ;;
    start)
        [ "$#" -eq 2 ] || fail "Usage: vcontainer start CONTAINER"
        [ -x /opt/vcontainer/bin/vcontainer ] || fail "runtime not installed; run python setup.py"
        sudo /opt/vcontainer/bin/vcontainer start "$2"
        exit $?
        ;;
    stop)
        [ "$#" -eq 2 ] || fail "Usage: vcontainer stop CONTAINER (no PID argument)"
        name="$2"
        case "$name" in
            ""|.|..|*[!A-Za-z0-9_.-]*) fail "invalid container name: $name" ;;
        esac
        sudo bash -c '
            set -euo pipefail
            group="/sys/fs/cgroup/vcontainer/$1"
            if [ ! -d "$group" ]; then
                [ -d "/var/lib/vcontainer/containers/$1" ] || { echo "container not found: $1" >&2; exit 1; }
                echo "already stopped: $1"
                exit 0
            fi

            pid_file="/var/lib/vcontainer/containers/$1/init.pid"
            
           if [ -f "$pid_file" ]; then
                pid=$(cat "$pid_file")

                if [[ "$pid" =~ ^[0-9]+$ ]] &&
                grep -qx "$pid" "$group/cgroup.procs"; then
                    kill -TERM "$pid" 2>/dev/null || true
                fi
            fi

            for attempt in $(seq 1 100); do
                [ -d "$group" ] || break
                grep -q "^populated 0$" "$group/cgroup.events" && break
                sleep 0.1
            done

            if [ -d "$group" ] &&
            ! grep -q "^populated 0$" "$group/cgroup.events"; then
                echo 1 > "$group/cgroup.kill"
            fi
            for attempt in $(seq 1 100); do
                [ -d "$group" ] || break

                if grep -q "^populated 0$" "$group/cgroup.events"; then
                    rmdir "$group" 2>/dev/null && break
                fi

                sleep 0.05
            done
            [ ! -d "$group" ] || { echo "stop timed out; cgroup still busy: $1" >&2; exit 1; }
            echo "stopped: $1"
        ' vcontainer-stop "$name"
        exit 0
        ;;
    *)
        fail "unknown command: $action (use vcontainer help)"
        ;;
esac

[ -x /opt/vcontainer/bin/vcontainer ] || fail "runtime not installed; run python setup.py"
rootfs="/var/lib/vcontainer/images/$image/rootfs"
if ! sudo test -d "$rootfs"; then
    echo "Image missing; pulling: $image"
    sudo bash /opt/vcontainer/libexec/image.sh pull "$image"
fi
sudo /opt/vcontainer/bin/vcontainer run --image "$image" --seccomp "$@"
