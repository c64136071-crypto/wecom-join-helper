import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_inno_setup_is_per_user_and_uninstallable(self):
        text = (ROOT / "installer" / "JoinHelper.iss").read_text(encoding="utf-8")
        self.assertIn("PrivilegesRequired=lowest", text)
        self.assertIn(r"DefaultDirName={localappdata}\Programs\WeComJoinHelper", text)
        self.assertIn(r"UninstallDisplayIcon={app}\JoinHelper.exe", text)
        self.assertIn("Name: \"desktopicon\"", text)
        self.assertIn(r"{autoprograms}\Join Helper", text)

    def test_installer_does_not_create_startup_or_services(self):
        text = (ROOT / "installer" / "JoinHelper.iss").read_text(encoding="utf-8").lower()
        self.assertNotIn("{userstartup}", text)
        self.assertNotIn("{commonstartup}", text)
        self.assertNotIn("create service", text)
        self.assertNotIn("deleteafterinstall", text)

    def test_installer_build_and_smoke_scripts_are_versioned(self):
        build = (ROOT / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "installer_smoke_test.ps1").read_text(encoding="utf-8")
        self.assertIn("JoinHelper-Setup-v$Version.exe", build)
        self.assertIn("ISCC.exe", build)
        self.assertIn("/VERYSILENT", smoke)
        self.assertIn("frozen_smoke_test.ps1", smoke)
        self.assertIn("unins000.exe", smoke)
        self.assertNotIn("Installed frozen smoke test failed", smoke)


if __name__ == "__main__":
    unittest.main()
