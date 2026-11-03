import http
import sys
from pathlib import Path

ROOT_DIRECTORY = str(Path(__file__).resolve().parent)
PYTHON_SOURCE = str(Path(ROOT_DIRECTORY) / "src")
if PYTHON_SOURCE not in sys.path:
    sys.path.insert(0, PYTHON_SOURCE)

from vcontainer_cli.cli import *  # noqa: E402,F403
from vcontainer_cli.cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        OSError,
        http.client.HTTPException,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"vcontainer: {error}", file=sys.stderr)
        sys.exit(1)
