#!/usr/bin/env bash

set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
image_store=/var/lib/vcontainer/images

usage() {
    echo "Usage:" >&2
    echo " $0 list" >&2
    echo " $0 pull LOCAL_NAME [REMOTE_REFERENCE]" >&2
    echo " $0 run IMAGE --name NAME [OPTIONS] -- COMMAND [ARGS...]" >&2
    echo " $0 volume {create|list|inspect|remove} [NAME]" >&2
    echo " $0 exec CONTAINER -- COMMAND [ARGS...]" >&2
    echo " $0 logs [-f] CONTAINER" >&2
    echo " $0 inspect CONTAINER" >&2
    echo " $0 rm CONTAINER" >&2
    echo " $0 stop CONTAINER" >&2
    echo " $0 ps" >&2
    echo " Run this script inside your WSL 2 Linux distribution." >&2
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

        bash -c '
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
        bash -c '
            set -eu

            echo "Available images:"
            printf "%-16s %s\n" "IMAGE" "ROOTFS"

            for image_dir in /var/lib/vcontainer/images/*; do
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
        case "$image" in
            ""|.|..|*[!A-Za-z0-9_.-]*) echo "invalid image name: $image" >&2; exit 2 ;;
        esac
        shift 2

        resolved_args=()
        publish_port=""
        container_name=""
        container_ip=""

        while [ "$#" -gt 0 ]; do
            case "$1" in
                --)
                    resolved_args+=("$@")
                    break
                    ;;
                -p)
                    [ "$#" -ge 2 ] || { echo "-p requires HOST:CONTAINER" >&2; exit 2; }
                    publish_port="$2"
                    case "$publish_port" in
                        [0-9]*:[0-9]*) ;;
                        *) echo "-p requires HOST:CONTAINER" >&2; exit 2 ;;
                    esac
                    shift 2
                    ;;
                --name)
                    [ "$#" -ge 2 ] || { echo "--name requires NAME" >&2; exit 2; }
                    container_name="$2"
                    resolved_args+=("--name" "$2")
                    shift 2
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
                *)
                    resolved_args+=("$1")
                    shift
                    ;;
            esac
        done

        if [ -n "$publish_port" ]; then
            [ -n "$container_name" ] || { echo "-p requires --name" >&2; exit 2; }
            case "$container_name" in
                blog) container_ip=10.88.0.11 ;;
                runner) container_ip=10.88.0.12 ;;
                *) container_ip="10.88.0.$((10 + $(printf %s "$container_name" | cksum | awk '{print $1 % 200}')))" ;;
            esac
            resolved_args=(--network bridge --ip "$container_ip" "${resolved_args[@]}")
        fi
        set -- "${resolved_args[@]}"
        ;;
    import)
        [ "$#" -eq 3 ] || usage
        image="$2"
        archive="$3"
        case "$image" in
            ""|.|..|*[!A-Za-z0-9_.-]*) echo "invalid image name: $image" >&2; exit 2 ;;
        esac
        [ -f "$archive" ] || { echo "archive not found: $archive" >&2; exit 2; }
        bash -c '
            set -eu
            project_dir="$1"
            work=/tmp/vcontainer-work
            mkdir -p "$work"
            cp "$project_dir/src/image.sh" "$work/"
            cd "$work"
            sudo bash ./image.sh import "$2" "$3"
        ' vcontainer-import "$project_dir" "$image" "$archive"
        exit 0
        ;;
    delete)
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
                sudo tail -n 15 "$log"
            fi
        ' vcontainer-logs "$follow" "$name"

        exit 0
        ;;
    inspect)
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
        bash -c '
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
                --mount --uts --ipc --net --pid --user --cgroup \
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
            config="$state_dir/config"
            if sudo test -f "$config"; then
                port=$(sudo sed -n "s/^port=//p" "$config")
                if [ -n "$port" ]; then
                    host_port="${port%%:*}"
                    container_port="${port##*:}"
                    container_ip="10.88.0.$((10 + $(printf %s "$name" | cksum | awk "{print $1 % 200}")))"
                    if sudo test -f "$state_dir/port.pid"; then
                        sudo kill "$(sudo cat "$state_dir/port.pid")" 2>/dev/null || true
                    fi
                fi
            fi

            if [ -d "$group" ]; then
                pids=$(sudo cat "$group/cgroup.procs")

                if [ -n "$pids" ]; then
                    echo "container is running; $name " >&2
                    echo "stop it first: run_container.sh stop $name" >&2
                    exit 1
                fi

                sudo umount -l "/var/lib/vcontainer/containers/$name/overlay/merged" 2>/dev/null || true
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
            ""|.|..|*[!A-Za-z0-9_.-]*)
                echo "Usage: $0 stop CONTAINER" >&2
                exit 2
                ;;
        esac

        bash -c '
            set -eu
            name="$1"
            group="/sys/fs/cgroup/vcontainer/$name"

            [ -d "$group" ] || {
                echo "container not found: $name" >&2
                exit 1
            }

            sudo sh -c '"'"'echo 1 > "$1/cgroup.kill"'"'"' sh "$group"
            for attempt in $(seq 1 50); do
                [ -n "$(sudo cat "$group/cgroup.procs" 2>/dev/null)" ] || break
                sleep 0.1
            done
            if sudo test -f "/var/lib/vcontainer/containers/$name/port.pid"; then
                sudo kill "$(sudo cat "/var/lib/vcontainer/containers/$name/port.pid")" 2>/dev/null || true
            fi
            sudo umount -l "/var/lib/vcontainer/containers/$name/overlay/merged" 2>/dev/null || true
            sudo rmdir "$group"

            echo "stopped: $name"
        ' vcontainer-stop "$name"
        exit 0
        ;;
    *)
        usage
        ;;
esac

bash -c '
  set -eu

  project_dir="$1"
  work=/tmp/vcontainer-work
  mkdir -p "$work/src" "$work/include" "$work/build"

  cp "$project_dir/src/cgroup.sh" "$work/"
  cp "$project_dir/src/image.sh" "$work/"
  cp "$project_dir/src/network.sh" "$work/"

  cd "$work"
  chmod 755 cgroup.sh image.sh network.sh
' vcontainer-build "$project_dir"


bash -c '
  set -eu

  image="$1"
  publish_port="$2"
  container_name="$3"
  container_ip="$4"
  shift 4

  cd /tmp/vcontainer-work

  rootfs="/var/lib/vcontainer/images/$image/rootfs"

  if ! sudo chroot "$rootfs" /bin/sh -c "exit 0"; then
      echo "Image missing; pulling: $image"
      sudo ./image.sh pull "$image"
  fi

  if ! sudo chroot "$rootfs" /bin/sh -c "exit 0"; then
      echo "Image missing; pulling: $image"
      exit 1
  fi

  if [ -n "$publish_port" ]; then
      host_port="${publish_port%%:*}"
      container_port="${publish_port##*:}"
      sudo socat "TCP-LISTEN:$host_port,fork,reuseaddr" "TCP:$container_ip:$container_port" >/dev/null 2>&1 &
      socat_pid=$!
      (
        d="/var/lib/vcontainer/containers/$container_name"
        for _ in $(seq 1 100); do [ -f "$d/config" ] && break; sleep 0.2; done
        printf "%s\n" "$socat_pid" | sudo tee "$d/port.pid" >/dev/null
        printf "port=%s\n" "$publish_port" | sudo tee -a "$d/config" >/dev/null
      ) &
  fi

  cleanup() {
      # Wait briefly for container processes to finish terminating
      sleep 0.2

      # Detached container still alive: keep its port forwarder running
      if [ -n "$(sudo cat /sys/fs/cgroup/vcontainer/$container_name/cgroup.procs 2>/dev/null)" ]; then
          return 0
      fi

      # Container is gone: kill port-forwarding if active
      [ -n "${socat_pid:-}" ] && sudo kill "$socat_pid" 2>/dev/null || true
      
      # 3. Remove leftover cgroup directories (fails safely if already gone or not empty)
      sudo rmdir "/sys/fs/cgroup/vcontainer/$container_name" 2>/dev/null || true
      sudo rmdir "/sys/fs/cgroup/$container_name" 2>/dev/null || true
  }
  trap cleanup EXIT INT TERM
  sudo /usr/local/libexec/vcontainer/build/vcontainer run \
    --image "$image" \
    "$@"
' vcontainer-run "$image" "$publish_port" "$container_name" "$container_ip" "$@"
