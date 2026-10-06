#!/usr/bin/env  bash

set -euo pipefail

action="$1"
id="$2"
memory_max="$3"
pid_max="$4"
cpu_quota="$5"
cpu_period="$6"
container_pid="${7:-0}"

base="/sys/fs/cgroup/vcontainer"
group="$base/$id"

case "$action" in
    create)
        mkdir -p "$base"

        echo "+cpu +memory +pids" > /sys/fs/cgroup/cgroup.subtree_control
        echo "+cpu +memory +pids" > "$base/cgroup.subtree_control"

        mkdir "$group"
        echo "$memory_max" > "$group/memory.max"
        echo "$pid_max" > "$group/pids.max"
        echo "$cpu_quota $cpu_period" > "$group/cpu.max"
        ;;

    attach)
        echo "$container_pid" > "$group/cgroup.procs"
        ;;

    stats)
        echo "memory_current=$(cat "$group/memory.current")"
        echo "memory_peak=$(cat "$group/memory.peak")"
        echo "pid_current=$(cat "$group/pids.current")"
        cat "$group/cpu.stat"
        ;;

    destroy)
        rmdir "$group"
        ;;

    *)
        echo "usage: $0 {create|attach|stats|destroy} id memory pids cpu period [pid]" >&2
        exit 2
        ;;
esac
