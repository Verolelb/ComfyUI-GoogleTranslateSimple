"""Simple Google Translate - a minimal, standalone translation node pack.

Nodes
-----
* Google Translate Text             -> STRING
* Google Translate CLIP Text Encode -> CONDITIONING, STRING

The pack ships one small frontend file that only adds a "Manual Translate"
button, a read-only translation preview box and a saved prompt library to those
two nodes. It hooks nothing else in ComfyUI.
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

# Serves web/google_translate_simple.js to the ComfyUI frontend.
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
