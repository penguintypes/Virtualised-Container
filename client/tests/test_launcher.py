"""Launcher contract checks; these do not invoke WSL."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "vcontainer.py"
sys.path.insert(0, str(PATH.parent / "src"))

from vcontainer_cli import cli as launcher  # noqa: E402


class LauncherTests(unittest.TestCase):
    def test_one_process_preserves_arguments_and_exit_code(self):
        arguments = [
            "exec",
            "demo",
            "--",
            "/bin/echo",
            "hello world",
            'a"b',
            "",
        ]
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys, "argv", [str(PATH), *arguments]),
            patch.object(launcher.subprocess, "call", return_value=7) as call,
        ):
            self.assertEqual(launcher.main(), 7)
        call.assert_called_once_with(
            [
                "wsl.exe",
                "-d",
                "Ubuntu",
                "-u",
                "root",
                "--cd",
                str(PATH.parent),
                "--exec",
                "env",
                "SUDO_USER=vcdev",
                "/opt/vcontainer/bin/vcontainer-cli",
                *arguments,
            ]
        )

    def test_configured_machine_and_user(self):
        with (
            patch.dict(
                os.environ,
                {
                    "VCONTAINER_WSL_DISTRO": "vcontainer-default-machine",
                    "VCONTAINER_WSL_USER": "alex",
                },
            ),
            patch.object(sys, "argv", [str(PATH), "help"]),
            patch.object(launcher.subprocess, "call", return_value=0) as call,
        ):
            self.assertEqual(launcher.main(), 0)
        command = call.call_args.args[0]
        self.assertEqual(command[2], "vcontainer-default-machine")
        self.assertIn("SUDO_USER=alex", command)

    def test_list_uses_backend(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys, "argv", [str(PATH), "list"]),
            patch.object(launcher, "list_images", return_value=0) as images,
            patch.object(launcher.subprocess, "call") as call,
        ):
            self.assertEqual(launcher.main(), 0)
        images.assert_called_once_with("Ubuntu")
        call.assert_not_called()

    def test_healthy_backend_does_not_launch_wsl(self):
        with (
            patch.object(launcher, "backend_ready", return_value=True),
            patch.object(launcher.subprocess, "run") as run,
        ):
            launcher.ensure_backend("Ubuntu")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
