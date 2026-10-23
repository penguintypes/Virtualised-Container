#!/usr/bin/env bash
set -u
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
printf 'shell: '; bash -n "$root/engine/run_container.sh" && echo ok
printf 'engine source: '; make -C "$root/engine" >/dev/null && echo ok || echo failed
printf 'subuid: '; grep -q "^${USER}:" /etc/subuid && echo ok || echo missing
printf 'subgid: '; grep -q "^${USER}:" /etc/subgid && echo ok || echo missing
printf 'cgroup v2: '; test -f /sys/fs/cgroup/cgroup.controllers && echo ok || echo missing
printf 'overlay: '; grep -qw overlay /proc/filesystems && echo ok || echo missing
for x in skopeo umoci ip socat curl; do printf '%s: ' "$x"; command -v "$x" >/dev/null && echo ok || echo missing; done
echo 'UNVERIFIED here: namespaces, cgroups, overlay mounts, bridge networking, socat localhost relay, Alpine pulls, sample servers, and resource-limit enforcement.'
