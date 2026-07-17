# Compatibility

UI automation compatibility is evidence-based. A blank cell means the
configuration has not been verified, not that it is known to fail.

## Verified Environment

| Date | Windows | WeCom | Display | Window modes | Result |
| --- | --- | --- | --- | --- | --- |
| 2026-07-17 | Build 26200 | 5.0.9.6060 | 3840 x 2160 high-DPI desktop | Large and compact | OCR recognition and one authorized live submission passed |

The authorized live check produced one insertion and one terminal success. The
process stopped without a second polling cycle. Frozen OCR was also verified
from a path containing spaces and Chinese characters.

## Not Yet Verified

- Windows 10 and Windows on ARM.
- WeCom versions other than the one listed above.
- Multi-monitor layouts with mixed DPI values.
- Screen readers, high-contrast themes, and non-Chinese WeCom UI languages.
- Cards whose visual structure differs from the bundled generic templates.

When reporting compatibility, provide only product versions, resolution, DPI,
and synthetic reproductions. Do not upload a real group screenshot or log that
contains company information.
