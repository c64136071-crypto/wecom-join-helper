from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from .ocr import OCRReader, keyword_matches
from .ui import TemplateStore
from .vision import locate_templates_multiscale


def run_smoke_test(
    app_root: str | Path,
    *,
    result_path: str | Path | None = None,
    ocr_reader: Any | None = None,
) -> dict[str, Any]:
    root = Path(app_root)
    store = TemplateStore(root / "templates")
    templates = {name: store.load(name) for name in store.required_names()}

    yellow_icon = templates["yellow_icon"]
    vision_match = bool(
        locate_templates_multiscale(yellow_icon, yellow_icon, threshold=0.99)
    )

    fixture_path = root / "assets" / "smoke" / "ocr-title.png"
    fixture = Image.open(fixture_path).convert("RGB")
    reader = ocr_reader or OCRReader()
    ocr_text = reader.read(fixture)
    ocr_match = keyword_matches(ocr_text, "下午茶")

    result = {
        "status": "SMOKE_TEST_OK" if vision_match and ocr_match else "SMOKE_TEST_FAILED",
        "templates_loaded": len(templates),
        "vision_match": vision_match,
        "ocr_keyword_match": ocr_match,
    }
    if result_path is not None:
        target = Path(result_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(result, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
    if result["status"] != "SMOKE_TEST_OK":
        raise RuntimeError("frozen smoke test failed")
    return result
