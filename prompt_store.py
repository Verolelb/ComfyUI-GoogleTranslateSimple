# Title: Simple Google Translate - saved prompt library
# Desc : Persistent storage + HTTP routes for the prompt manager of the nodes.
#
# Saved prompts live in a single human-readable JSON file inside ComfyUI's user
# directory (``<ComfyUI>/user/google_translate_simple/prompts.json``). They
# therefore survive browser cache clears, ComfyUI restarts and workflow
# reloads, and the library is shared by every node of this pack.
#
# The frontend only needs four small routes:
#   GET    /google_translate_simple/prompts       -> list every saved prompt
#   POST   /google_translate_simple/prompts       -> save the current text
#   DELETE /google_translate_simple/prompts/{id}  -> delete one prompt
#   DELETE /google_translate_simple/prompts       -> delete every prompt

from __future__ import annotations

import json
import os
import threading
import time
import uuid

# Hard limits, so a huge text field cannot bloat the JSON file forever.
MAX_PROMPTS = 500
MAX_NAME_LENGTH = 120
MAX_TEXT_LENGTH = 200_000

PROMPTS_ROUTE = "/google_translate_simple/prompts"

_LOCK = threading.Lock()
_ROUTES_REGISTERED = False


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _store_dir() -> str:
    """Directory holding the prompt library (ComfyUI's user directory)."""
    try:
        import folder_paths

        base = folder_paths.get_user_directory()
    except Exception:  # noqa: BLE001 - imported outside ComfyUI (tests, ...)
        base = os.path.join(os.path.expanduser("~"), ".comfyui")
    return os.path.join(base, "google_translate_simple")


def _store_path() -> str:
    return os.path.join(_store_dir(), "prompts.json")


def _read() -> list[dict]:
    """Read the library, tolerating a missing or corrupted file."""
    try:
        with open(_store_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        # Never break the node because of a damaged file: start empty, the
        # next write replaces it.
        return []

    prompts = data.get("prompts") if isinstance(data, dict) else data
    if not isinstance(prompts, list):
        return []

    return [
        item
        for item in prompts
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item.get("id")
        and isinstance(item.get("text"), str)
    ]


def _write(prompts: list[dict]) -> None:
    """Atomically replace the library file."""
    directory = _store_dir()
    os.makedirs(directory, exist_ok=True)
    path = _store_path()
    temporary = f"{path}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(
            {"version": 1, "prompts": prompts},
            handle,
            ensure_ascii=False,
            indent=2,
        )
    os.replace(temporary, path)


def _clean_name(name: str) -> str:
    return " ".join(str(name or "").split())[:MAX_NAME_LENGTH].strip()


def _auto_name(text: str) -> str:
    """Use the first meaningful line of the text as a default name."""
    for line in str(text).splitlines():
        line = " ".join(line.split())
        if line:
            return line[:60]
    return "Untitled prompt"


def _unique_name(prompts: list[dict], wanted: str) -> str:
    existing = {prompt.get("name") for prompt in prompts}
    if wanted not in existing:
        return wanted
    index = 2
    while f"{wanted} ({index})" in existing:
        index += 1
    return f"{wanted} ({index})"


