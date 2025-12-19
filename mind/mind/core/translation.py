# standard library imports
from pathlib import Path
import re
from typing import Optional

# 3rd-party imports
from loguru import logger
import yaml

# ------------------------------------------------------------------------------
# translation loading and parsing
# ------------------------------------------------------------------------------

_translations_cache = None


def load_translations() -> list[tuple[str, str]]:
    """
    Load translations from YAML config file.
    Returns list of (voice_phrase, output_string) tuples, sorted by phrase length
    (longest first) to ensure multi-word phrases are matched before single words.
    """
    global _translations_cache
    if _translations_cache is not None:
        return _translations_cache

    config_path = Path(__file__).parent.parent.parent / "config" / "translations.yaml"

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        translations = []

        # flatten all categories into a single list
        for category_name, category_data in config.items():
            if isinstance(category_data, dict):
                for voice, output in category_data.items():
                    translations.append((str(voice), str(output)))

        # sort by length (longest first) to match multi-word phrases first
        translations.sort(key=lambda x: len(x[0]), reverse=True)

        _translations_cache = translations
        logger.info(f"loaded {len(translations)} translations from config")
        return translations

    except Exception as e:
        logger.error(f"failed to load translations config: {e}")
        # fallback to empty list
        return []


def parse_voice_to_cli(text: str) -> Optional[str]:
    """
    Parse voice transcription to CLI command using translations from config.

    :param text: transcribed voice text
    :return: parsed CLI command or None
    """
    if not text:
        return None

    # normalize text
    text = text.lower().strip()

    # load translations from config (cached after first load)
    translations = load_translations()

    # apply translations (already sorted by length, longest first)
    for voice, output in translations:
        pattern = r'\b' + re.escape(voice) + r'\b'
        # escape backslashes in replacement to avoid regex interpretation
        safe_output = output.replace('\\', '\\\\')
        text = re.sub(pattern, safe_output, text, flags=re.IGNORECASE)

    # post-processing: join consecutive single letters (NATO alphabet result)
    # e.g., "l s" -> "ls", "g i t" -> "git"
    text = re.sub(r'\b([a-z])\s+(?=[a-z]\b)', r'\1', text)

    # post-processing: connect prefixes to following text (remove space after)
    # NOTE: dot is NOT included here - it's handled separately below to preserve
    # spaces in paths like "cd .." and "ls .hidden"
    connecting_prefixes = ["-", "/", "~", "@", "#", "$", "%", "&", "*"]
    for sym in connecting_prefixes:
        text = re.sub(re.escape(sym) + r'\s+', sym, text)

    # post-processing: join underscores with surrounding text
    text = re.sub(r'\s*_\s*', '_', text)

    # post-processing: convert ". ." to ".." (parent directory)
    text = re.sub(r'\.\s+\.', '..', text)

    # post-processing: convert ". /" to "./" (current directory path)
    text = re.sub(r'\.\s+/', './', text)

    # post-processing: join dots for file extensions FIRST (word + dot + short extension)
    # e.g., "file . txt" -> "file.txt", "script . py" -> "script.py"
    text = re.sub(r'(\w)\s*\.\s*(\w{1,4})\b', r'\1.\2', text)

    # post-processing: connect standalone dot to following word (for dotfiles)
    # e.g., "ls . hidden" -> "ls .hidden" (only if not already joined above)
    text = re.sub(r'(?<=\s)\.\s+(\w)', r'.\1', text)

    # post-processing: ensure space after redirect operators
    text = re.sub(r'>(\S)', r'> \1', text)
    text = re.sub(r'<(\S)', r'< \1', text)

    # normalize whitespace
    text = " ".join(text.split())

    logger.info(f"parsed command: {text}")
    return text
