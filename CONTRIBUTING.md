# Contributing

## Development Setup

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Keep changes focused and add a failing test before changing runtime behavior.
Do not commit real group screenshots, user names, company information, runtime
logs, `config.json`, or `state.json`.

## Pull Requests

- Explain the user-visible behavior and safety impact.
- Include tests for new behavior and failure paths.
- Confirm test mode sends no mouse input.
- Confirm live mode cannot retry after an insertion attempt.
- Update documentation when compatibility or setup changes.

This project is unofficial and is not affiliated with WeCom or Tencent.
