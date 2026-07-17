import tempfile
import unittest
from pathlib import Path

from wecom_rusher.paths import AppPaths


class AppPathsTests(unittest.TestCase):
    def test_installed_mode_uses_local_app_data(self):
        paths = AppPaths.resolve(
            Path(r"D:\Apps\JoinHelper"),
            portable=False,
            local_app_data=Path(r"C:\Users\Test\AppData\Local"),
        )
        self.assertEqual(
            paths.data_dir,
            Path(r"C:\Users\Test\AppData\Local\WeComJoinHelper"),
        )
        self.assertEqual(paths.config_path, paths.data_dir / "config.json")
        self.assertEqual(paths.templates_dir, Path(r"D:\Apps\JoinHelper\templates"))
        self.assertFalse(paths.portable)

    def test_portable_mode_keeps_mutable_data_beside_app(self):
        paths = AppPaths.resolve(Path(r"D:\Portable\JoinHelper"), portable=True)
        self.assertEqual(paths.data_dir, Path(r"D:\Portable\JoinHelper\data"))
        self.assertEqual(paths.state_path, paths.data_dir / "state.json")
        self.assertEqual(paths.log_path, paths.data_dir / "join-helper.log")
        self.assertTrue(paths.portable)

    def test_ensure_creates_only_mutable_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            app_root = Path(directory) / "app"
            paths = AppPaths.resolve(app_root, portable=True)
            paths.ensure()
            self.assertTrue(paths.data_dir.is_dir())
            self.assertFalse(paths.templates_dir.exists())


if __name__ == "__main__":
    unittest.main()
