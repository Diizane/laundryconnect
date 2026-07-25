"""Operator-only live smoke test (run manually, never by CI or the service).

Performs the single, supervised first live interaction: ONE model search and
(optionally) ONE document retrieval — no indexing, no crawling, no background
discovery. Use it to pin the real search endpoint/response mapping and to
capture a response for a sanitised fixture.

Guardrails: refuses to run under CI, refuses unless the access record is
approved (`ALLIANCE_ACCESS_APPROVED=true`) with the kill switch off, and
requires a valid manually-bootstrapped session. Prints only non-sensitive
summaries — never cookies, tokens, URLs with query strings, or response
bodies.

    ALLIANCE_MODE=session \\
    ALLIANCE_ACCESS_APPROVED=true \\
    ALLIANCE_SESSION_PATH=~/.laundryconnect/alliance-session.json \\
    python -m app.providers.alliance.smoke_test SC60 [--document <url>]
"""

import argparse
import asyncio
import sys
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.providers.alliance.config import is_ci, require_live_allowed, resolve_mode
from app.providers.alliance.connector import AllianceConnector
from app.providers.models import ProviderResult, QueryType


def sanitise_reference(ref: str | None) -> str:
    """Return a log-safe form of a source reference.

    Drops query strings, fragments, and any userinfo — where signed URLs
    place tokens/signatures/session ids — leaving only host + path (for URL
    references) or the bare identifier (for non-URL references). Never
    returns credentials or signed parameters.
    """
    if not ref:
        return ""
    if "://" in ref:
        parts = urlsplit(ref)
        return f"{parts.hostname or ''}{parts.path}"
    # Non-URL reference: still strip any accidental query/fragment.
    return ref.split("?", 1)[0].split("#", 1)[0]


def result_summary(result: ProviderResult) -> str:
    """A one-line, sanitised summary safe to print to stdout."""
    return (
        f"{result.result_type.value}: {result.title} "
        f"[origin={result.data_origin.value}, ref={sanitise_reference(result.source_reference)}]"
    )


async def _run(model: str, document_url: str | None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)

    if is_ci():
        print("Refusing: CI must never run the live smoke test.", file=sys.stderr)  # noqa: T201
        return 2
    if resolve_mode(settings).value != "session":
        print("Refusing: set ALLIANCE_MODE=session.", file=sys.stderr)  # noqa: T201
        return 2
    try:
        # Same gate the connector uses: kill switch off, not CI, approved.
        require_live_allowed(settings)
    except Exception as exc:  # LiveModeRefused
        print(f"Refusing: {exc}", file=sys.stderr)  # noqa: T201
        return 2

    connector = AllianceConnector(settings=settings)

    print(f"[smoke] ONE search for model {model!r}…")  # noqa: T201
    results = await connector.search(model, QueryType.MODEL)
    print(f"[smoke] search returned {len(results)} result(s).")  # noqa: T201
    for result in results[:10]:
        # Sanitised summary only — no URLs with query strings/tokens.
        print(f"  - {result_summary(result)}")  # noqa: T201

    if document_url:
        transport = connector._build_session_transport()  # noqa: SLF001 - operator tool
        print("[smoke] ONE document retrieval…")  # noqa: T201
        content = await transport.fetch_document(document_url)
        print(f"[smoke] document retrieved: {len(content)} bytes.")  # noqa: T201

    print(  # noqa: T201
        "[smoke] Done. No indexing, crawling, or discovery performed. "
        "Sanitise and human-review any captured response before committing a fixture."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alliance live smoke test (operator only)")
    parser.add_argument("model", help="A single model number to search for, e.g. SC60")
    parser.add_argument("--document", default=None, help="Optional single document URL to retrieve")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.model, args.document))


if __name__ == "__main__":
    raise SystemExit(main())
