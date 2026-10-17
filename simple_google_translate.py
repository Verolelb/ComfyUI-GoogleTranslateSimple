# Title: Simple Google Translate
# Desc : Minimal Google Translate nodes for ComfyUI.
#
# Design goals
# ------------
# * One single job: translate text with Google Translate.
# * No frontend JavaScript at all -> nothing that can slow down or hook the
#   Preview/Save image nodes.
# * No extra pip install: only `requests`, which ComfyUI already bundles.

from __future__ import annotations

import json
import os
import time

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Optional: if this environment variable is set, the official Google Cloud
# Translation API is used instead of the free web endpoint.
API_KEY_ENV = "GOOGLE_TRANSLATION_API_KEY"

# Max characters sent in a single request (Google shortens/refuses huge inputs).
MAX_CHUNK = 1800
# (connect, read) timeout in seconds.
REQUEST_TIMEOUT = (5, 25)
RETRIES = 2

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_AUTO = "auto"

# Google Translate language codes -> English name
GOOGLE_LANGUAGES = {
    "af": "afrikaans",
    "sq": "albanian",
    "am": "amharic",
    "ar": "arabic",
    "hy": "armenian",
    "as": "assamese",
    "ay": "aymara",
    "az": "azerbaijani",
    "bm": "bambara",
    "eu": "basque",
    "be": "belarusian",
    "bn": "bengali",
    "bho": "bhojpuri",
    "bs": "bosnian",
    "bg": "bulgarian",
    "ca": "catalan",
    "ceb": "cebuano",
    "ny": "chichewa",
    "zh-CN": "chinese (simplified)",
    "zh-TW": "chinese (traditional)",
    "co": "corsican",
    "hr": "croatian",
    "cs": "czech",
    "da": "danish",
    "dv": "dhivehi",
    "doi": "dogri",
    "nl": "dutch",
    "en": "english",
    "eo": "esperanto",
    "et": "estonian",
    "ee": "ewe",
    "tl": "filipino",
    "fi": "finnish",
    "fr": "french",
    "fy": "frisian",
    "gl": "galician",
    "ka": "georgian",
    "de": "german",
    "el": "greek",
    "gn": "guarani",
    "gu": "gujarati",
    "ht": "haitian creole",
    "ha": "hausa",
    "haw": "hawaiian",
    "he": "hebrew",
    "hi": "hindi",
    "hmn": "hmong",
    "hu": "hungarian",
    "is": "icelandic",
    "ig": "igbo",
    "ilo": "ilocano",
    "id": "indonesian",
    "ga": "irish",
    "it": "italian",
    "ja": "japanese",
    "jv": "javanese",
    "kn": "kannada",
    "kk": "kazakh",
    "km": "khmer",
    "rw": "kinyarwanda",
    "gom": "konkani",
    "ko": "korean",
    "kri": "krio",
    "ku": "kurdish (kurmanji)",
    "ckb": "kurdish (sorani)",
    "ky": "kyrgyz",
    "lo": "lao",
    "la": "latin",
    "lv": "latvian",
    "ln": "lingala",
    "lt": "lithuanian",
    "lg": "luganda",
    "lb": "luxembourgish",
    "mk": "macedonian",
    "mai": "maithili",
    "mg": "malagasy",
    "ms": "malay",
    "ml": "malayalam",
    "mt": "maltese",
    "mi": "maori",
    "mr": "marathi",
    "mni-Mtei": "meiteilon (manipuri)",
    "lus": "mizo",
    "mn": "mongolian",
    "my": "myanmar (burmese)",
    "ne": "nepali",
    "no": "norwegian",
    "or": "odia (oriya)",
    "om": "oromo",
    "ps": "pashto",
    "fa": "persian",
    "pl": "polish",
    "pt": "portuguese",
    "pa": "punjabi",
    "qu": "quechua",
    "ro": "romanian",
    "ru": "russian",
    "sm": "samoan",
    "sa": "sanskrit",
    "gd": "scots gaelic",
    "nso": "sepedi",
    "sr": "serbian",
    "st": "sesotho",
    "sn": "shona",
    "sd": "sindhi",
    "si": "sinhala",
    "sk": "slovak",
    "sl": "slovenian",
    "so": "somali",
    "es": "spanish",
    "su": "sundanese",
    "sw": "swahili",
    "sv": "swedish",
    "tg": "tajik",
    "ta": "tamil",
    "tt": "tatar",
    "te": "telugu",
    "th": "thai",
    "ti": "tigrinya",
    "ts": "tsonga",
    "tr": "turkish",
    "tk": "turkmen",
    "ak": "twi",
    "uk": "ukrainian",
    "ur": "urdu",
    "ug": "uyghur",
    "uz": "uzbek",
    "vi": "vietnamese",
    "cy": "welsh",
    "xh": "xhosa",
    "yi": "yiddish",
    "yo": "yoruba",
    "zu": "zulu",
}


