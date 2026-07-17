from __future__ import annotations

from dataclasses import replace

from .config import Config


def needs_first_run(config: Config) -> bool:
    return not config.setup_complete or config.dry_run


def mark_recognition_test_passed(config: Config) -> Config:
    return replace(config, dry_run=True, recognition_test_passed=True)


def activate_live_mode(config: Config) -> Config:
    if not config.recognition_test_passed:
        raise ValueError("a successful recognition test is required")
    return replace(config, dry_run=False, setup_complete=True)


def update_keyword(config: Config, keyword: str) -> Config:
    clean = keyword.strip()
    if not clean:
        raise ValueError("title keyword must not be empty")
    return replace(
        config,
        title_keyword=clean,
        dry_run=True,
        setup_complete=False,
        recognition_test_passed=False,
    )
