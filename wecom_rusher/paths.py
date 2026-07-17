from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    app_root: Path
    data_dir: Path
    config_path: Path
    state_path: Path
    log_path: Path
    templates_dir: Path
    portable: bool

    @classmethod
    def resolve(
        cls,
        app_root: str | Path,
        *,
        portable: bool,
        local_app_data: str | Path | None = None,
    ) -> "AppPaths":
        root = Path(app_root)
        if portable:
            data_dir = root / "data"
        else:
            base = Path(local_app_data) if local_app_data is not None else _local_app_data()
            data_dir = base / "WeComJoinHelper"
        return cls(
            app_root=root,
            data_dir=data_dir,
            config_path=data_dir / "config.json",
            state_path=data_dir / "state.json",
            log_path=data_dir / "join-helper.log",
            templates_dir=root / "templates",
            portable=portable,
        )

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


def _local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value)
    return Path.home() / "AppData" / "Local"
