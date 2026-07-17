import tempfile
import unittest
from pathlib import Path

from wecom_rusher.logging_utils import redact_message, setup_file_logger


class LoggingUtilsTests(unittest.TestCase):
    def test_redacts_title_group_and_name_fields(self):
        message = (
            "OCR title: 7月16日下午茶接龙登记; "
            "group=研发一部; name=张三; fingerprint=abc123"
        )
        redacted = redact_message(message)
        self.assertNotIn("7月16", redacted)
        self.assertNotIn("研发一部", redacted)
        self.assertNotIn("张三", redacted)
        self.assertIn("fingerprint=abc123", redacted)

    def test_file_logger_redacts_formatted_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "join-helper.log"
            logger = setup_file_logger(path, logger_name="redaction-test")
            logger.info("group=%s; status=%s", "研发一部", "waiting")
            for handler in logger.handlers:
                handler.flush()
            contents = path.read_text(encoding="utf-8")
            self.assertNotIn("研发一部", contents)
            self.assertIn("status=waiting", contents)
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
