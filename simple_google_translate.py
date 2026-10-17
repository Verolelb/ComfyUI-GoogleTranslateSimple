# Title: Simple Google Translate
# Desc : Minimal Google Translate nodes for ComfyUI.
#
# Design goals
# ------------
# * One single job: translate text with Google Translate.
# * No frontend hooks beyond one small "Manual Translate" button -> nothing that
#   can slow down or interfere with the Preview/Save image nodes.
# * No extra pip install: only `requests`, which ComfyUI already bundles.
#
# Reliability
# -----------
# Google heavily rate limits its free web endpoints (HTTP 429). This module
# therefore:
#   * tries several independent Google endpoints, then falls back to MyMemory,
#   * retries with a short backoff,
#   * caches results so re-running a workflow does not hit the network again.

from __future__ import annotations

import hashlib
import html
import json
import os
import threading
import time

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Optional: if this environment variable is set, the official Google Cloud
# Translation API is tried first (falling back to the free providers).
API_KEY_ENV = "GOOGLE_TRANSLATION_API_KEY"

# Max characters sent in a single request, per provider.
GOOGLE_MAX_CHUNK = 1800
MYMEMORY_MAX_CHUNK = 450

# (connect, read) timeout in seconds.
REQUEST_TIMEOUT = (5, 25)

# Pause before retrying the same endpoint (number of entries = extra attempts).
RETRY_DELAYS = (1.0,)

# Number of translations kept in memory.
CACHE_SIZE = 256

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

GOOGLE_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"

# Free Google endpoints using the `dict-chrome-ex` client. This client is much
# more permissive than the classic `gtx` one, which answers 429 very quickly.
GOOGLE_ENDPOINTS = (
    "https://clients5.google.com/translate_a/t",
    "https://translate.googleapis.com/translate_a/t",
    "https://translate.google.com/translate_a/t",
)

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
    """Raised when no translation provider could be reached."""


# ---------------------------------------------------------------------------
# Small in-memory cache (avoids hammering Google when a workflow is re-run)
# ---------------------------------------------------------------------------

_CACHE: dict[str, str] = {}
_CACHE_LOCK = threading.Lock()


def _cache_key(text: str, source: str, target: str) -> str:
    raw = f"{source}\x00{target}\x00{text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _cache_get(key: str):
    with _CACHE_LOCK:
        return _CACHE.get(key)