def _label(code: str, name: str) -> str:
    return f"{code} ({name})"


# Widget value -> language code
LANGUAGE_OPTIONS = {_label(_AUTO, "detect language"): _AUTO}
for _code, _name in sorted(GOOGLE_LANGUAGES.items(), key=lambda kv: kv[1]):
    LANGUAGE_OPTIONS[_label(_code, _name)] = _code

SOURCE_LANGUAGES = list(LANGUAGE_OPTIONS.keys())
TARGET_LANGUAGES = [opt for opt in SOURCE_LANGUAGES if LANGUAGE_OPTIONS[opt] != _AUTO]

DEFAULT_SOURCE = _label(_AUTO, "detect language")
DEFAULT_TARGET = _label("en", "english")


class GoogleTranslateError(RuntimeError):
    """Raised when Google Translate could not be reached."""


def _to_code(value: str | None, fallback: str = _AUTO) -> str:
    """Accept a dropdown label ('fr (french)'), a raw code ('fr') or None."""
    if not value:
        return fallback
    value = str(value).strip()
    if value in LANGUAGE_OPTIONS:
        return LANGUAGE_OPTIONS[value]
    if value.lower() == _AUTO:
        return _AUTO
    # Raw code, optionally written like "CODE (name)"
    code = value.split("(")[0].strip()
    return code or fallback


