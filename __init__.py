"""Simple Google Translate - a minimal, standalone translation node pack.

Intentionally kept tiny: one Python module, no JavaScript, no dependencies
beyond what ComfyUI already ships.

Nodes
-----
* Google Translate Text                  -> STRING
* Google Translate CLIP Text Encode      -> CONDITIONING, STRING
"""

from .simple_google_translate import (
    GoogleTranslateCLIPTextEncodeNode,
    GoogleTranslateTextNode,
)

NODE_CLASS_MAPPINGS = {
    "SimpleGoogleTranslateTextNode": GoogleTranslateTextNode,
    "SimpleGoogleTranslateCLIPTextEncodeNode": GoogleTranslateCLIPTextEncodeNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleGoogleTranslateTextNode": "Google Translate Text",
    "SimpleGoogleTranslateCLIPTextEncodeNode": "Google Translate CLIP Text Encode",
}

# No WEB_DIRECTORY on purpose: this pack ships no frontend extension.
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
