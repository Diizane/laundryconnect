"""Isolated PDF extraction worker (ADR 0011).

The in-process extraction timeout is cooperative and cannot interrupt a
hung `page.extract_text()` call (ADR 0010). This module provides the hard
guarantee required before processing untrusted or provider-supplied files:

- the child process (`python -m app.documents.worker`) runs extraction and
  applies OS resource limits to itself (address-space and CPU caps,
  best-effort on macOS, enforced on Linux — our container platform);
- the async parent (`extract_pages_isolated`) enforces a WALL-CLOCK timeout
  and guarantees child cleanup on EVERY abnormal exit — timeout, asyncio
  cancellation, or unexpected parent errors. A hung page cannot hang the
  service and no orphan/zombie extraction process is left behind.

Protocol: the child writes one JSON object on stdout —
    {"ok": true, "pages": [{"text": ..., "truncated": ...}, ...]}
    {"ok": false, "reason": "<ExtractionFailure>", "detail": "..."}
The parent validates the structure strictly (`_parse_worker_output`);
anything malformed — wrong types, null pages, unknown reasons, non-JSON,
crashes, OOM-kills — becomes a typed `ExtractionError(UNREADABLE)`. Raw
exceptions never escape. Unexpected extra fields are deliberately ignored
(forward compatibility).

This single-object protocol is only suitable within the aggregate
`max_total_text_chars` bound, because the document text is duplicated
across the process boundary (child strings → JSON → parent bytes → parsed
objects). For manuals beyond that bound the future path is streamed NDJSON
or a temporary result file plus staged storage (ADR 0010/0011) — not a
larger cap.
"""

import argparse
import asyncio
import contextlib
import json
import logging
import sys
from pathlib import Path

from app.documents.extraction import (
    ExtractedPage,
    ExtractionError,
    ExtractionFailure,
    ExtractionLimits,
    extract_page_texts,
)

logger = logging.getLogger(__name__)

# Wall-clock budget for the whole child process: the cooperative limit plus
# grace for interpreter startup and JSON serialisation.
HARD_TIMEOUT_GRACE_SECONDS = 30.0
# Child address-space cap. Worst-case materialisation is bounded by
# max_total_text_chars (ADR 0011); 1 GiB leaves room for pypdf parsing
# structures with a hard ceiling against runaway allocation.
WORKER_MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024

_SERVICE_ROOT = Path(__file__).resolve().parents[2]


def _apply_child_resource_limits(cpu_seconds: int) -> None:
    """Limit this process's address space and CPU time (best effort).

    macOS ignores or rejects some rlimits; failures are logged to stderr and
    tolerated there. Production containers are Linux, where these hold.
    """
    import resource

    for limit, value in (
        (resource.RLIMIT_AS, WORKER_MEMORY_LIMIT_BYTES),
        (resource.RLIMIT_CPU, cpu_seconds),
    ):
        try:
            resource.setrlimit(limit, (value, value))
        except (OSError, ValueError) as exc:  # pragma: no cover - platform dependent
            print(f"worker rlimit not applied: {exc}", file=sys.stderr)


def _worker_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--limits-json", default=None)
    # Test-only: simulates a hung extraction so the parent's kill paths are
    # verifiable. Never set outside tests; deliberately NOT read from the
    # environment so a stray service variable cannot stall extractions.
    parser.add_argument("--test-hang-seconds", type=float, default=0.0)
    args = parser.parse_args()

    limits = (
        ExtractionLimits(**json.loads(args.limits_json)) if args.limits_json else ExtractionLimits()
    )
    _apply_child_resource_limits(cpu_seconds=int(limits.max_seconds) + 60)

    if args.test_hang_seconds > 0:  # pragma: no cover - exercised via kill tests
        import time

        time.sleep(args.test_hang_seconds)

    try:
        pages = [
            {"text": page.text, "truncated": page.truncated}
            for page in extract_page_texts(args.pdf_path, limits)
        ]
    except ExtractionError as error:
        print(json.dumps({"ok": False, "reason": error.reason.value, "detail": error.detail}))
        return 0
    print(json.dumps({"ok": True, "pages": pages}))
    return 0


