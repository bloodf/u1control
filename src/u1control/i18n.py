"""The language of the texts Python writes: errors, notices, and what OrcaSlicer's Print dialog shows for the
printer agent. Free of the `orca` module.

The English text is the key: tr("the U1 is busy (%s)") answers in the language in use, or the English itself when
there is no translation. Placeholders keep their order in every language (i18n_text.py; tests/test_i18n.py checks it).
The page's own texts are in ui/src/core/messages*.ts. Text the printer sends is never translated.
"""

from i18n_text import MESSAGES
from i18n_text_cs import FIRMWARE as FIRMWARE_CS

FIRMWARE = {"cs": FIRMWARE_CS}   # Extended Firmware texts (English from the printer); other languages keep the English

LANGUAGES = ("en", "pt-BR", "es", "de", "zh-CN", "pl", "cs")
_PREFIXES = (("pt", "pt-BR"), ("en", "en"), ("es", "es"), ("de", "de"), ("zh", "zh-CN"), ("pl", "pl"), ("cs", "cs"))   # zh_TW reads zh-CN too
_language = "en"


def normalize(code):
    """OrcaSlicer's or a browser's language code ("pt_BR", "de", "zh_CN", "pl_PL", "cs_CZ", "es-MX") -> one of LANGUAGES, or None."""
    if not isinstance(code, str):
        return None
    tag = code.strip().replace("_", "-").lower()
    return next((lang for prefix, lang in _PREFIXES if tag == prefix or tag.startswith(prefix + "-")), None)


def resolve(choice, host):
    """The user's explicit choice first, then OrcaSlicer's language, then English."""
    return choice if choice in LANGUAGES else normalize(host) or "en"


def use(language):
    global _language
    _language = language if language in LANGUAGES else "en"


def language():
    return _language


def tr(text):
    """`text` (English) in the language in use. Format the answer afterwards: tr("T%d is empty") % 2."""
    if _language == "en":
        return text
    langs = MESSAGES.get(text)
    return langs.get(_language, text) if langs else FIRMWARE.get(_language, {}).get(text, text)
