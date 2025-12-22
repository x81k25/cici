# standard library imports
import json
import re
from pathlib import Path
from typing import Optional

# 3rd-party imports
from loguru import logger


# ------------------------------------------------------------------------------
# word alias normalization
# ------------------------------------------------------------------------------

_aliases: Optional[dict[str, str]] = None
CONFIG_PATH = Path(__file__).parent / "config" / "word_aliases.json"


def load_aliases() -> dict[str, str]:
    """
    Load word aliases from config file.

    Returns:
        Dictionary mapping alias -> canonical form (all lowercase).
    """
    global _aliases
    if _aliases is not None:
        return _aliases

    if not CONFIG_PATH.exists():
        logger.warning(f"word aliases config not found: {CONFIG_PATH}")
        _aliases = {}
        return _aliases

    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            _aliases = config.get("aliases", {})
            # ensure all keys are lowercase
            _aliases = {k.lower(): v for k, v in _aliases.items()}
            logger.info(f"loaded {len(_aliases)} word aliases from config")
            return _aliases
    except Exception as e:
        logger.error(f"failed to load word aliases: {e}")
        _aliases = {}
        return _aliases


def normalize_transcription(text: str) -> str:
    """
    Normalize transcription by replacing known aliases with canonical forms.

    Performs word-boundary-aware replacement to avoid partial matches.
    Preserves original case structure where possible.

    Args:
        text: Raw transcription text from Whisper.

    Returns:
        Normalized transcription with aliases replaced.
    """
    if not text:
        return text

    aliases = load_aliases()
    if not aliases:
        return text

    result = text

    # sort aliases by length (longest first) to avoid partial replacements
    sorted_aliases = sorted(aliases.keys(), key=len, reverse=True)

    for alias in sorted_aliases:
        canonical = aliases[alias]
        # create case-insensitive word boundary pattern
        pattern = re.compile(r'\b' + re.escape(alias) + r'\b', re.IGNORECASE)
        result = pattern.sub(canonical, result)

    if result != text:
        logger.debug(f"normalized: '{text}' -> '{result}'")

    return result


def reload_aliases() -> None:
    """Force reload of aliases from config file."""
    global _aliases
    _aliases = None
    load_aliases()
