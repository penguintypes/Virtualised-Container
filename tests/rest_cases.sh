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

container_exit_code() {
    name="$1"
    request GET "/containers/$name" 2>/dev/null | python3 -c '
import json
import sys

try:
    value = json.load(sys.stdin).get("exit_code")
    print("" if value is None else value)
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
    outcome="$2"

    if [ "$outcome" = "pass" ]; then
        echo "PASS $description"
        PASSED=$((PASSED + 1))
    else
        echo "FAIL $description"
        FAILED=$((FAILED + 1))
    fi
}

if ! request GET /health >/dev/null; then
    echo "Vcontainer API is not available at $API_URL" >&2
    echo "Start vcontainer-api.service and run this test again." >&2
    exit 1
fi

if ! request GET /images | python3 -c '
import json
import os
import sys

images = json.load(sys.stdin).get("images", [])
wanted = os.environ.get("VCONTAINER_TEST_IMAGE", "alpine")
raise SystemExit(0 if any(item.get("name") == wanted for item in images) else 1)
'; then
    echo "Test image '$IMAGE' is not installed." >&2
    echo "Pull it before running this script." >&2
    exit 1
fi

cleanup_container rest-echo
request POST /containers \
    "{\"name\":\"rest-echo\",\"image\":\"$IMAGE\",\"command\":[\"/bin/echo\",\"rest-api-works\"]}" \
    >/dev/null
if wait_for_status rest-echo stopped &&
   wait_for_logs rest-echo rest-api-works >/dev/null; then
    result "create, execute, record logs and exit" pass
else
    result "create, execute, record logs and exit" fail
fi
cleanup_container rest-echo

cleanup_container rest-life
request POST /containers \
    "{\"name\":\"rest-life\",\"image\":\"$IMAGE\",\"command\":[\"/bin/sleep\",\"120\"]}" \
    >/dev/null
if wait_for_status rest-life running &&
   request POST /containers/rest-life/stop >/dev/null &&
   wait_for_status rest-life stopped &&
   request POST /containers/rest-life/start >/dev/null &&
   wait_for_status rest-life running; then
    result "create, stop and restart lifecycle" pass
else
    result "create, stop and restart lifecycle" fail
fi
cleanup_container rest-life

cleanup_container rest-env
request POST /containers \
    "{\"name\":\"rest-env\",\"image\":\"$IMAGE\",\"environment\":{\"VCONTAINER_TEST\":\"environment-works\"},\"command\":[\"/bin/sh\",\"-c\",\"printf %s \\\"\$VCONTAINER_TEST\\\"\"]}" \
    >/dev/null
if wait_for_status rest-env stopped &&
   wait_for_logs rest-env environment-works >/dev/null; then
    result "environment variables reach the container" pass
else
    result "environment variables reach the container" fail
fi
cleanup_container rest-env

rm -f /tmp/vcontainer-rest-isolation
cleanup_container rest-file
request POST /containers \
    "{\"name\":\"rest-file\",\"image\":\"$IMAGE\",\"command\":[\"/bin/sh\",\"-c\",\"echo isolated > /tmp/vcontainer-rest-isolation; cat /tmp/vcontainer-rest-isolation\"]}" \
    >/dev/null
if wait_for_status rest-file stopped &&
   wait_for_logs rest-file isolated >/dev/null &&
   [ ! -e /tmp/vcontainer-rest-isolation ]; then
    result "container root filesystem is isolated" pass
else
    result "container root filesystem is isolated" fail
fi
cleanup_container rest-file

cleanup_container rest-host-one
cleanup_container rest-host-two
request POST /containers \
    "{\"name\":\"rest-host-one\",\"image\":\"$IMAGE\",\"hostname\":\"rest-host-one\",\"command\":[\"/bin/hostname\"]}" \
    >/dev/null
request POST /containers \
    "{\"name\":\"rest-host-two\",\"image\":\"$IMAGE\",\"hostname\":\"rest-host-two\",\"command\":[\"/bin/hostname\"]}" \
    >/dev/null
if wait_for_status rest-host-one stopped &&
   wait_for_status rest-host-two stopped &&
   wait_for_logs rest-host-one rest-host-one >/dev/null &&
   wait_for_logs rest-host-two rest-host-two >/dev/null; then
    result "containers have independent hostnames" pass
else
    result "containers have independent hostnames" fail
fi
cleanup_container rest-host-one
cleanup_container rest-host-two

cleanup_container rest-memory
request POST /containers \
    "{\"name\":\"rest-memory\",\"image\":\"$IMAGE\",\"memory_max\":\"32M\",\"command\":[\"/bin/sh\",\"-c\",\"exec awk 'BEGIN { value=\\\"x\\\"; while (1) value=value value }'\"]}" \
    >/dev/null
if wait_for_status rest-memory stopped; then
    exit_code=$(container_exit_code rest-memory)
    if [ "$exit_code" = 137 ]; then
        result "memory limit terminates an excessive allocation" pass
    else
        result "memory limit terminates an excessive allocation" fail
    fi
else
    result "memory limit terminates an excessive allocation" fail
fi
cleanup_container rest-memory

cleanup_container rest-delete
request POST /containers \
    "{\"name\":\"rest-delete\",\"image\":\"$IMAGE\",\"command\":[\"/bin/sleep\",\"120\"]}" \
    >/dev/null
if wait_for_status rest-delete running &&
   request DELETE /containers/rest-delete >/dev/null &&
   ! request GET /containers/rest-delete >/dev/null 2>&1; then
    result "delete stops and removes a running container" pass
else
    result "delete stops and removes a running container" fail
    cleanup_container rest-delete
fi

cleanup_container rest-devices
request POST /containers \
    "{\"name\":\"rest-devices\",\"image\":\"$IMAGE\",\"command\":[\"/bin/sh\",\"-c\",\"test -c /dev/null && test -c /dev/full && test -c /dev/tty && test -d /dev/pts && test -e /dev/ptmx && test -d /dev/shm && test -d /dev/mqueue && test -e /dev/fd/0 && grep -q '^Seccomp:[[:space:]]*2' /proc/self/status && echo runtime-filesystems-ok\"]}" \
    >/dev/null
if wait_for_status rest-devices stopped &&
   wait_for_logs rest-devices runtime-filesystems-ok >/dev/null; then
    result "standard devices, runtime filesystems and seccomp are active" pass
else
    result "standard devices, runtime filesystems and seccomp are active" fail
fi
cleanup_container rest-devices

echo "RESULT $PASSED/$((PASSED + FAILED)) passed"
[ "$FAILED" -eq 0 ]
