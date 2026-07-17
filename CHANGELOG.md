# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.3] - 2026-07-17

### Fixed

- Restricted window discovery to the real `WXWork.exe` and `WXWorkWeb.exe`
  processes so browser tabs and WeCom Mail windows cannot steal focus merely
  because their titles contain `WeCom`.

## [1.0.2] - 2026-07-17

### Changed

- Kept the desktop window open after a successful join so the user can start a
  later monitoring run manually.
- Preserved per-card deduplication and the one-attempt boundary within each
  monitoring run.

## [1.0.1] - 2026-07-17

### Fixed

- Prevented blue document links and grayscale list regions from being mistaken
  for the filled confirmation button during post-submission verification.
- Kept the fail-closed one-attempt boundary while correctly recognizing the
  saved document state after the join button reappears.

## [1.0.0] - 2026-07-17

### Added

- Safe first-run recognition test and explicit live-mode activation.
- Per-user and portable settings paths with atomic UTF-8 persistence.
- Post-attempt terminal state and redacted rotating diagnostics.
- Reproducible portable and installer builds with SHA-256 checksums.
- Frozen OpenCV, RapidOCR, ONNX Runtime, and model smoke test.
- Windows GitHub Actions tests and draft release workflow.
- English-first public documentation and synthetic demonstration media.

## [0.9.0] - 2026-07-17

### Added

- Open-source repository hygiene, security policy, and contribution guidance.
- Verified one-attempt WeCom join workflow with OCR title filtering.

## [0.1.0] - 2026-07-17

### Added

- Initial private prototype and successful authorized live submission test.
