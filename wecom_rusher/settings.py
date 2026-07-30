from __future__ import annotations

from dataclasses import replace

from .config import Config


def needs_first_run(config: Config) -> bool:
    return False


def mark_recognition_test_passed(config: Config) -> Config:
    return replace(config, dry_run=True, recognition_test_passed=True)


def activate_live_mode(config: Config) -> Config:
    return replace(
        config,
        dry_run=False,
        setup_complete=True,
        recognition_test_passed=True,
    )


def update_keyword(config: Config, keyword: str) -> Config:
    clean = keyword.strip()
    if not clean:
        raise ValueError("title keyword must not be empty")
    return replace(
        config,
        title_keyword=clean,
    )
