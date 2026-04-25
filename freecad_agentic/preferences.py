"""Thin wrapper around FreeCAD's parameter store for addon settings."""
from __future__ import annotations

import os

import FreeCAD

_PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/Agentic"

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_ITERATIONS = 40
DEFAULT_SYSTEM_PROMPT_EXTRA = ""


def _params():
    return FreeCAD.ParamGet(_PARAM_PATH)


def get_api_key() -> str:
    key = _params().GetString("ApiKey", "")
    if key:
        return key
    return os.environ.get("ANTHROPIC_API_KEY", "")


def set_api_key(value: str) -> None:
    _params().SetString("ApiKey", value or "")


def get_model() -> str:
    return _params().GetString("Model", DEFAULT_MODEL) or DEFAULT_MODEL


def set_model(value: str) -> None:
    _params().SetString("Model", value or DEFAULT_MODEL)


def get_max_tokens() -> int:
    return int(_params().GetInt("MaxTokens", DEFAULT_MAX_TOKENS) or DEFAULT_MAX_TOKENS)


def set_max_tokens(value: int) -> None:
    _params().SetInt("MaxTokens", int(value))


def get_max_iterations() -> int:
    return int(_params().GetInt("MaxIterations", DEFAULT_MAX_ITERATIONS) or DEFAULT_MAX_ITERATIONS)


def set_max_iterations(value: int) -> None:
    _params().SetInt("MaxIterations", int(value))


def get_auto_screenshot() -> bool:
    return bool(_params().GetBool("AutoScreenshot", True))


def set_auto_screenshot(value: bool) -> None:
    _params().SetBool("AutoScreenshot", bool(value))


def get_system_prompt_extra() -> str:
    return _params().GetString("SystemPromptExtra", DEFAULT_SYSTEM_PROMPT_EXTRA)


def set_system_prompt_extra(value: str) -> None:
    _params().SetString("SystemPromptExtra", value or "")
