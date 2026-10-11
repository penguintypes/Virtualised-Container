#!/usr/bin/env bash

set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

usage() {
    echo "Usage:" >&2
    echo " $0 list" >&2
    echo " $0 pull LOCAL_NAME [REMOTE_REFERENCE]" >&2
    echo " $0 run IMAGE COMMAND [ARGS...]" >&2
    echo " $0 volume {create|list|inspect|remove} [NAME]" >&2
    echo " $0 exec CONTAINER -- COMMAND [ARGS...]" >&2
    echo " $0 logs [-f] CONTAINER" >&2
    echo " $0 inspect CONTAINER" >&2
    echo " $0 rm CONTAINER" >&2
    echo " $0 [--network bridge --ip ADDRESS] "
    exit 2
}

action="${1:-}"

case "$action" in
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

        lima sh -lc '
            set -eu
            project_dir="$1"
            work=/tmp/vcontainer-work
            mkdir -p "$work"
            cp "$project_dir/src/image.sh" "$work/"
            cd "$work"
            sudo bash ./image.sh pull "$2" "$3"
        ' vcontainer-pull "$project_dir" "$image" "$reference"
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

        lima sh -lc '
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
        lima sh -lc '
            set -eu

            echo "Available images:"
            printf "%-16s %s\n" "IMAGE" "ROOTFS"

            for image_dir in /tmp/vcontainer-images/*; do
                [ -d "$image_dir/rootfs" ] || continue
                printf "%-16s %s\n" \
                "$(basename "$image_dir")" \
                "$image_dir/rootfs"
            done
        '
        exit 0
        ;;
    run)
        [ "$#" -ge 3 ] || usage
        image="$2"
        shift 2

        resolved_args=()

        while [ "$#" -gt 0 ]; do
            case "$1" in
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
                *)
                    resolved_args+=("$1")
                    shift
                    ;;
            esac
        done

        set -- "${resolved_args[@]}"
        ;;
    delete)
        image="${2:-}"

        if [ -z "$image" ]; then
                echo "Usage: $0 delete <image>"
                exit 1
        fi

        lima sh -lc '
            set -eu
            image="$1"
            sudo rm -rf -- \
                "/tmp/vcontainer-images/$image" \
                "/tmp/vcontainer-oci/$image"
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
            ""|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 logs [-f] CONTAINER" >&2
                exit 2
                ;;
        esac

        lima sh -lc '
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
        name="${2:-}"

        case "$name" in
            ""|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 inspect CONTAINER" >&2
                exit 2
                ;;
        esac

        lima sh -lc '
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
        lima sh -lc '
            set -eu

            sudo sh -c '"'"'
                printf "%-16s %s\n" "CONTAINER" "PIDS"

                for group in /sys/fs/cgroup/vcontainer/*; do
                    [ -d "$group" ] || continue

                    pids=$(cat "$group/cgroup.procs")
                    [ -n "$pids" ] || continue

                    name=${group##*/}
                    printf "%-16s %s\n" "$name" "$(echo "$pids" | tr "\n" " ")"
                done
            '"'"'
        '
        exit 0
        ;;
    exec)
       name="${2:-}"

      case "$name" in
         ""|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 exec CONTAINER -- COMMAND [ARGS...]" >&2
                exit 2
                ;;
      esac

      [ "${3:-}" = "--" ] && [ "$#" -ge 4 ] ||{
          echo "Usage: $0 exec CONTAINER -- COMMAND [ARGS...]" >&2
          exit 2
      }

      shift 3

      lima sh -lc '
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
        name="${2:-}"

         case "$name" in
            ""|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 rm CONTAINER" >&2
                exit 2
                ;;
        esac

        lima sh -lc '
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
    stop)
        name="${2:-}"

        case "$name" in
            ""|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 stop CONTAINER" >&2
                exit 2
                ;;
        esac

        lima sh -lc '
            set -eu
            name="$1"
            group="/sys/fs/cgroup/vcontainer/$name"

            [ -d "$group" ] || {
                echo "container not found: $name" >&2
                exit 1
            }

            sudo sh -c '"'"'echo 1 > "$1/cgroup.kill"'"'"' sh "$group"
            sudo rmdir "$group"

            echo "stopped: $name"
        ' vcontainer-stop "$name"
        exit 0
        ;;
    *)
        usage
        ;;