def _public(prompt: dict) -> dict:
    return {
        "id": prompt["id"],
        "name": str(prompt.get("name") or "Untitled prompt"),
        "text": str(prompt.get("text") or ""),
        "source_language": str(prompt.get("source_language") or ""),
        "target_language": str(prompt.get("target_language") or ""),
        "created_at": prompt.get("created_at") or 0,
        "updated_at": prompt.get("updated_at") or prompt.get("created_at") or 0,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_prompts() -> list[dict]:
    """Every saved prompt, newest first."""
    with _LOCK:
        prompts = _read()
    prompts.sort(key=lambda prompt: prompt.get("created_at") or 0, reverse=True)
    return [_public(prompt) for prompt in prompts]


def save_prompt(
    text: str,
    name: str = "",
    source_language: str = "",
    target_language: str = "",
) -> tuple[dict, bool]:
    """Save ``text`` and return ``(prompt, created)``.

    * With an empty ``name``, the first line of the text is used and made
      unique, so saving twice never overwrites by accident.
    * With an explicit ``name`` that already exists, that save is updated
      instead of creating a duplicate (``created`` is then ``False``).
    """
    text = str(text or "")
    if not text.strip():
        raise ValueError("Cannot save an empty prompt.")

    text = text[:MAX_TEXT_LENGTH]
    name = _clean_name(name)
    now = time.time()

    with _LOCK:
        prompts = _read()

        if name:
            for prompt in prompts:
                if prompt.get("name") == name:
                    prompt["text"] = text
                    prompt["source_language"] = str(source_language or "")
                    prompt["target_language"] = str(target_language or "")
                    prompt["updated_at"] = now
                    _write(prompts)
                    return _public(prompt), False

        prompt = {
            "id": uuid.uuid4().hex,
            "name": name or _unique_name(prompts, _auto_name(text)),
            "text": text,
            "source_language": str(source_language or ""),
            "target_language": str(target_language or ""),
            "created_at": now,
            "updated_at": now,
        }
        prompts.append(prompt)

        if len(prompts) > MAX_PROMPTS:
            prompts.sort(key=lambda item: item.get("created_at") or 0)
            prompts = prompts[-MAX_PROMPTS:]

        _write(prompts)
        return _public(prompt), True


def delete_prompt(prompt_id: str) -> bool:
    """Delete one prompt. Returns False when it does not exist."""
    with _LOCK:
        prompts = _read()
        remaining = [prompt for prompt in prompts if prompt.get("id") != prompt_id]
        if len(remaining) == len(prompts):
            return False
        _write(remaining)
        return True


def delete_all_prompts() -> int:
    """Delete every prompt and return how many were removed."""
    with _LOCK:
        count = len(_read())
        _write([])
        return count


# ---------------------------------------------------------------------------
# HTTP routes (called by the "prompt manager" widgets in the frontend)
# ---------------------------------------------------------------------------


def register_routes() -> bool:
    """Register the prompt routes on ComfyUI's server.

    Everything is wrapped in a try/except on purpose: importing this module
    must never fail outside a running ComfyUI server.
    """
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return True

    try:
        from aiohttp import web
        from server import PromptServer

        routes = PromptServer.instance.routes
    except Exception:  # noqa: BLE001 - not running inside ComfyUI
        return False

    @routes.get(PROMPTS_ROUTE)
    async def _list_prompts(request):
        try:
            return web.json_response({"prompts": list_prompts()})
        except Exception as exc:  # noqa: BLE001 - reported to the frontend
            return web.json_response({"error": str(exc)}, status=500)

    @routes.post(PROMPTS_ROUTE)
    async def _save_prompt(request):
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001 - malformed body
            return web.json_response({"error": "Invalid JSON body."}, status=400)

        if not isinstance(data, dict):
            return web.json_response({"error": "Invalid JSON body."}, status=400)

        try:
            prompt, created = save_prompt(
                text=data.get("text", ""),
                name=data.get("name", ""),
                source_language=data.get("source_language", ""),
                target_language=data.get("target_language", ""),
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 - reported to the frontend
            return web.json_response({"error": str(exc)}, status=500)

        return web.json_response({"prompt": prompt, "created": created})

    @routes.delete(PROMPTS_ROUTE + "/{prompt_id}")
    async def _delete_prompt(request):
        prompt_id = request.match_info.get("prompt_id", "")
        try:
            deleted = delete_prompt(prompt_id)
        except Exception as exc:  # noqa: BLE001 - reported to the frontend
            return web.json_response({"error": str(exc)}, status=500)

        if not deleted:
            return web.json_response({"error": "Prompt not found."}, status=404)
        return web.json_response({"deleted": prompt_id})

    @routes.delete(PROMPTS_ROUTE)
    async def _delete_all_prompts(request):
        try:
            count = delete_all_prompts()
        except Exception as exc:  # noqa: BLE001 - reported to the frontend
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({"deleted": count})

    _ROUTES_REGISTERED = True
    return True
