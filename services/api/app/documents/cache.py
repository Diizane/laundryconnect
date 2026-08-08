"""Disk-backed document cache (Milestone 12).

Documents the operator is already entitled to download are stored on the
server after first retrieval, so subsequent opens are instant and — the
bigger win — still work when the provider session has expired or the
provider is unreachable.

This is a **revalidating cache, not an archive**. Manuals get revised, and
a technician following a superseded procedure (torque figures, wiring,
fault codes) is a safety problem, not just a correctness one. So:

- every hit is revalidated against the provider with `If-None-Match` /
  `If-Modified-Since` — a cheap header-only round trip; 304 means serve the
  copy, 200 means the provider revised it and we replace ours;
- a copy is served WITHOUT revalidation only when the provider cannot be
  reached (expired session, outage), and the caller is told it is cached
  and how old it is so the technician can be shown that honestly;
- beyond `max_stale_seconds` without a successful revalidation, a copy is
  refused rather than silently trusted.

Storage is content-addressed by (provider, source path), size-capped with
least-recently-used eviction. Bodies never contain credentials; metadata
holds only HTTP validators and timestamps.
"""

import contextlib
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedDocument:
    body: bytes
    etag: str | None
    last_modified: str | None
    stored_at: float
    revalidated_at: float

    def age_seconds(self, now: float) -> float:
        """Time since we last confirmed this copy is current."""
        return max(0.0, now - self.revalidated_at)


class DocumentCache:
    """Content-addressed document store with LRU eviction."""

    def __init__(
        self,
        root: Path,
        *,
        max_bytes: int,
        now=time.time,
    ) -> None:
        self._root = Path(root)
        self._max_bytes = max_bytes
        self._now = now
        self._root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(provider_id: str, source_path: str) -> str:
        digest = hashlib.sha256(f"{provider_id}\0{source_path}".encode()).hexdigest()
        return digest

    def _paths(self, key: str) -> tuple[Path, Path]:
        shard = self._root / key[:2]
        return shard / f"{key}.bin", shard / f"{key}.json"

    def _index_path(self, key: str) -> Path:
        return self._root / key[:2] / f"{key}.index.json"

    def get_index(self, key: str) -> dict | None:
        """The derived search/contents index for a cached document, if it
        has been built. Derived data: a miss simply means rebuild."""
        try:
            return json.loads(self._index_path(key).read_text())
        except (OSError, ValueError):
            return None

    def put_index(self, key: str, index: dict) -> None:
        path = self._index_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(index))
        os.chmod(path, 0o600)

    def get(self, key: str) -> CachedDocument | None:
        body_path, meta_path = self._paths(key)
        try:
            meta = json.loads(meta_path.read_text())
            body = body_path.read_bytes()
        except (OSError, ValueError):
            return None
        try:
            return CachedDocument(
                body=body,
                etag=meta.get("etag"),
                last_modified=meta.get("last_modified"),
                stored_at=float(meta["stored_at"]),
                revalidated_at=float(meta.get("revalidated_at", meta["stored_at"])),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def put(
        self,
        key: str,
        body: bytes,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        body_path, meta_path = self._paths(key)
        body_path.parent.mkdir(parents=True, exist_ok=True)
        now = self._now()
        # Write body then metadata: a torn write leaves metadata missing,
        # which `get` treats as a miss rather than as corrupt data.
        body_path.write_bytes(body)
        meta_path.write_text(
            json.dumps(
                {
                    "etag": etag,
                    "last_modified": last_modified,
                    "stored_at": now,
                    "revalidated_at": now,
                    "bytes": len(body),
                }
            )
        )
        os.chmod(body_path, 0o600)
        os.chmod(meta_path, 0o600)
        self._evict_if_needed()

    def mark_revalidated(self, key: str) -> None:
        """Record that the provider confirmed this copy is still current."""
        _, meta_path = self._paths(key)
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError):
            return
        meta["revalidated_at"] = self._now()
        with contextlib.suppress(OSError):
            meta_path.write_text(json.dumps(meta))

    def total_bytes(self) -> int:
        return sum(p.stat().st_size for p in self._root.rglob("*.bin") if p.is_file())

    def _evict_if_needed(self) -> None:
        entries = [p for p in self._root.rglob("*.bin") if p.is_file()]
        total = sum(p.stat().st_size for p in entries)
        if total <= self._max_bytes:
            return
        # Least recently *used*: access time, refreshed on every read.
        entries.sort(key=lambda p: p.stat().st_atime)
        for path in entries:
            if total <= self._max_bytes:
                break
            size = path.stat().st_size
            meta = path.with_suffix(".json")
            index = path.parent / f"{path.stem}.index.json"
            for target in (path, meta, index):
                with contextlib.suppress(OSError):
                    target.unlink()
            total -= size
            logger.info("document cache evicted an entry", extra={"freed_bytes": size})