esac

lima sh -lc '
  set -eu

  project_dir="$1"
  work=/tmp/vcontainer-work
  mkdir -p "$work/src" "$work/include" "$work/build"

  cp "$project_dir/src/vcontainer.c" "$work/src/"
  cp "$project_dir/src/cgroup.c" "$work/src/"
  cp "$project_dir/src/namespace.c" "$work/src/"
  cp "$project_dir/src/seccomp.c" "$work/src/"
  cp "$project_dir/src/remember.c" "$work/src/"
  cp "$project_dir/src/log.c" "$work/src/"
  cp "$project_dir/src/state.c" "$work/src/"
  cp "$project_dir/src/overlay.c" "$work/src/"
  cp "$project_dir/src/network.c" "$work/src/"
  cp "$project_dir/include/cgroup.h" "$work/include/"
  cp "$project_dir/include/namespace.h" "$work/include/"
  cp "$project_dir/include/seccomp.h" "$work/include/"
  cp "$project_dir/include/remember.h" "$work/include/"
  cp "$project_dir/include/log.h" "$work/include/"
  cp "$project_dir/include/state.h" "$work/include/"
  cp "$project_dir/include/overlay.h" "$work/include/"
  cp "$project_dir/include/network.h" "$work/include/"
  cp "$project_dir/src/cgroup.sh" "$work/"
  cp "$project_dir/src/image.sh" "$work/"
  cp "$project_dir/src/network.sh" "$work/"
  cp "$project_dir/Makefile" "$work/"

  cd "$work"
  chmod 755 cgroup.sh image.sh network.sh
  make clean
  make
' vcontainer-build "$project_dir"


lima sh -lc '
  set -eu

  image="$1"
  shift

  cd /tmp/vcontainer-work

  rootfs="/tmp/vcontainer-images/$image/rootfs"

  if ! sudo test -x "$rootfs/bin/sh"; then
      echo "Image missing; pulling: $image"
      sudo ./image.sh pull "$image"
  fi

  if ! sudo test -x "$rootfs/bin/sh"; then
      echo "Image missing; pulling: $image"
      exit 1
  fi

  sudo ./build/vcontainer run \
    --image "$image" \
    "$@"
' vcontainer-run "$image" "$@"

# Cgroup v2 smoke test: create a limited group, attach one process, print
# metrics, then stop that process so the group can be removed.

#lima sh -lc '
 # set -eu
  #cd /tmp/vcontainer-work

  #sudo ./cgroup.sh create test1 256M 64 50000 100000

  #sleep 30 &
  #test_pid=$!

  #sudo ./cgroup.sh attach test1 max max max 100000 "$test_pid"

  #echo "Process cgroup:"
  #cat "/proc/$test_pid/cgroup"

 # echo "Cgroup statistics:"
 # sudo ./cgroup.sh stats test1 max max max 100000

 # kill "$test_pid"
 # wait "$test_pid" || true

  #sudo ./cgroup.sh destroy test1 max max max 100000
#'

# line (69)
#if ! sudo test -x "$rootfs/bin/sh"; then
#  case "$image" in
#    alpine)
      # Preserve a broken/partial import instead of deleting it.
#      if [ -e /tmp/vcontainer-images/alpine ]; then
 #       sudo mv /tmp/vcontainer-images/alpine \
 #         "/tmp/vcontainer-images/alpine-invalid-$(date +%s)"
  #    fi

      #sudo ./image.sh import alpine \
       # "/Users/nodyhody/Productivity/virtualised_container copy/custom-initramfs.cpio.gz"
      #;;
    #*)
      #echo "image is missing: $image" >&2
      #echo "import it first with image.sh" >&2
      #exit 1
      #;;
  #esac
#fi

#if ! sudo test -x "$rootfs/bin/sh"; then
#  echo "image not imported or has no /bin/sh: $image" >&2
#  exit 1
#fi
