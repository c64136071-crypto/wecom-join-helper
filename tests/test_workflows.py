import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class WorkflowTests(unittest.TestCase):
    def load(self, name):
        return yaml.load((WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    def test_test_workflow_runs_on_windows_for_push_and_pull_request(self):
        workflow = self.load("test.yml")
        self.assertIn("push", workflow["on"])
        self.assertIn("pull_request", workflow["on"])
        self.assertEqual(workflow["permissions"]["contents"], "read")
        self.assertEqual(workflow["jobs"]["tests"]["runs-on"], "windows-latest")

    def test_release_workflow_is_tag_only_and_can_write_releases(self):
        workflow = self.load("release.yml")
        self.assertEqual(workflow["on"]["push"]["tags"], ["v*"])
        self.assertEqual(workflow["permissions"]["contents"], "write")
        self.assertEqual(workflow["jobs"]["release"]["runs-on"], "windows-latest")

    def test_all_actions_are_pinned_to_commit_shas(self):
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            references = re.findall(r"uses:\s*[^\s@]+@([^\s#]+)", text)
            self.assertTrue(references, path.name)
            for reference in references:
                self.assertRegex(reference, r"^[0-9a-f]{40}$", path.name)


if __name__ == "__main__":
    unittest.main()
