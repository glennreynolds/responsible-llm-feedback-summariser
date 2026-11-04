"""Append-only, hash-chained audit log (JSON Lines).

Each record carries the hash of the previous record, so any edit, deletion or reordering
is detectable with `verify()`. It is tamper-evident, not tamper-proof: in production the
log would be shipped to write-once storage or a SIEM (e.g. Splunk) as well.
"""
from __future__ import annotations

import getpass
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _last_hash(self) -> str:
        if not self.path.exists():
            return GENESIS
        last = None
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line
        return json.loads(last)["hash"] if last else GENESIS

    def record(self, event: str, data: dict, actor: str | None = None) -> dict:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "actor": actor or getpass.getuser(),
            "data": data,
            "prev_hash": self._last_hash(),
        }
        rec["hash"] = _hash(rec)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def verify(self) -> tuple[bool, str]:
        if not self.path.exists():
            return True, "No audit log yet."
        prev = GENESIS
        with open(self.path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("prev_hash") != prev:
                    return False, f"Chain broken at line {i}: prev_hash does not match previous record."
                if _hash(rec) != rec.get("hash"):
                    return False, f"Record at line {i} has been modified."
                prev = rec["hash"]
        return True, "Audit log intact."
