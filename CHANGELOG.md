# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.9] - 2026-09-30

### Fixed

- Restore recognition of the current WeCom card rendering at the fractional
  display scale used by high-DPI Windows desktops.
- Match the lower-contrast **Participate** button only after pairing it with
  the yellow sign-up icon and confirming the configured title keyword.
- Remove the unsafe icon-only click-coordinate fallback.

## [1.0.8] - 2026-08-27

### Fixed

- Recognize keyword-matching join cards from their yellow icon when the
  **Participate** button rendering no longer matches the bundled template.
- Ignore mouse-transparent desktop overlays, including the NVIDIA overlay,
  when deciding whether another application covers WeCom.

## [1.0.7] - 2026-08-27

### Fixed

- Continue scanning immediately after restoring WeCom from behind another
  application. This avoids a transient foreground-state check incorrectly
  pausing monitoring just after WeCom is brought forward.

## [1.0.6] - 2026-08-13

### Fixed

- Ignore WeCom-owned overlays during z-order visibility checks, preventing a
  false obstruction from stopping every card scan.
- Bring WeCom forward immediately after **Start**, then only return it to the
  foreground when an external application actually covers it.
- Pause scanning while Join Helper itself is active, so its **Stop** button can
  be used without the application taking focus back.

## [1.0.5] - 2026-07-30

### Changed

- Open the desktop app idle and require an explicit Start after every Stop or
  relaunch.
- Focus WeCom only once when monitoring starts, pause scans while its window is
  obscured, and keep fully visible split-screen layouts usable.
- Removed the mandatory recognition-test activation flow.
- Keep monitoring after a previously processed card is seen.

### Fixed

- Match both `下午茶` and `午茶` with the default title filter.
- Preload DPI-sensitive automation support before creating the Tk window to
  prevent the initial window-size jump on scaled displays.

## [1.0.4] - 2026-07-21

### Fixed

- Allowed `WeMail.exe` only for strictly titled WeCom document windows, fixing
  join documents that stopped being recognized after the process allowlist was
  introduced while keeping browser and mail windows out of chat discovery.

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
