# standard library imports
from pathlib import Path
import subprocess
from typing import Optional

# 3rd-party imports
from loguru import logger
import yaml

# ------------------------------------------------------------------------------
# command trigger loading and execution
# ------------------------------------------------------------------------------

_commands_cache = None


def load_commands() -> dict:
    """
    Load command triggers from YAML config file.
    Returns dict of trigger phrases to command definitions.
    """
    global _commands_cache
    if _commands_cache is not None:
        return _commands_cache

    config_path = Path(__file__).parent.parent.parent / "config" / "commands.yaml"

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        commands = {}
        for category_name, category_data in config.items():
            if isinstance(category_data, dict):
                for trigger, definition in category_data.items():
                    commands[trigger.lower()] = definition

        _commands_cache = commands
        logger.info(f"loaded {len(commands)} command triggers from config")
        return commands

    except Exception as e:
        logger.error(f"failed to load commands config: {e}")
        return {}


def check_command_trigger(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Check if text starts with a command trigger phrase.

    :param text: transcribed voice text
    :return: tuple of (action, command_or_text, remaining_text) or (None, None, None)
             action: "cli", "llm", "cli_enter", "cli_exit", "llm_enter", "llm_exit"
             command_or_text: shell command (for cli) or message (for llm)
             remaining_text: text after trigger
    """
    if not text:
        return None, None, None

    text_lower = text.lower().strip()
    commands = load_commands()

    # check each trigger (sorted by length, longest first)
    for trigger in sorted(commands.keys(), key=len, reverse=True):
        if text_lower.startswith(trigger):
            definition = commands[trigger]
            remaining = text[len(trigger):].strip()
            # strip leading comma
            if remaining.startswith(","):
                remaining = remaining[1:].strip()

            # check if command requires text
            if definition.get("requires_text", False) and not remaining:
                return None, None, None

            action = definition.get("action", "cli")

            # for cli actions with command template, build the command
            if action == "cli" and "command" in definition:
                cmd_template = definition["command"]
                if "{text}" in cmd_template:
                    cmd = cmd_template.replace("{text}", remaining)
                else:
                    cmd = cmd_template
                return action, cmd, remaining

            # for other actions, return remaining text as the content
            return action, remaining, remaining

    return None, None, None


def get_cli_enter_triggers() -> list[str]:
    """
    Get list of triggers that enter CLI mode (from LLM default).

    :return: list of trigger phrases that have action: cli_enter
    """
    commands = load_commands()
    triggers = []
    for trigger, definition in commands.items():
        action = definition.get("action", "")
        if action in ("cli_enter", "llm_exit"):
            triggers.append(trigger)
    return triggers


def get_cli_exit_triggers() -> list[str]:
    """
    Get list of triggers that exit CLI mode (return to LLM default).

    :return: list of trigger phrases that have action: cli_exit
    """
    commands = load_commands()
    triggers = []
    for trigger, definition in commands.items():
        action = definition.get("action", "")
        if action in ("cli_exit", "llm_enter"):
            triggers.append(trigger)
    return triggers


def get_llm_exit_triggers() -> list[str]:
    """
    Get list of triggers that exit LLM mode (same as entering CLI mode).
    Kept for backwards compatibility.

    :return: list of trigger phrases
    """
    return get_cli_enter_triggers()


def get_claude_code_enter_triggers() -> list[str]:
    """
    Get list of triggers that enter Claude Code mode.

    :return: list of trigger phrases that have action: claude_code_enter
    """
    commands = load_commands()
    triggers = []
    for trigger, definition in commands.items():
        action = definition.get("action", "")
        if action == "claude_code_enter":
            triggers.append(trigger)
    return triggers


def execute_command(command: str) -> str:
    """
    Execute a CLI command safely and return output.
    """
    dangerous_patterns = ["rm -rf", "sudo", "mkfs", "dd if=", "> /dev/"]
    for pattern in dangerous_patterns:
        if pattern in command.lower():
            logger.warning(f"blocked dangerous command: {command}")
            return f"error: command '{command}' is not allowed for safety reasons"

    try:
        logger.info(f"executing command: {command}")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd="/infra/experiments/cici"
        )

        output = result.stdout if result.stdout else result.stderr
        if result.returncode != 0 and result.stderr:
            output = f"error (code {result.returncode}): {result.stderr}"

        logger.info(f"command output: {output[:200]}...")
        return output.strip() if output else "command completed with no output"

    except subprocess.TimeoutExpired:
        logger.error(f"command timed out: {command}")
        return "error: command timed out after 30 seconds"
    except Exception as e:
        logger.error(f"command execution error: {e}")
        return f"error: {str(e)}"
