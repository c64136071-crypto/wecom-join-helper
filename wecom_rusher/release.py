from __future__ import annotations

import re


_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


def release_filenames(version: str) -> tuple[str, str]:
    if not _VERSION.fullmatch(version):
        raise ValueError("version must follow semantic versioning")
    return (
        f"JoinHelper-Portable-v{version}.zip",
        f"JoinHelper-Setup-v{version}.exe",
    )
