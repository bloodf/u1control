"""Texts Python writes (errors, notices, the agent's Print dialog progress) in English, Portuguese, Spanish,
German and Simplified Chinese: every text has every language with the same placeholders, and the language
follows the user's choice, then OrcaSlicer's, then English."""

import ast
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "u1control")
sys.path[:0] = [SRC, os.path.join(ROOT, "tests")]

import fakes  # noqa: E402,F401  (fake orca module)
import i18n  # noqa: E402
import service  # noqa: E402
from i18n_text import MESSAGES  # noqa: E402

HOLES = re.compile(r"%[sd]|%\.\d+f|%\(\w+\)[sd]")


def tr_keys():
    """Every tr("...") in the sources, constants passed to tr() resolved by name."""
    keys, consts = set(), {}
    trees = [ast.parse(p.read_text(encoding="utf-8")) for p in Path(SRC).glob("*.py")]
    for tree in trees:
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        consts[t.id] = n.value.value
    for tree in trees:
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "tr" and n.args:
                a = n.args[0]
                if isinstance(a, ast.Constant):
                    keys.add(a.value)
                elif isinstance(a, ast.Name) and a.id in consts:
                    keys.add(consts[a.id])
    return keys


class Messages(unittest.TestCase):
    def tearDown(self):
        i18n.use("en")

    def test_every_text_has_every_language_with_the_same_placeholders(self):
        for key, langs in MESSAGES.items():
            self.assertEqual(set(langs), set(i18n.LANGUAGES) - {"en"}, key)
            for lang, text in langs.items():
                self.assertTrue(text.strip(), (lang, key))
                self.assertEqual(HOLES.findall(text), HOLES.findall(key), (lang, key, text))

    def test_every_text_python_shows_is_translated(self):
        missing = sorted(tr_keys() - set(MESSAGES))
        self.assertGreater(len(tr_keys()), 100)
        self.assertEqual(missing, [])

    def test_language_follows_choice_then_orcaslicer_then_english(self):
        self.assertEqual(i18n.resolve("de", "zh_CN"), "de")
        self.assertEqual(i18n.resolve("auto", "es_ES"), "es")
        self.assertEqual(i18n.resolve("auto", "zh_CN"), "zh-CN")
        self.assertEqual(i18n.resolve("auto", "zh_TW"), "zh-CN")
        self.assertEqual(i18n.resolve("auto", "pt_BR"), "pt-BR")
        self.assertEqual(i18n.resolve("auto", "fr_FR"), "en")
        self.assertEqual(i18n.resolve("auto", None), "en")
        self.assertEqual(i18n.resolve("xx", "de"), "de")
        self.assertIsNone(i18n.normalize("esperanto"))

    def test_tr_answers_in_the_language_in_use(self):
        i18n.use("de")
        self.assertEqual(i18n.tr("Print started"), "Druck gestartet")
        i18n.use("zh-CN")
        self.assertEqual(i18n.tr("Print started"), "打印已开始")
        self.assertEqual(i18n.tr("text from the printer"), "text from the printer")   # unknown: as given
        i18n.use("klingon")
        self.assertEqual(i18n.language(), "en")
        self.assertEqual(i18n.tr("Print started"), "Print started")

    def test_service_error_reaches_the_page_translated(self):
        i18n.use("es")
        pub = []
        svc = service.Service(pub.append, log=lambda m: None)
        self.addCleanup(svc.close)
        svc.submit(1, "connect", {}, gen=12345)
        self.assertEqual(pub[-1]["error"], MESSAGES[service.STALE]["es"])


if __name__ == "__main__":
    unittest.main()
