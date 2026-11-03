"""Integration checks: run with Windows Python after setup.py.

Creates uniquely named containers and removes only those test containers.
Pulls Alpine if it is absent from the persistent store.
"""

import subprocess
import sys
import uuid
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "vcontainer.py"


def cli(*args, success=True):
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(
        args,
        result.returncode,
        result.stdout.strip(),
        result.stderr.strip(),
        flush=True,
    )
    assert (result.returncode == 0) == success, result
    assert (
        "Arguments:" not in result.stdout and "Command:" not in result.stdout
    )
    assert "rm -f build/vcontainer" not in result.stdout
    assert "cc -iquote" not in result.stdout
    return result


def main():
    cli()
    assert "unknown command" in cli("not-a-command", success=False).stderr
    cli("stop", success=False)
    cli("stop", "missing", "123", success=False)
    cli("delete", success=False)
    if "alpine" not in cli("list").stdout:
        cli("pull", "alpine")
    token = "regression-" + uuid.uuid4().hex[:10]
    bad = token + "-bad"
    try:
        failed = cli(
            "run",
            "alpine",
            "--name",
            bad,
            "--detach",
            "--",
            "/bash/sh",
            success=False,
        )
        assert "started:" not in failed.stdout
        cli("stop", bad)
        cli("start", token, success=False)
        cli(
            "run",
            "alpine",
            "--name",
            token,
            "--detach",
            "--",
            "/bin/sleep",
            "300",
        )
        cli(
            "exec",
            token,
            "--",
            "/bin/sh",
            "-c",
            "echo preserved > /restart-check",
        )
        cli("start", token, success=False)
        listing = cli("ps").stdout
        assert (
            token in listing and "running" in listing and "COMMAND" in listing
        )
        cli("stop", token, "123", success=False)
        cli("stop", token)
        cli("stop", token)
        assert "status=stopped" in cli("inspect", token).stdout
        cli("start", token)
        assert (
            "preserved"
            in cli("exec", token, "--", "/bin/cat", "/restart-check").stdout
        )
        cli("stop", token)
        assert "alpine" in cli("list").stdout
    finally:
        for name in (token, bad):
            subprocess.run(
                [sys.executable, str(LAUNCHER), "stop", name], timeout=120
            )
            subprocess.run(
                [sys.executable, str(LAUNCHER), "rm", name], timeout=120
            )
    print("WSL regression checks passed", flush=True)


if __name__ == "__main__":
    main()
