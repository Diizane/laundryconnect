"""Loader for recorded provider response fixtures (see fixtures/providers/README.md)."""

import json
from pathlib import Path
from typing import Any

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "providers"


def load_provider_fixture(provider_id: str, name: str) -> Any:
    """Load `fixtures/providers/<provider_id>/<name>.json`."""
    path = FIXTURES_ROOT / provider_id / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"No recorded fixture {name!r} for provider {provider_id!r} at {path}"
        )
    return json.loads(path.read_text())
