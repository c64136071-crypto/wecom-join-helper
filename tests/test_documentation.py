import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_readme_contains_public_release_sections(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for heading in (
            "## Safety Boundary",
            "## Installation",
            "## Quick Start",
            "## How It Works",
            "## Limitations",
            "## Development",
            "## 中文快速开始",
        ):
            self.assertIn(heading, text)
        self.assertIn("unofficial", text.lower())
        self.assertIn("not affiliated", text.lower())

    def test_documentation_files_and_images_exist(self):
        for relative in (
            "docs/architecture.md",
            "docs/compatibility.md",
            "docs/troubleshooting.md",
            "docs/assets/join-helper-main.png",
            "docs/assets/join-helper-demo.gif",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

        markdown_files = [ROOT / "README.md", *ROOT.glob("docs/*.md")]
        for markdown in markdown_files:
            text = markdown.read_text(encoding="utf-8")
            for target in re.findall(r"!\[[^]]*]\(([^)]+)\)", text):
                if "://" in target:
                    continue
                self.assertTrue((markdown.parent / target).resolve().is_file(), target)

    def test_public_docs_contain_no_private_paths_or_bypass_claims(self):
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in [ROOT / "README.md", *ROOT.glob("docs/*.md")]
        ).lower()
        private_home = str(Path.home()).lower()
        self.assertNotIn(private_home, text)
        self.assertNotIn("bypass detection", text)
        self.assertNotIn("evade detection", text)
        self.assertNotIn("tbd", text)


if __name__ == "__main__":
    unittest.main()
