"""Download and verify the privileged WSL helper release."""

import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

HELPER_VERSION = "0.2.0"
HELPER_URL = (
    "https://github.com/NodyHody06/"
    "vcontainer-helper/releases/download/"
    f"v{HELPER_VERSION}/"
    f"vcontainer-helpers-v{HELPER_VERSION}.zip"
)
HELPER_SHA256 = (
    "21d510e2d1c75c7ce6d88df5e5795f5"
    "2c51b383928d31a4f1f03559c2874369e"
)
EXPECTED_HELPERS = {
    "vcontainer-read",
    "vcontainer-control",
    "vcontainer-image-control",
    "vcontainer-volume-control",
}
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024


@contextmanager
def downloaded_helpers():
    local = (
        Path(__file__).resolve().parent
        / "helper"
        / "vcontainer-helper"
        / "helpers"
    )
    if local.is_dir() and {
        path.name for path in local.iterdir() if path.is_file()
    }.issuperset(EXPECTED_HELPERS):
        print(f"Using local runtime helpers: {local}")
        yield local
        return

    temporary = Path(tempfile.mkdtemp(prefix="vcontainer-helpers-"))
    archive = temporary / "helpers.zip"
    extracted = temporary / "helpers"
    extracted.mkdir()

    try:
        print(f"Downloading runtime helpers v{HELPER_VERSION}...")
        request = urllib.request.Request(
            HELPER_URL,
            headers={"User-Agent": "Vcontainer-Installer"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > MAX_ARCHIVE_BYTES:
                raise RuntimeError("Runtime helper archive is too large")
            with archive.open("wb") as destination:
                shutil.copyfileobj(response, destination)

        if archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise RuntimeError("Runtime helper archive is too large")

        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest.lower() != HELPER_SHA256.lower():
            raise RuntimeError("Runtime helper checksum verification failed")

        discovered = set()
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                if member.is_dir():
                    continue
                member_path = Path(member.filename)
                name = member_path.name
                if name not in EXPECTED_HELPERS:
                    continue
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or name in discovered
                    or member.file_size > MAX_ARCHIVE_BYTES
                ):
                    raise RuntimeError(
                        f"Unexpected helper archive entry: {member.filename}"
                    )
                with (
                    package.open(member) as source,
                    (extracted / name).open("wb") as destination,
                ):
                    shutil.copyfileobj(source, destination)
                discovered.add(name)

        if discovered != EXPECTED_HELPERS:
            missing = ", ".join(sorted(EXPECTED_HELPERS - discovered))
            raise RuntimeError(f"Runtime helper package is incomplete: {missing}")

        yield extracted
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise RuntimeError(f"Could not prepare runtime helpers: {error}") from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
