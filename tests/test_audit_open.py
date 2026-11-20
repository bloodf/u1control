"""OrcaSlicer audits every "open" a plugin makes. Two kinds carry no path, so its permission prompt can only say
"This operation does not expose a target the audit hook can display" (seen when activating the plugin, GUI test
2026-11-20): a file object opened on a descriptor (os.fdopen), and the bytecode-cache write of a module first
imported inside the plugin's scope, that is, an import inside a function (importlib.resources does that too on its
first use). The package imports what it needs at load, which OrcaSlicer runs outside the plugin's scope."""

import ast
import glob
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "u1control")


def pathless_opens(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    found = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found += ["import in %s()" % fn.name for node in ast.walk(fn) if isinstance(node, (ast.Import, ast.ImportFrom))]
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "fdopen":
            found.append("os.fdopen")
        if (isinstance(node, ast.ImportFrom) and node.module == "importlib" and any(a.name == "resources" for a in node.names)
                or isinstance(node, ast.Import) and any(a.name.startswith("importlib.resources") for a in node.names)):
            found.append("importlib.resources")
    return ["%s: %s" % (os.path.basename(path), f) for f in found]


class NoOpenWithoutAPath(unittest.TestCase):
    def test_modules_open_files_by_path_and_import_at_load(self):
        paths = glob.glob(os.path.join(SRC, "*.py"))
        self.assertTrue(paths)
        self.assertEqual([f for p in sorted(paths) for f in pathless_opens(p)], [])


if __name__ == "__main__":
    unittest.main()
