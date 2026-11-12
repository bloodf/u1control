"""The built wheel: expected files, valid RECORD, metadata, and no dynamic code execution."""

import ast
import base64
import hashlib
import re
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402

PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
DIST_INFO = "u1control-%s.dist-info/" % PROJECT["version"]
EXPECTED = {"u1control/%s.py" % n for n in ("__init__", "_assets") + build.MODULES} | {
    DIST_INFO + n for n in ("METADATA", "WHEEL", "RECORD", "top_level.txt", "licenses/LICENSE", "licenses/PrimeUIX.txt",
                            "licenses/PrimeVue.txt", "licenses/Vue.txt")}
FORBIDDEN = re.compile(r"\bexec\(|\beval\(|__import__|importlib")
DYNAMIC_BUILTINS = {"exec", "eval", "compile", "__import__"}


class WheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = build.build(out_dir=Path(tempfile.mkdtemp()))
        cls.zip = zipfile.ZipFile(cls.path)
        cls.addClassCleanup(cls.zip.close)

    def read(self, name):
        return self.zip.read(name).decode("utf-8")

    def test_exact_file_list(self):
        self.assertEqual(set(self.zip.namelist()), EXPECTED)
        self.assertEqual(len(self.zip.namelist()), len(EXPECTED))

    def test_record_hashes_and_sizes(self):
        rows = {}
        for line in self.read(DIST_INFO + "RECORD").splitlines():
            name, digest, size = line.rsplit(",", 2)
            rows[name] = (digest, size)
        self.assertEqual(set(rows), EXPECTED)
        self.assertEqual(rows[DIST_INFO + "RECORD"], ("", ""))
        for name in EXPECTED - {DIST_INFO + "RECORD"}:
            data = self.zip.read(name)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            self.assertEqual(rows[name], ("sha256=" + digest, str(len(data))), name)

    def test_metadata_and_wheel_files(self):
        meta = dict(line.split(": ", 1) for line in self.read(DIST_INFO + "METADATA").splitlines() if ": " in line)
        self.assertEqual(meta["Name"], "u1control")
        self.assertEqual(meta["Version"], PROJECT["version"])
        self.assertEqual(meta["Summary"], PROJECT["description"])
        self.assertEqual(meta["Author"], PROJECT["authors"][0]["name"])
        self.assertEqual(meta["License"], PROJECT["license"])
        self.assertNotIn("Requires-Dist", self.read(DIST_INFO + "METADATA"))
        wheel = self.read(DIST_INFO + "WHEEL")
        for line in ("Wheel-Version: 1.0", "Root-Is-Purelib: true", "Tag: py3-none-any"):
            self.assertIn(line, wheel.splitlines())
        self.assertIn("Generator:", wheel)
        self.assertEqual(self.read(DIST_INFO + "top_level.txt").strip(), "u1control")

    def test_licenses_travel_with_the_wheel(self):
        """Our LICENSE and the notices of the bundled Vue, PrimeVue and PrimeUIX, byte for byte."""
        self.assertEqual(self.zip.read(DIST_INFO + "licenses/LICENSE"), (ROOT / "LICENSE").read_bytes())
        shared = sorted((ROOT / "ui" / "shared" / "licenses").glob("*.txt"))
        self.assertEqual({f.name for f in shared}, {"PrimeUIX.txt", "PrimeVue.txt", "Vue.txt"})
        for f in shared:
            self.assertEqual(self.zip.read(DIST_INFO + "licenses/" + f.name), f.read_bytes())

    def test_version_matches_pyproject(self):
        self.assertIn("VERSION = %r" % PROJECT["version"], self.read("u1control/__init__.py"))

    def test_no_dynamic_execution(self):
        for name in (n for n in EXPECTED if n.endswith(".py")):
            text = self.read(name)
            self.assertIsNone(FORBIDDEN.search(text), name)
            for node in ast.walk(ast.parse(text)):   # builtin compile()/exec()/eval() calls; re.compile is fine
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, DYNAMIC_BUILTINS, name)

    def test_reproducible(self):
        again = build.build(out_dir=Path(tempfile.mkdtemp()))
        self.assertEqual(again.read_bytes(), self.path.read_bytes())

    def test_sha256sums(self):
        line = (self.path.parent / "SHA256SUMS").read_text("utf-8").strip()
        self.assertEqual(line, "%s  u1control_any.whl" % hashlib.sha256(self.path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