def _split_text(text: str, limit: int = MAX_CHUNK) -> list[str]:
    """Split text into <= limit sized chunks, keeping line breaks."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(line[i : i + limit] for i in range(0, len(line), limit))
            continue
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks or [""]


def _parse_web_response(payload) -> str:
    """Parse the answer of the free Google Translate web endpoints.

    Two shapes exist depending on the endpoint:

    * ``[["Bonjour", "en"]]``              (client=dict-chrome-ex)
    * ``[[["Bonjour", "hello", ...]]]``    (client=gtx / webapp)
    """
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, list) and first and isinstance(first[0], str):
            return "".join(item[0] for item in payload if item and isinstance(item[0], str))
        if isinstance(first, list) and first and isinstance(first[0], list):
            return "".join(segment[0] for segment in first if segment and segment[0])
    raise GoogleTranslateError(f"Unexpected Google Translate answer: {str(payload)[:200]}")


# Free endpoints, tried in order. `client` is the value passed to the endpoint.
_FREE_ENDPOINTS = (
    ("https://clients5.google.com/translate_a/t", "dict-chrome-ex"),
    ("https://translate.googleapis.com/translate_a/single", "gtx"),
    ("https://translate.google.com/translate_a/single", "gtx"),
)


def _request_free(url: str, client: str, chunk: str, source: str, target: str) -> str:
    params = {"client": client, "sl": source or _AUTO, "tl": target}
    if client == "gtx":
        params.update({"dt": "t", "ie": "UTF-8", "oe": "UTF-8"})

    response = requests.post(
        url, params=params, data={"q": chunk}, headers=_HEADERS, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return _parse_web_response(json.loads(response.content.decode("utf-8", "replace")))


def _translate_web(chunk: str, source: str, target: str) -> str:
    last_error: Exception | None = None
    for index, (url, client) in enumerate(_FREE_ENDPOINTS):
        # Retry the main endpoint, try the fallbacks only once each.
        attempts = RETRIES if index == 0 else 1
        for attempt in range(attempts):
            try:
                return _request_free(url, client, chunk, source, target)
            except Exception as exc:  # noqa: BLE001 - network errors are broad
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(0.5 * (attempt + 1))
    raise GoogleTranslateError(
        "Google Translate could not be reached (tried "
        + ", ".join(url.split("/")[2] for url, _ in _FREE_ENDPOINTS)
        + f"): {last_error}"
    )


def _translate_api_key(chunk: str, source: str, target: str, api_key: str) -> str:
    data = {"q": chunk, "target": target, "format": "text"}
    if source and source != _AUTO:
        data["source"] = source
    response = requests.post(
        "https://translation.googleapis.com/language/translate/v2",
        params={"key": api_key},
        data=data,
        headers=_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["data"]["translations"][0]["translatedText"]


def _translate_chunk(chunk: str, source: str, target: str, api_key: str) -> str:
    if api_key:
        try:
            return _translate_api_key(chunk, source, target, api_key)
        except Exception as exc:  # noqa: BLE001 - fall back to the free endpoint
            print(f"[Simple Google Translate] API key request failed ({exc}), using free endpoint.")
    return _translate_web(chunk, source, target)


def translate_text(
    text: str,
    source_language: str = DEFAULT_SOURCE,
    target_language: str = DEFAULT_TARGET,
) -> str:
    """Translate `text` from `source_language` to `target_language`."""
    if text is None:
        return ""

    text = str(text)
    if not text.strip():
        return text

    source = _to_code(source_language, _AUTO)
    target = _to_code(target_language, "en")
    api_key = os.environ.get(API_KEY_ENV, "").strip()

    if source == target:
        return text

    parts: list[str] = []
    for chunk in _split_text(text):
        if not chunk.strip():
            parts.append(chunk)
            continue
        parts.append(_translate_chunk(chunk, source, target, api_key))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


class GoogleTranslateTextNode:
    """Translate a text into another language (string in, string out)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": False,
                        "default": "",
                    },
                ),
                "source_language": (SOURCE_LANGUAGES, {"default": DEFAULT_SOURCE}),
                "target_language": (TARGET_LANGUAGES, {"default": DEFAULT_TARGET}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "translate"
    CATEGORY = "Translate/Google"
    DESCRIPTION = (
        "Translates the input text with Google Translate and returns the "
        "translated text."
    )

    def translate(self, text, source_language, target_language):
        return (translate_text(text, source_language, target_language),)


class GoogleTranslateCLIPTextEncodeNode:
    """Translate a prompt, then encode it with CLIP (conditioning output)."""

    @classmethod
    def INPUT_TYPES(cls):
        types = GoogleTranslateTextNode.INPUT_TYPES()
        types["required"]["clip"] = ("CLIP",)
        return types

    RETURN_TYPES = (
        "CONDITIONING",
        "STRING",
    )
    RETURN_NAMES = ("conditioning", "text")
    FUNCTION = "translate_and_encode"
    CATEGORY = "Translate/Google"
    DESCRIPTION = (
        "Translates the prompt with Google Translate and encodes the "
        "translated text with CLIP."
    )

    def translate_and_encode(self, text, source_language, target_language, clip):
        translated = translate_text(text, source_language, target_language)
        tokens = clip.tokenize(translated)
        conditioning, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
        return ([[conditioning, {"pooled_output": pooled}]], translated)
