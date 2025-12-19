# standard library imports
from pathlib import Path

# 3rd-party imports
from loguru import logger
import yaml


# ------------------------------------------------------------------------------
# prompt loading
# ------------------------------------------------------------------------------

_prompts_cache: dict | None = None


def load_prompts() -> dict:
    """
    Load system prompts from YAML config file.

    Returns:
        Dict of prompt name to prompt template string.
    """
    global _prompts_cache
    if _prompts_cache is not None:
        return _prompts_cache

    config_path = Path(__file__).parent.parent.parent / "config" / "system-prompts.yaml"

    try:
        with open(config_path, "r") as f:
            prompts = yaml.safe_load(f)

        _prompts_cache = prompts or {}
        logger.info(f"loaded {len(_prompts_cache)} system prompts from config")
        return _prompts_cache

    except Exception as e:
        logger.error(f"failed to load prompts config: {e}")
        return {}


def get_prompt(name: str, **kwargs) -> str:
    """
    Get a prompt by name, optionally with variable substitution.

    Args:
        name: The prompt name (key in system-prompts.yaml).
        **kwargs: Variables to substitute in the prompt template.

    Returns:
        The prompt string with variables substituted.

    Raises:
        KeyError: If prompt name not found.
    """
    prompts = load_prompts()

    if name not in prompts:
        raise KeyError(f"prompt '{name}' not found in system-prompts.yaml")

    prompt = prompts[name]

    # substitute variables if provided
    if kwargs:
        prompt = prompt.format(**kwargs)

    return prompt.strip()


def get_prompt_or_default(name: str, default: str, **kwargs) -> str:
    """
    Get a prompt by name with a fallback default.

    Args:
        name: The prompt name.
        default: Default value if prompt not found.
        **kwargs: Variables to substitute.

    Returns:
        The prompt string or default.
    """
    try:
        return get_prompt(name, **kwargs)
    except KeyError:
        logger.warning(f"prompt '{name}' not found, using default")
        if kwargs:
            return default.format(**kwargs)
        return default
