import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class WorkflowSourceTests(unittest.TestCase):
    def test_source_archive_uses_only_explicit_inputs_with_hashes_and_no_overwrite(self):
        script = ROOT / 'scripts/build_workflow_source.py'
        self.assertTrue(script.is_file(), 'scoped source delivery builder is missing')
        spec = importlib.util.spec_from_file_location('scoped_builder', script)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input'
            for name in module.FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(('synthetic:' + name).encode())
            (source / 'current-desktop.png').write_bytes(b'PRIVATE-DO-NOT-READ')
            private = source / 'release-final-v1.0.9'
            private.mkdir()
            (private / 'secret.txt').write_bytes(b'PRIVATE-DO-NOT-READ')
            archive = root / 'candidate.zip'
            accessed = []
            read_bytes = Path.read_bytes
            def read(path):
                accessed.append(path.relative_to(source).as_posix())
                return read_bytes(path)
            with patch.object(Path, 'read_bytes', read):
                result = module.build(source, archive)
            self.assertEqual(set(accessed), set(module.FILES))
            with zipfile.ZipFile(archive) as package:
                manifest = json.loads(package.read('SOURCE-MANIFEST.json'))
                self.assertEqual(set(package.namelist()), set(module.FILES) | {'SOURCE-MANIFEST.json'})
                for name, sha in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(package.read(name)).hexdigest(), sha)
            self.assertEqual(result['kind'], 'source-launcher-not-exe-or-installer')
            old = archive.read_bytes()
            with self.assertRaises(FileExistsError):
                module.build(source, archive)
            self.assertEqual(archive.read_bytes(), old)
            (source / module.FILES[0]).unlink()
            with self.assertRaises(OSError):
                module.build(source, root / 'incomplete.zip')
            self.assertFalse((root / 'incomplete.zip').exists())


if __name__ == '__main__':
    unittest.main()
