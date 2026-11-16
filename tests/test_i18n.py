"""Texts Python writes (errors, notices, the agent's Print dialog progress) in English, Portuguese, Spanish,
German and Simplified Chinese: every text has every language with the same placeholders, and the language
follows the user's choice, then OrcaSlicer's, then English."""

import ast
import os
import re
import sys
import types
import unittest
from unittest import mock
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "u1control")
sys.path[:0] = [SRC, os.path.join(ROOT, "tests")]

import fakes  # noqa: E402  (fake orca module)
import i18n  # noqa: E402

fakes.install_orca()
import plugin  # noqa: E402
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

    def test_top_cover_mode_is_named_in_the_language_in_use(self):
        i18n.use("de")
        self.assertEqual([plugin._cover_text(m) for m in ("strong", "weak", "keep-warm", "off")],
                         ["starke Kühlung", "schwache Kühlung", "warm halten", "wie beim Slicen festgelegt"])
        i18n.use("en")
        self.assertEqual(plugin._cover_text("keep-warm"), "keep warm")

    def check_connection(self, kind):
        client = types.SimpleNamespace(address="10.0.0.9", info=None, query=None)
        answers = iter([({}, {}), [{"index": 0, "loaded": False}]])
        with mock.patch.object(plugin, "use_language"), mock.patch.object(plugin, "_selected_u1", return_value=client), \
                mock.patch.object(plugin, "run_off_thread", side_effect=lambda fn: next(answers)), \
                mock.patch.object(plugin.u1, "detect_firmware", return_value={"kind": kind, "version": "1.2.3"}):
            return plugin.CheckConnection().execute().message

    def test_firmware_is_named_whole_never_stock(self):
        i18n.use("es")
        self.assertEqual(self.check_connection("stock"), "U1 en 10.0.0.9 (firmware oficial 1.2.3). T1 vacío")
        self.assertEqual(self.check_connection("extended"), "U1 en 10.0.0.9 (Extended Firmware 1.2.3). T1 vacío")
        i18n.use("en")
        self.assertEqual(self.check_connection("stock"), "U1 at 10.0.0.9 (official firmware 1.2.3). T1 empty")
        for langs in MESSAGES.values():
            for text in langs.values():
                self.assertNotIn("stock", text.lower().replace("stock-", ""))


if __name__ == "__main__":
    unittest.main()
