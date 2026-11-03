import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helper_package import EXPECTED_HELPERS, downloaded_helpers


def test_local_helpers_are_used_without_network(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Network download should not be used")

    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)

    with downloaded_helpers() as directory:
        discovered = {
            path.name for path in directory.iterdir() if path.is_file()
        }

    assert discovered.issuperset(EXPECTED_HELPERS)
