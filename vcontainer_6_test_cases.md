# vcontainer: Core Test Cases

Verifies the runtime end-to-end through the REST API. Tested on WSL2 Ubuntu 26.04.

**Prerequisites:** `./start.sh` running (dashboard on :8080), images `alpine`, `blog`, `runner` already built. No rebuild or download is needed.

## Run all cases with one command

```bash
bash tests/rest_cases.sh
```

Expected: six `PASS` lines, then `RESULT 6/6 passed`. Takes about 1 minute and cleans up after itself.

## Notes that apply to every case

- `command` is a JSON list: `["/bin/cat","/opt/index.html"]`. A plain string is also accepted and split like a shell would.
- Container status values are `running` and `stopped`.
- The blog page is at `/opt/index.html` inside the image.

## B1: Blog image runs a command

```bash
curl -s -X POST http://localhost:8080/containers -H "Content-Type: application/json" -d '{"name":"blog-demo","image":"blog","command":["/bin/cat","/opt/index.html"]}'
sleep 3; curl -s http://localhost:8080/containers/blog-demo/logs | grep -io 'doctype html'
curl -s -X DELETE http://localhost:8080/containers/blog-demo
```

Pass: logs contain `doctype html`; container deleted.

## B2: Runner image runs Python

```bash
curl -s -X POST http://localhost:8080/containers -H "Content-Type: application/json" -d @- <<'JSON'
{"name":"runner-test","image":"runner","command":["python3","-c","print('runner works')"]}
JSON
sleep 3; curl -s http://localhost:8080/containers/runner-test/logs
curl -s -X DELETE http://localhost:8080/containers/runner-test
```

Pass: logs show `runner works`; the container list shows status `stopped`.

## C1: API and dashboard stay in sync

```bash
curl -s -X POST http://localhost:8080/containers -H "Content-Type: application/json" -d '{"name":"c1","image":"blog","command":["/bin/sh","-c","sleep 120"]}'
```

1. Open http://localhost:8080. Card `c1` shows `running`.
2. Click Stop on the card. The badge changes to `stopped` and a Start button appears.
3. Check the API:

```bash
curl -s http://localhost:8080/containers | grep -o '"name": "c1", "image": "blog", "status": "[a-z]*"'
curl -s -X DELETE http://localhost:8080/containers/c1
```

Pass: API reports `stopped` after the dashboard Stop. Delete also works on a running container (it stops it first).

## C2: Memory limit is enforced

```bash
curl -s -X POST http://localhost:8080/containers -H "Content-Type: application/json" -d @- <<'JSON'
{"name":"c2","image":"runner","memory":"128M","command":["python3","-c","x=b'a'*(300*1024*1024);print('survived')"]}
JSON
sleep 6; curl -s http://localhost:8080/containers/c2/logs
curl -s -X DELETE http://localhost:8080/containers/c2
```

Pass: logs do not contain `survived` (the kernel killed the process at 128 MB). The container list shows `stopped`. Swap is disabled for limited containers (`memory.swap.max` = 0), otherwise WSL2 pushes the excess to swap and the process survives.

## A1: File isolation

```bash
rm -f /tmp/test.txt
curl -s -X POST http://localhost:8080/containers -H "Content-Type: application/json" -d '{"name":"w1","image":"blog","command":["/bin/sh","-c","echo hello > /tmp/test.txt && cat /tmp/test.txt"]}'
sleep 3; curl -s http://localhost:8080/containers/w1/logs
ls /tmp/test.txt
curl -s -X DELETE http://localhost:8080/containers/w1
```

Pass: logs show `hello`; `ls` reports `No such file or directory` on the host.

## A2: Hostname isolation (UTS namespace)

```bash
for n in iso1 iso2; do curl -s -X POST http://localhost:8080/containers -H "Content-Type: application/json" -d "{\"name\":\"$n\",\"image\":\"blog\",\"command\":[\"/bin/hostname\"]}"; done
sleep 3; curl -s http://localhost:8080/containers/iso1/logs; curl -s http://localhost:8080/containers/iso2/logs
hostname
for n in iso1 iso2; do curl -s -X DELETE http://localhost:8080/containers/$n; done
```

Pass: logs show `iso1` and `iso2`; the host prints its own different name. This passes on the tested WSL2 setup.

## Troubleshooting

- `Address already in use :8080`: another dashboard is running. Stop it with Ctrl+C in its terminal, then run `./start.sh`.
- Blog or runner ports refuse connections after a stop: click Start on the card; the port forwarder is recreated.
- Do not put `!` inside double-quoted shell strings; bash history expansion breaks them. Use single quotes.

*Last updated: 2026-10-25*