def _malformed(detail: str) -> ExtractionError:
    return ExtractionError(ExtractionFailure.UNREADABLE, f"invalid worker output: {detail}")


def _parse_worker_output(raw: bytes) -> list[ExtractedPage]:
    """Strictly validate the worker protocol; malformed output of ANY shape
    becomes ExtractionError(UNREADABLE), a valid failure object re-raises
    its typed reason."""
    try:
        data = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _malformed("not valid JSON") from exc

    if not isinstance(data, dict):
        raise _malformed("top level is not an object")
    ok = data.get("ok")
    if not isinstance(ok, bool):
        raise _malformed("'ok' is not a boolean")

    if ok:
        pages = data.get("pages")
        if not isinstance(pages, list):
            raise _malformed("'pages' is not a list")
        parsed: list[ExtractedPage] = []
        for index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                raise _malformed(f"page {index} is not an object")
            text = page.get("text")
            truncated = page.get("truncated")
            if not isinstance(text, str):
                raise _malformed(f"page {index} 'text' is not a string")
            if not isinstance(truncated, bool):
                raise _malformed(f"page {index} 'truncated' is not a boolean")
            parsed.append(ExtractedPage(text=text, truncated=truncated))
        return parsed

    reason_raw = data.get("reason")
    detail = data.get("detail")
    if not isinstance(reason_raw, str):
        raise _malformed("'reason' is not a string")
    if not isinstance(detail, str):
        raise _malformed("'detail' is not a string")
    try:
        reason = ExtractionFailure(reason_raw)
    except ValueError as exc:
        raise _malformed(f"unknown failure reason {reason_raw!r}") from exc
    raise ExtractionError(reason, detail)


async def extract_pages_isolated(
    pdf_path: Path,
    limits: ExtractionLimits | None = None,
    hard_timeout_seconds: float | None = None,
    _test_hang_seconds: float = 0.0,
) -> list[ExtractedPage]:
    """Run extraction in a killable child process with a hard wall-clock cap.

    Cleanup guarantee: on timeout, asyncio cancellation, or any unexpected
    parent error, the child is killed and reaped before this coroutine
    exits — `CancelledError` is re-raised unchanged. Typed `ExtractionError`
    covers every failure mode (child's own typed errors round-trip; a hung
    child becomes TIMEOUT; crashes and malformed output become UNREADABLE).

    `_test_hang_seconds` is a test-only hook forwarded as an explicit child
    argument; it is never read from the environment.
    """
    limits = limits or ExtractionLimits()
    deadline = hard_timeout_seconds or (limits.max_seconds + HARD_TIMEOUT_GRACE_SECONDS)

    argv = [
        sys.executable,
        "-m",
        "app.documents.worker",
        str(pdf_path),
        "--limits-json",
        json.dumps(limits.__dict__),
    ]
    if _test_hang_seconds > 0:
        argv += ["--test-hang-seconds", str(_test_hang_seconds)]

    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=_SERVICE_ROOT,
    )
    try:
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=deadline)
        except TimeoutError:
            raise ExtractionError(
                ExtractionFailure.TIMEOUT,
                f"worker exceeded hard wall-clock limit of {deadline}s and was killed",
            ) from None
    finally:
        # Runs on every abnormal exit: timeout, CancelledError, unexpected
        # errors. Kill if still running, then reap so no zombie remains.
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(asyncio.CancelledError):
                await process.wait()

    if process.returncode != 0:
        logger.warning(
            "extraction worker crashed",
            extra={"exit_code": process.returncode, "file": pdf_path.name},
        )
        raise ExtractionError(
            ExtractionFailure.UNREADABLE,
            f"extraction worker exited with code {process.returncode}",
        )

    return _parse_worker_output(stdout)


if __name__ == "__main__":
    sys.exit(_worker_main())