def _cache_set(key: str, value: str) -> None:
    with _CACHE_LOCK:
        if len(_CACHE) >= CACHE_SIZE:
            for old in list(_CACHE)[: CACHE_SIZE // 4]:
                _CACHE.pop(old, None)
        _CACHE[key] = value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _split_text(text: str, limit: int) -> list[str]:
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


# ---------------------------------------------------------------------------
# Google (free web endpoints)
# ---------------------------------------------------------------------------


def _parse_google_payload(payload) -> tuple[str, str | None]:
    """Parse Google's answer, whatever its shape.

    * ``[["text", "fr"]]``        -> dict-chrome-ex with sl=auto
    * ``["text"]``                -> dict-chrome-ex with an explicit sl
    * ``[[["text", "src", ...]]]`` -> classic gtx / webapp layout
    """
    if not isinstance(payload, list) or not payload:
        raise GoogleTranslateError(f"unexpected answer: {str(payload)[:160]}")

    pieces: list[str] = []
    detected: str | None = None

    for item in payload:
        if isinstance(item, str):
            pieces.append(item)
        elif isinstance(item, list) and item:
            if isinstance(item[0], str):
                pieces.append(item[0])
                if len(item) > 1 and isinstance(item[1], str) and detected is None:
                    detected = item[1]
            elif isinstance(item[0], list):
                for segment in item:
                    if isinstance(segment, list) and segment and isinstance(segment[0], str):
                        pieces.append(segment[0])
                        if (
                            len(segment) > 2
                            and isinstance(segment[2], str)
                            and len(segment[2]) == 2
                            and detected is None
                        ):
                            detected = segment[2]

    text = "".join(pieces)
    if not text:
        raise GoogleTranslateError(f"empty answer: {str(payload)[:160]}")
    return text, detected


def _google_request(url: str, chunk: str, source: str, target: str) -> tuple[str, str | None]:
    response = requests.post(
        url,
        params={"client": "dict-chrome-ex", "sl": source or _AUTO, "tl": target},
        data={"q": chunk},
        headers=_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = json.loads(response.content.decode("utf-8", "replace"))
    return _parse_google_payload(payload)


def _google_chunk(url: str, chunk: str, source: str, target: str) -> tuple[str, str | None]:
    last_error: Exception | None = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return _google_request(url, chunk, source, target)
        except Exception as exc:  # noqa: BLE001 - network errors are broad
            last_error = exc
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
    raise GoogleTranslateError(f"{url.split('/')[2]} -> {last_error}")


def _translate_google(text: str, source: str, target: str) -> tuple[str, dict]:
    pieces: list[str] = []
    errors: list[str] = []
    detected: str | None = None

    for chunk in _split_text(text, GOOGLE_MAX_CHUNK):
        if not chunk.strip():
            pieces.append(chunk)
            continue

        result = None
        for url in GOOGLE_ENDPOINTS:
            try:
                result = _google_chunk(url, chunk, source, target)
                break
            except Exception as exc:  # noqa: BLE001 - try the next endpoint
                errors.append(str(exc))

        if result is None:
            raise GoogleTranslateError("; ".join(errors[-3:]) or "no endpoint answered")

        pieces.append(result[0])
        detected = detected or result[1]

    return "".join(pieces), {"provider": "google", "detected_source": detected}


# ---------------------------------------------------------------------------
# MyMemory (independent fallback, no API key)
# ---------------------------------------------------------------------------

_MYMEMORY_ERRORS = (
    "QUERY LENGTH LIMIT EXCEEDED",
    "INVALID LANGUAGE PAIR",
    "NO QUERY SPECIFIED",
)


def _mymemory_chunk(chunk: str, source: str, target: str) -> str:
    langpair = f"{_AUTO if source in (None, '', _AUTO) else source}|{target}"
    if langpair.startswith(_AUTO):
        langpair = "autodetect|" + target

    response = requests.get(
        MYMEMORY_URL,
        params={"q": chunk, "langpair": langpair},
        headers=_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    text = html.unescape(str(payload.get("responseData", {}).get("translatedText", "")))
    upper = text.upper()

    # The text is already in the target language: nothing to translate.
    if "DISTINCT LANGUAGES" in upper:
        return chunk

    if any(hint in upper for hint in _MYMEMORY_ERRORS):
        raise GoogleTranslateError(f"mymemory -> {text[:120]}")

    status = payload.get("responseStatus")
    if status is not None and str(status) != "200":
        raise GoogleTranslateError(f"mymemory -> status {status}: {text[:120]}")

    if not text:
        raise GoogleTranslateError("mymemory -> empty answer")
    return text


def _translate_mymemory(text: str, source: str, target: str) -> tuple[str, dict]:
    pieces: list[str] = []
    for chunk in _split_text(text, MYMEMORY_MAX_CHUNK):
        pieces.append(chunk if not chunk.strip() else _mymemory_chunk(chunk, source, target))
    return "".join(pieces), {"provider": "mymemory", "detected_source": None}


# ---------------------------------------------------------------------------
# Optional: official Google Cloud Translation API
# ---------------------------------------------------------------------------


def _translate_api_key(text: str, source: str, target: str, api_key: str) -> tuple[str, dict]:
    pieces: list[str] = []
    detected: str | None = None

    for chunk in _split_text(text, GOOGLE_MAX_CHUNK):
        if not chunk.strip():
            pieces.append(chunk)
            continue
        data = {"q": chunk, "target": target, "format": "text"}
        if source and source != _AUTO:
            data["source"] = source
        response = requests.post(
            GOOGLE_TRANSLATE_URL,
            params={"key": api_key},
            data=data,
            headers=_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()["data"]
        translations = payload.get("translations", [])
        if not translations:
            raise GoogleTranslateError("api key -> empty answer")
        pieces.append(html.unescape(translations[0]["translatedText"]))
        detected = detected or payload.get("detectedSourceLanguage") or translations[0].get(
            "detectedSourceLanguage"
        )

    return "".join(pieces), {"provider": "google-cloud-api", "detected_source": detected}


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def translate_with_meta(text: str, source_language: str, target_language: str) -> tuple[str, dict]:
    """Translate `text` and also return which provider was used."""
    if text is None:
        return "", {"provider": "none", "detected_source": None}

    text = str(text)
    if not text.strip():
        return text, {"provider": "none", "detected_source": None}

    source = _to_code(source_language, _AUTO)
    target = _to_code(target_language, "en")

    if source == target:
        return text, {"provider": "none", "detected_source": source}

    key = _cache_key(text, source, target)
    cached = _cache_get(key)
    if cached is not None:
        return cached, {"provider": "cache", "detected_source": None}

    errors: list[str] = []
    providers = []

    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if api_key:
        providers.append(("google-cloud-api", lambda: _translate_api_key(text, source, target, api_key)))
    providers.extend(
        (
            ("google", lambda: _translate_google(text, source, target)),
            ("mymemory", lambda: _translate_mymemory(text, source, target)),
        )
    )

    for name, provider in providers:
        try:
            translated, meta = provider()
        except Exception as exc:  # noqa: BLE001 - try the next provider
            errors.append(f"{name}: {exc}")
            continue
        if translated and translated.strip():
            _cache_set(key, translated)
            return translated, meta
        errors.append(f"{name}: empty result")

    raise GoogleTranslateError(
        "no translation provider succeeded -> " + " | ".join(errors)
    )


def translate_text(text: str, source_language: str, target_language: str) -> str:
    """Translate `text` from `source_language` to `target_language`."""
    return translate_with_meta(text, source_language, target_language)[0]


# ---------------------------------------------------------------------------
# Server route used by the "Manual Translate" button
# ---------------------------------------------------------------------------


def _register_manual_translate_route() -> bool:
    """Register the route called by the frontend button.

    Everything is wrapped in a try/except on purpose: importing this module
    must never fail, even when it happens outside a running ComfyUI server
    (node scanning, tests, ...).
    """
    try:
        from aiohttp import web
        from server import PromptServer

        routes = PromptServer.instance.routes
    except Exception:  # noqa: BLE001 - not running inside ComfyUI
        return False

    @routes.post("/google_translate_simple/translate")
    async def _google_translate_simple_route(request):
        data = await request.json()
        try:
            translated, meta = translate_with_meta(
                data.get("text", ""),
                data.get("source_language", DEFAULT_SOURCE),
                data.get("target_language", DEFAULT_TARGET),
            )
            return web.json_response(
                {
                    "translated_text": translated,
                    "provider": meta.get("provider"),
                    "detected_source": meta.get("detected_source"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - reported to the frontend
            return web.json_response({"error": str(exc)}, status=500)

    return True


MANUAL_TRANSLATE_ROUTE = _register_manual_translate_route()


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
        "translated text. The 'Manual Translate' button translates directly "
        "inside the text field."
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
