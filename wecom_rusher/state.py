from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SubmissionState:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.submitted: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        try:
            payload: Any = json.loads(self.path.read_text(encoding="utf-8"))
            submitted = payload.get("submitted", {})
            if isinstance(submitted, dict):
                self.submitted = {
                    str(key): value
                    for key, value in submitted.items()
                    if isinstance(value, dict)
                }
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            self.submitted = {}

    def seen(self, fingerprint: str) -> bool:
        return fingerprint in self.submitted

    def record(self, fingerprint: str, title: str) -> None:
        self.submitted[fingerprint] = {
            "title": title,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"submitted": self.submitted}
        fd, temp_name = tempfile.mkstemp(prefix=f"{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
