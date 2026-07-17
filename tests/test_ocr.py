import unittest

from wecom_rusher.ocr import OCRReader, keyword_matches, normalize_ocr_text


class FakeEngine:
    def __call__(self, image):
        return (
            [
                [[[0, 0], [10, 0], [10, 10], [0, 10]], "7月16日", 0.99],
                [[[12, 0], [50, 0], [50, 10], [12, 10]], "下午茶 接龙登记", 0.98],
            ],
            [0.01, 0.01, 0.01],
        )


class OCRTests(unittest.TestCase):
    def test_normalization_removes_spacing_and_punctuation(self):
        self.assertEqual(
            normalize_ocr_text("7 月 16 日：下午茶，接龙登记"),
            "7月16日下午茶接龙登记",
        )

    def test_keyword_match_uses_normalized_text(self):
        self.assertTrue(keyword_matches("7月16日 下午茶接龙登记", "下午 茶"))
        self.assertFalse(keyword_matches("团建报名接龙", "下午茶"))

    def test_reader_combines_detected_lines(self):
        reader = OCRReader(engine=FakeEngine())
        self.assertEqual(reader.read(object()), "7月16日下午茶接龙登记")
