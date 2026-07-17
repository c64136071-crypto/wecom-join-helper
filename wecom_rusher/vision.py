from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TemplateMatch:
    x: int
    y: int
    score: float
    scale: float
    width: int
    height: int


def _array(image: Any):
    try:
        import numpy as np
    except ImportError:
        raise RuntimeError("vision matching requires numpy; install requirements.txt") from None

    if hasattr(image, "convert"):
        return np.asarray(image.convert("RGB"))
    if isinstance(image, (str, bytes)):
        import cv2

        loaded = cv2.imread(image if isinstance(image, str) else image.decode())
        if loaded is None:
            raise ValueError(f"could not read image: {image!r}")
        return loaded
    return np.asarray(image)


def locate_template(image: Any, template: Any, threshold: float) -> tuple[int, int] | None:
    """Return the center point of the best match, or None below threshold."""
    matches = locate_templates_multiscale(image, template, threshold, scales=(1.0,))
    if not matches:
        return None
    return matches[0].x, matches[0].y


def locate_templates_multiscale(
    image: Any,
    template: Any,
    threshold: float,
    scales: tuple[float, ...] = (0.75, 0.9, 1.0, 1.1, 1.25, 1.5),
) -> list[TemplateMatch]:
    """Return non-overlapping template matches across common display scales."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError("vision matching requires opencv-python; install requirements.txt") from None

    source = _array(image)
    needle = _array(template)
    if source.ndim == 3:
        source = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
    if needle.ndim == 3:
        needle = cv2.cvtColor(needle, cv2.COLOR_RGB2GRAY)
    candidates: list[TemplateMatch] = []
    for scale in scales:
        width = max(1, round(needle.shape[1] * scale))
        height = max(1, round(needle.shape[0] * scale))
        if height > source.shape[0] or width > source.shape[1]:
            continue
        resized = cv2.resize(needle, (width, height), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        result = cv2.matchTemplate(source, resized, cv2.TM_CCOEFF_NORMED)
        rows, columns = np.where(result >= threshold)
        for row, column in zip(rows.tolist(), columns.tolist()):
            candidates.append(
                TemplateMatch(
                    column + width // 2,
                    row + height // 2,
                    float(result[row, column]),
                    scale,
                    width,
                    height,
                )
            )

    selected: list[TemplateMatch] = []
    for candidate in sorted(candidates, key=lambda match: match.score, reverse=True):
        if any(
            abs(candidate.x - existing.x) < max(candidate.width, existing.width) * 0.5
            and abs(candidate.y - existing.y) < max(candidate.height, existing.height) * 0.5
            for existing in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= 20:
            break
    return selected


def image_signature(image: Any) -> bytes:
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError("image signatures require opencv-python and numpy") from None

    array = _array(image)
    if array.ndim == 3:
        array = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(array, (32, 8), interpolation=cv2.INTER_AREA)
    bits = (small > float(small.mean())).astype(np.uint8).reshape(-1)
    return np.packbits(bits).tobytes()


def signature_distance(first: bytes, second: bytes) -> int:
    if len(first) != len(second):
        raise ValueError("image signatures must have equal length")
    return sum((left ^ right).bit_count() for left, right in zip(first, second))


def image_fingerprint(image: Any) -> str:
    """Create a stable fingerprint for a captured card image."""
    array = _array(image)
    return hashlib.sha256(array.tobytes() + repr(array.shape).encode("ascii")).hexdigest()
