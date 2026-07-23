"""Isolated PDF extraction worker (ADR 0011).

The in-process extraction timeout is cooperative and cannot interrupt a
hung `page.extract_text()` call (ADR 0010). This module provides the hard
guarantee required before processing untrusted or provider-supplied files:

- the child process (`python -m app.documents.worker`) runs extraction and
  applies OS resource limits to itself (address-space and CPU caps,
  best-effort on macOS, enforced on Linux — our container platform);
- the async parent (`extract_pages_isolated`) enforces a WALL-CLOCK timeout
  and kills the child outright if it exceeds it — a hung page cannot hang
  the service.

The child communicates one JSON object on stdout:
    {"ok": true, "pages": [{"text": ..., "truncated": ...}, ...]}
    {"ok": false, "reason": "<ExtractionFailure>", "detail": "..."}
Anything else (crash, OOM-kill, garbage output) is reported as a typed
`ExtractionError` by the parent — raw failures never escape.
"""

import argparse
import asyncio
import json
import logging
import os
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
# Child address-space cap. Worst-case materialisation is ~60 MB of text
# (ADR 0010); 1 GiB leaves room for pypdf parsing structures with a hard
# ceiling against runaway allocation.
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
    args = parser.parse_args()

    limits = (
        ExtractionLimits(**json.loads(args.limits_json)) if args.limits_json else ExtractionLimits()
    )
    _apply_child_resource_limits(cpu_seconds=int(limits.max_seconds) + 60)

    # Test-only hook: simulates a hung extraction so the parent's hard kill
    # is verifiable. Ignored unless explicitly set in the environment.
    hang = float(os.environ.get("LC_EXTRACTION_TEST_HANG_SECONDS", "0") or "0")
    if hang > 0:  # pragma: no cover - exercised via the parent-kill test
        import time

        time.sleep(hang)

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


async def extract_pages_isolated(
    pdf_path: Path,
    limits: ExtractionLimits | None = None,
    hard_timeout_seconds: float | None = None,
) -> list[ExtractedPage]:
    """Run extraction in a killable child process with a hard wall-clock cap.

    Raises `ExtractionError` for every failure mode: the child's typed
    errors are re-raised as-is; a hung child is killed and reported as
    TIMEOUT; a crashed child (non-zero exit, OOM-kill, bad output) is
    reported as UNREADABLE.
    """
    limits = limits or ExtractionLimits()
    deadline = hard_timeout_seconds or (limits.max_seconds + HARD_TIMEOUT_GRACE_SECONDS)

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.documents.worker",
        str(pdf_path),
        "--limits-json",
        json.dumps(limits.__dict__),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=_SERVICE_ROOT,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=deadline)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise ExtractionError(
            ExtractionFailure.TIMEOUT,
            f"worker exceeded hard wall-clock limit of {deadline}s and was killed",
        ) from None

    if process.returncode != 0:
        logger.warning(
            "extraction worker crashed",
            extra={"exit_code": process.returncode, "file": pdf_path.name},
        )
        raise ExtractionError(
            ExtractionFailure.UNREADABLE,
            f"extraction worker exited with code {process.returncode}",
        )

    try:
        result = json.loads(stdout.decode())
        if result["ok"]:
            return [
                ExtractedPage(text=page["text"], truncated=page["truncated"])
                for page in result["pages"]
            ]
        reason = ExtractionFailure(result["reason"])
        detail = str(result["detail"])
    except ExtractionError:
        raise
    except (json.JSONDecodeError, KeyError, ValueError, UnicodeDecodeError) as exc:
        logger.warning(
            "extraction worker returned invalid output",
            extra={"file": pdf_path.name, "error": type(exc).__name__},
        )
        raise ExtractionError(
            ExtractionFailure.UNREADABLE, "extraction worker returned invalid output"
        ) from exc
    raise ExtractionError(reason, detail)


if __name__ == "__main__":
    sys.exit(_worker_main())
