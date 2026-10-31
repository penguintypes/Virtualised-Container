#!/usr/bin/env bash
set -eu

bridge=vcbr0
subnet=10.88.0.0/24
gateway=10.88.0.1
prefix=24

fail() {
    echo "vcontainer-network: $*" >&2
    exit 1
}

init_bridge() {
    if ! ip link show "$bridge" >/dev/null 2>&1; then
        ip link add "$bridge" type bridge
        ip addr add "$gateway/$prefix" dev "$bridge"
        ip link set "$bridge" up
    fi

    sysctl -w net.ipv4.ip_forward=1 >/dev/null

    uplink=$(ip route show default | awk 'NR == 1 { print $5 }')
    [ -n "$uplink" ] || fail "no default route found"

    iptables -t nat -C POSTROUTING \
        -s "$subnet" -o "$uplink" -j MASQUERADE 2>/dev/null ||
        iptables -t nat -A POSTROUTING \
            -s "$subnet" -o "$uplink" -j MASQUERADE

    iptables -C FORWARD -i "$bridge" -o "$uplink" -j ACCEPT 2>/dev/null ||
        iptables -A FORWARD -i "$bridge" -o "$uplink" -j ACCEPT

    iptables -C FORWARD -i "$uplink" -o "$bridge" \
        -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null ||
        iptables -A FORWARD -i "$uplink" -o "$bridge" \
            -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

}

interface_names() {
    token=$(printf '%s' "$1" | cksum | awk '{ print $1 }')
    host_interface="vch$token"
    container_interface="vcc$token"

}

setup_container() {
    name="$1"
    pid="$2"
    ip_address="$3"

    case "$ip_address" in
        10.88.0.*) ;;
        *) fail "container IP must be inside 10.88.0.0/24" ;;
    esac

    init_bridge
    interface_names "$name"

    ip link show "$host_interface" >/dev/null 2>&1 &&
        fail "network already exists for container: $name"

    ip link add "$host_interface" type veth peer name "$container_interface"
    ip link set "$host_interface" master "$bridge"
    ip link set "$host_interface" up
    ip link set "$container_interface" netns "$pid"

    nsenter --target "$pid" --net ip link set lo up
    nsenter --target "$pid" --net ip link set "$container_interface" name eth0
    nsenter --target "$pid" --net ip addr add "$ip_address/$prefix" dev eth0
    nsenter --target "$pid" --net ip link set eth0 up
    nsenter --target "$pid" --net ip route replace default via "$gateway"
}

case "${1:-}" in
    init)
        init_bridge
        ;;
    setup)
        [ "$#" -eq 4 ] || fail "Usage: $0 setup NAME PID IP"
        setup_container "$2" "$3" "$4"
        ;;
    *)
        fail "Usage: $0 {init|setup}"
        ;;
esac
