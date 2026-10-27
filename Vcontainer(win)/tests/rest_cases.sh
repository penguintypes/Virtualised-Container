#!/usr/bin/env bash

set -u

API_URL="${VCONTAINER_API_URL:-http://127.0.0.1:8010}"
IMAGE="${VCONTAINER_TEST_IMAGE:-alpine}"
CONTENT_TYPE="Content-Type: application/json"
PASSED=0
FAILED=0

request() {
    method="$1"
    path="$2"
    data="${3:-}"

    if [ -n "$data" ]; then
        curl --silent --show-error --fail-with-body \
            --request "$method" \
            --header "$CONTENT_TYPE" \
            --data "$data" \
            "$API_URL$path"
    else
        curl --silent --show-error --fail-with-body \
            --request "$method" \
            "$API_URL$path"
    fi
}

cleanup_container() {
    name="$1"
    request POST "/containers/$name/stop" >/dev/null 2>&1 || true
    request DELETE "/containers/$name" >/dev/null 2>&1 || true
}

container_status() {
    name="$1"
    request GET "/containers/$name" 2>/dev/null | python3 -c '
import json
import sys

try:
    print(json.load(sys.stdin).get("status", ""))
except (json.JSONDecodeError, AttributeError):
    pass
'
}

wait_for_status() {
    name="$1"
    expected="$2"

    attempt=0
    while [ "$attempt" -lt 100 ]; do
        status=$(container_status "$name")
        [ "$status" = "$expected" ] && return 0
        sleep 0.1
        attempt=$((attempt + 1))
    done

    return 1
}

container_logs() {
    name="$1"
    request GET "/containers/$name/logs" 2>/dev/null | python3 -c '
import json
import sys

try:
    print(json.load(sys.stdin).get("output", ""), end="")
except (json.JSONDecodeError, AttributeError):
    pass
'
}

wait_for_logs() {
    name="$1"
    pattern="$2"

    attempt=0
    while [ "$attempt" -lt 100 ]; do
        output=$(container_logs "$name")
        printf '%s' "$output" | grep -q "$pattern" && {
            printf '%s' "$output"
            return 0
        }
        sleep 0.1
        attempt=$((attempt + 1))
    done

    printf '%s' "$output"
    return 1
}

result() {
    description="$1"