from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, fields, replace
from datetime import time
from pathlib import Path
from typing import Any


def _parse_time(value: str, field_name: str) -> time:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
        return time(hour, minute)
    except (ValueError, AttributeError):
        raise ValueError(f"{field_name} must use HH:MM format") from None


@dataclass(frozen=True)
class Config:
    title_keyword: str = "下午茶"
    window_title_keyword: str = "企业微信|WeCom"
    document_window_title_keyword: str = "企业微信-文档"
    run_weekdays: tuple[int, ...] = ()
    normal_interval_seconds: float = 5.0
    rush_interval_seconds: float = 0.5
    rush_start: time = time(11, 0)
    rush_end: time = time(12, 0)
    match_threshold: float = 0.88
    action_timeout_seconds: float = 8.0
    dry_run: bool = True
    setup_complete: bool = False
    recognition_test_passed: bool = False
    stop_after_submission: bool = True
    templates_dir: Path = Path("templates")
    state_path: Path = Path("state.json")
    log_path: Path = Path("wecom-rusher.log")

    @classmethod
    def defaults(cls) -> "Config":
        return cls()

    @classmethod
    def from_json(cls, path: str | Path) -> "Config":
        raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
        values = {field.name: raw[field.name] for field in fields(cls) if field.name in raw}
        for name in ("templates_dir", "state_path", "log_path"):
            if name in values:
                values[name] = Path(values[name])
        for name in ("rush_start", "rush_end"):
            if name in values:
                values[name] = _parse_time(values[name], name)
        if "run_weekdays" in values:
            values["run_weekdays"] = tuple(values["run_weekdays"])
        config = cls(**values)
        config.validate()
        return config

    @classmethod
    def load_or_create(
        cls,
        path: str | Path,
        defaults: "Config | None" = None,
    ) -> "Config":
        target = Path(path)
        if target.exists():
            return cls.from_json(target)
        config = defaults or cls.defaults()
        config.validate()
        config.write_json(target)
        return config

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field in fields(self):
            if field.name in {"templates_dir", "state_path", "log_path"}:
                continue
            value = getattr(self, field.name)
            if isinstance(value, Path):
                payload[field.name] = str(value)
            elif isinstance(value, time):
                payload[field.name] = value.strftime("%H:%M")
            elif isinstance(value, tuple):
                payload[field.name] = list(value)
            else:
                payload[field.name] = value
        return payload

    def write_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f"{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def with_runtime_paths(
        self,
        *,
        templates_dir: str | Path,
        state_path: str | Path,
        log_path: str | Path,
    ) -> "Config":
        return replace(
            self,
            templates_dir=Path(templates_dir),
            state_path=Path(state_path),
            log_path=Path(log_path),
        )

    def validate(self) -> None:
        if not self.title_keyword.strip():
            raise ValueError("title_keyword must not be empty")
        if self.normal_interval_seconds <= 0:
            raise ValueError("normal_interval_seconds must be positive")
        if self.rush_interval_seconds <= 0:
            raise ValueError("rush_interval_seconds must be positive")
        if self.action_timeout_seconds <= 0:
            raise ValueError("action_timeout_seconds must be positive")
        if not 0 < self.match_threshold <= 1:
            raise ValueError("match_threshold must be in (0, 1]")
        if self.rush_start >= self.rush_end:
            raise ValueError("rush_start must be before rush_end")
        if any(day not in range(7) for day in self.run_weekdays):
            raise ValueError("run_weekdays must contain weekday numbers from 0 to 6")
