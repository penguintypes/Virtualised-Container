# vcontainer: 6 Core Test Cases

**Purpose:** Verify vcontainer core functionality end-to-end
**Environment:** WSL2 Ubuntu or bare-metal Linux
**Time required:** ~15 minutes
**Status:** Can run in parallel with feature development

---

## TEST SET B: Sample Containers

### B1: Blog Container Execution
**What we're testing:** Blog image builds and can execute filesystem commands

**Setup (one time):**
```bash
curl -X POST http://localhost:8080/images/build -d '{"file": "samples/blog/Vcfile"}' -H "Content-Type: application/json"
# Expected output: JSON with image details
```

**Test B1:**
```bash
curl -X POST http://localhost:8080/containers -d '{"name": "blog-demo", "image": "blog", "command": "/bin/cat var/www/index.html"}' -H "Content-Type: application/json"
```

**Expected output:**
```json
{"id": "<container-id>", "status": "running", ...}
```

**Verify logs contain HTML:**
```bash
curl -s http://localhost:8080/containers/blog-demo/logs | grep -o "<!DOCTYPE html>"
```

**Cleanup:**
```bash
curl -X DELETE http://localhost:8080/containers/blog-demo
```

**Pass criteria:** ✓ Container created with blog image
✓ Command executed inside container (cat ran)
✓ Logs show HTML file contents
✓ Container deleted successfully

---

### B2: Runner Container (Python Execution)
**What we're testing:** Runner image has Python interpreter and can execute code

**Setup (one time):**
```bash
curl -X POST http://localhost:8080/images/build -d '{"file": "samples/runner/Vcfile"}' -H "Content-Type: application/json"
```

**Test B2:**
```bash
curl -X POST http://localhost:8080/containers -d '{"name": "runner-test", "image": "runner", "command": "python3 -c \"print('runner works')\""}' -H "Content-Type: application/json"
```

**Verify logs contain output:**
```bash
curl -s http://localhost:8080/containers/runner-test/logs
```
*Expected: "runner works"*

**Inspect container:**
```bash
curl -s http://localhost:8080/containers/runner-test | grep exit_code
```
*Expected: "exit_code": 0*

**Cleanup:**
```bash
curl -X DELETE http://localhost:8080/containers/runner-test
```

---

## TEST SET C: Dashboard Integration

### C1: Create via API → View in Dashboard → Stop via Dashboard

**What we're testing:** API and dashboard are in sync; actions work in both directions

**Terminal 1: Ensure system is running**
```bash
bash start.sh
```

**Step 1: Create container via API**
```bash
curl -X POST http://localhost:8080/containers -d '{"name": "c1", "image": "blog", "command": "/bin/sh -c \"sleep 30\""}' -H "Content-Type: application/json"
```

**Step 2: Verify container is running via API**
```bash
curl -s http://localhost:8080/containers | grep -o '"name": "c1"'
```

**Step 3: View in dashboard**
Open browser: `http://localhost:8080`
*Expected: "c1" is listed, status badge is green (running), memory/processes visible.*

**Step 4: Stop via dashboard**
On the `c1` card, click the `Stop` button.
*Expected: Status changes to exited (gray).*

**Step 5: Verify stop via API**
```bash
curl -s http://localhost:8080/containers | grep '"status"'
```

**Step 6: Cleanup**
```bash
curl -X DELETE http://localhost:8080/containers/c1
```

---

## TEST SET A: Process Isolation

### A1: File I/O Isolation
**What we're testing:** Files written inside a container don't appear on the host filesystem

**Test A1:**
```bash
curl -X POST http://localhost:8080/containers -d '{"name": "w1", "image": "blog", "command": "/bin/sh -c \"echo hello > /tmp/test.txt && cat /tmp/test.txt\""}' -H "Content-Type: application/json"
```

**Step 1: Check container logs**
```bash
curl -s http://localhost:8080/containers/w1/logs
```
*Expected: "hello"*

**Step 2: Check host filesystem**
```bash
ls /tmp/test.txt
```
*Expected: ls: cannot access '/tmp/test.txt': No such file or directory*

**Step 3: Cleanup**
```bash
curl -X DELETE http://localhost:8080/containers/w1
```

---

### A2: Namespace Isolation (Hostname)
**What we're testing:** Each container gets its own hostname (UTS namespace)

**Test A2:**
```bash
curl -X POST http://localhost:8080/containers -d '{"name": "iso1", "image": "blog", "command": "/bin/hostname"}' -H "Content-Type: application/json"
curl -X POST http://localhost:8080/containers -d '{"name": "iso2", "image": "blog", "command": "/bin/hostname"}' -H "Content-Type: application/json"
```

**Check hostnames:**
```bash
curl -s http://localhost:8080/containers/iso1/logs
curl -s http://localhost:8080/containers/iso2/logs
```
*Expected: "iso1" and "iso2"*

**Verify host hostname is different:**
```bash
hostname
```

**Cleanup:**
```bash
curl -X DELETE http://localhost:8080/containers/iso1
curl -X DELETE http://localhost:8080/containers/iso2
```

**⚠️ Expected to FAIL on WSL2 (Known Limitation):**
`iso1` and `iso2` may both show the host's hostname. WSL2 sandboxing prevents full unprivileged namespace isolation.

---

## Running All Tests in Sequence (~5 min)

```bash
# Ensure system is running
bash start.sh

# B1
curl -X POST http://localhost:8080/images/build -d '{"file": "samples/blog/Vcfile"}' -H "Content-Type: application/json"
curl -X POST http://localhost:8080/containers -d '{"name": "blog-demo", "image": "blog", "command": "/bin/cat var/www/index.html"}' -H "Content-Type: application/json"
curl -s http://localhost:8080/containers/blog-demo/logs
curl -X DELETE http://localhost:8080/containers/blog-demo

# B2
curl -X POST http://localhost:8080/images/build -d '{"file": "samples/runner/Vcfile"}' -H "Content-Type: application/json"
curl -X POST http://localhost:8080/containers -d '{"name": "runner-test", "image": "runner", "command": "python3 -c \"print('runner works')\""}' -H "Content-Type: application/json"
curl -s http://localhost:8080/containers/runner-test/logs
curl -X DELETE http://localhost:8080/containers/runner-test

# C1 (open browser to http://localhost:8080 during this test)
curl -X POST http://localhost:8080/containers -d '{"name": "c1", "image": "blog", "command": "/bin/sh -c \"sleep 30\""}' -H "Content-Type: application/json"
# [Dashboard: click Stop]
curl -X DELETE http://localhost:8080/containers/c1

# A1
curl -X POST http://localhost:8080/containers -d '{"name": "w1", "image": "blog", "command": "/bin/sh -c \"echo hello > /tmp/test.txt && cat /tmp/test.txt\""}' -H "Content-Type: application/json"
curl -s http://localhost:8080/containers/w1/logs
ls /tmp/test.txt
curl -X DELETE http://localhost:8080/containers/w1

# A2
curl -X POST http://localhost:8080/containers -d '{"name": "iso1", "image": "blog", "command": "/bin/hostname"}' -H "Content-Type: application/json"
curl -X POST http://localhost:8080/containers -d '{"name": "iso2", "image": "blog", "command": "/bin/hostname"}' -H "Content-Type: application/json"
curl -s http://localhost:8080/containers/iso1/logs
curl -s http://localhost:8080/containers/iso2/logs
curl -X DELETE http://localhost:8080/containers/iso1
curl -X DELETE http://localhost:8080/containers/iso2
```

---
*Last updated: 2026-10-24*
