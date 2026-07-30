import unittest

from wecom_rusher.config import Config
from wecom_rusher.settings import (
    activate_live_mode,
    mark_recognition_test_passed,
    needs_first_run,
    update_keyword,
)


class SettingsTests(unittest.TestCase):
    def test_new_config_does_not_require_first_run_gate(self):
        self.assertFalse(needs_first_run(Config(dry_run=True, setup_complete=False)))

    def test_live_mode_does_not_require_recognition_test(self):
        activated = activate_live_mode(
            Config(dry_run=True, setup_complete=False, recognition_test_passed=False)
        )
        self.assertFalse(activated.dry_run)
        self.assertTrue(activated.setup_complete)

    def test_successful_test_allows_live_mode(self):
        tested = mark_recognition_test_passed(Config(dry_run=True))
        activated = activate_live_mode(tested)
        self.assertTrue(activated.setup_complete)
        self.assertTrue(activated.recognition_test_passed)
        self.assertFalse(activated.dry_run)

    def test_changing_keyword_keeps_live_mode_ready(self):
        config = Config(
            title_keyword="下午茶",
            dry_run=False,
            setup_complete=True,
            recognition_test_passed=True,
        )
        updated = update_keyword(config, "团建")
        self.assertEqual(updated.title_keyword, "团建")
        self.assertFalse(updated.dry_run)
        self.assertTrue(updated.setup_complete)
        self.assertTrue(updated.recognition_test_passed)


if __name__ == "__main__":
    unittest.main()
