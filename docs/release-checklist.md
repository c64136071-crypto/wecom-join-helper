# Release Checklist

## v1.0.3 Evidence

- Public tree excludes runtime config, state, logs, caches, and real screenshots.
- Four published templates were manually inspected and contain no personal or
  company information.
- New users start in recognition-test mode with live mode disabled.
- Test recognition sends no mouse input and exits after one matching candidate.
- The runner records an explicit post-attempt state and cannot retry from it.
- Dynamic title, group, and name fields are redacted from file logs.
- Portable build is verified from a path containing spaces and Chinese text.
- Frozen smoke test loads four templates, OpenCV, RapidOCR, ONNX Runtime, and
  all three OCR models against a synthetic title fixture.
- Installer smoke test covers silent per-user installation, frozen OCR, standard
  uninstall, and absence of remaining program processes.
- Release workflows use Windows runners and pin third-party actions to commit
  SHAs.
- Public documentation states unofficial status, authorization requirements,
  safety boundaries, limitations, and verified compatibility.

## Measured Local Results

| Evidence | Result |
| --- | --- |
| Automated tests | 76 passed |
| Authorized live check | One insertion, one terminal success, no retry |
| Verified environment | Windows build 26200, WeCom 5.0.9.6060 |
| Portable v1.0.3 ZIP | 96.80 MB, SHA-256 verified |
| Installer v1.0.3 | 68.88 MB, SHA-256 verified |
| Installer lifecycle | Install, frozen smoke, uninstall passed |

The final artifacts were rebuilt from the reviewed release tree. Their checksum
sidecars are stored beside the files in the release output directory. GitHub
publication occurs only after the full tracked tree and repository history are
scanned for private data.
