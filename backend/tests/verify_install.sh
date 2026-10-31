#!/usr/bin/env bash

set -u

PASSED=0
FAILED=0

check() {
    description="$1"
    shift

    if "$@" >/dev/null 2>&1; then
        echo "PASS $description"
        PASSED=$((PASSED + 1))
    else
        echo "FAIL $description"
        FAILED=$((FAILED + 1))
    fi
}

check "WSL uses cgroup v2" \
    test "$(stat -fc %T /sys/fs/cgroup)" = "cgroup2fs"

check "overlay filesystem is supported" \
    grep -q overlay /proc/filesystems

check "C runtime is installed" \
    test -x /opt/vcontainer/bin/vcontainer

check "CLI wrapper is installed" \
    test -x /opt/vcontainer/bin/vcontainer-cli

check "image helper is installed" \
    test -x /opt/vcontainer/libexec/image.sh

check "network helper is installed" \
    test -x /opt/vcontainer/libexec/network.sh

check "read helper is installed" \
    test -x /usr/local/sbin/vcontainer-read

check "control helper is installed" \
    test -x /usr/local/sbin/vcontainer-control

check "image-control helper is installed" \
    test -x /usr/local/sbin/vcontainer-image-control

check "volume-control helper is installed" \
    test -x /usr/local/sbin/vcontainer-volume-control

check "API service is installed" \
    systemctl cat vcontainer-api.service

check "API service is running" \
    systemctl is-active --quiet vcontainer-api.service

check "API health endpoint responds" \
    curl --fail --silent http://127.0.0.1:8010/health

check "image storage exists" \
    test -d /var/lib/vcontainer/images

check "container storage exists" \
    test -d /var/lib/vcontainer/containers

check "skopeo is installed" command -v skopeo
check "umoci is installed" command -v umoci
check "socat is installed" command -v socat
check "ip is installed" command -v ip
check "iptables is installed" command -v iptables

echo "RESULT $PASSED/$((PASSED + FAILED)) passed"
[ "$FAILED" -eq 0 ]
