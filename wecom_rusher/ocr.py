from __future__ import annotations

import unicodedata
from typing import Any


def normalize_ocr_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(char for char in normalized if char.isalnum())


def keyword_matches(text: str, keyword: str) -> bool:
    clean_text = normalize_ocr_text(text)
    aliases = (normalize_ocr_text(alias) for alias in keyword.split("|"))
    return any(alias and alias in clean_text for alias in aliases)


class OCRReader:
    def __init__(self, engine: Any | None = None):
        self._engine = engine

    def _get_engine(self) -> Any:
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError:
                raise RuntimeError("Chinese OCR is not installed; run setup again") from None
            self._engine = RapidOCR()
        return self._engine

    def read(self, image: Any) -> str:
        payload = image
        if hasattr(image, "convert"):
            import numpy as np

            payload = np.asarray(image.convert("RGB"))
        output = self._get_engine()(payload)
        result = output[0] if isinstance(output, tuple) else output
        if not result:
            return ""
        lines = [str(item[1]) for item in result if isinstance(item, (list, tuple)) and len(item) >= 2]
        return normalize_ocr_text("".join(lines))
