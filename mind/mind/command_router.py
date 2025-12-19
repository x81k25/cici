# standard library imports
import re
from typing import TYPE_CHECKING

# 3rd-party imports
from loguru import logger

# local imports
from mind.core.commands import (
    check_command_trigger,
    get_cli_enter_triggers,
    get_cli_exit_triggers,
    get_claude_code_enter_triggers,
)
from mind.controllers.cli import CLIController
from mind.controllers.claude import ClaudeController
from mind.controllers.claude_code import ClaudeCodeController
from mind.controllers.ollama import OllamaController

if TYPE_CHECKING:
    from mind.session import Session


# command prefixes for "Hey Cici" commands
COMMAND_PREFIXES = [
    "hey cici",
    "hey sissy",
    "hey cc",
    "cici",
]



class CommandRouter:
    """
    Routes commands to appropriate controllers.

    Default mode is Ollama for conversational interaction.
    Use "commands mode" to switch to CLI for shell commands.

    Handles:
    - "Hey Cici" prefix parsing
    - Interaction mode switching (ollama/cli)
    - CLI command routing
    - Ollama routing
    """

    def __init__(self):
        """Initialize the command router."""
        self.cli_controller = CLIController()
        self.claude_controller = ClaudeController()
        self.claude_code_controller = ClaudeCodeController()
        self.ollama_controller = OllamaController()

    def parse_command(self, text: str) -> tuple[str | None, str | None, dict]:
        """
        Parse a command and determine its type.

        Args:
            text: The input text.

        Returns:
            Tuple of (command_type, command_text, params).
            command_type: "cli" | "llm" | "cli_enter" | "cli_exit" | "trigger" | None
            command_text: The actual command/message to execute
            params: Additional parameters
        """
        if not text:
            return None, None, {}

        text_lower = text.lower().strip()
        original_text = text.strip()

        # check for "Hey Cici" prefix
        remaining_text = original_text

        for prefix in COMMAND_PREFIXES:
            if text_lower.startswith(prefix):
                remaining_text = original_text[len(prefix):].strip()
                # remove leading comma if present
                if remaining_text.startswith(","):
                    remaining_text = remaining_text[1:].strip()
                break

        # check for command triggers from config
        action, cmd_or_text, triggered_remaining = check_command_trigger(remaining_text)
        if action:
            # for cli triggers with command template, use "trigger" type
            if action == "cli" and cmd_or_text and cmd_or_text != triggered_remaining:
                return "trigger", cmd_or_text, {"remaining": triggered_remaining}
            # for other actions, return action type directly
            return action, cmd_or_text, {"remaining": triggered_remaining}

        # default: treat as CLI command
        return "cli", remaining_text, {}

    async def route(
        self,
        text: str,
        session: "Session",
        original_voice: str | None = None
    ) -> dict:
        """
        Route a command to the appropriate controller.

        Args:
            text: The input text (translated command).
            session: The session context.
            original_voice: The original voice transcription (for Ollama fallback in CLI mode).

        Returns:
            Dict with routing result:
            {
                "type": str,  # "cli" | "ollama" | "trigger" | "error"
                "result": Any,
                "message": str
            }
        """
        # strip "Hey Cici" prefix for trigger checking
        text_lower = text.lower().strip()
        text_stripped = text.strip()
        for prefix in COMMAND_PREFIXES:
            if text_lower.startswith(prefix):
                text_stripped = text.strip()[len(prefix):].strip()
                text_lower = text_stripped.lower()
                if text_lower.startswith(","):
                    text_stripped = text_stripped[1:].strip()
                    text_lower = text_stripped.lower()
                break

        # =====================================================================
        # CHECK FOR MODE ENTRANCE TRIGGERS (valid from any mode)
        # =====================================================================

        # check for Claude Code mode enter triggers
        claude_code_triggers = get_claude_code_enter_triggers()
        for trigger in claude_code_triggers:
            if text_lower.startswith(trigger):
                session.enter_claude_code_mode()
                return {
                    "type": "claude_code_enter",
                    "result": {"interaction_mode": "claude_code"},
                    "confirmation": {"message": "Entering code mode. What would you like to build?", "success": True},
                    "message": "entered Claude Code mode"
                }

        # check for CLI mode enter triggers
        cli_enter_triggers = get_cli_enter_triggers()
        for trigger in cli_enter_triggers:
            if text_lower.startswith(trigger):
                session.enter_cli_mode()
                confirmation = await self.cli_controller.generate_mode_confirmation("cli", session)
                return {
                    "type": "cli_enter",
                    "result": {"interaction_mode": "cli"},
                    "confirmation": confirmation,
                    "message": "entered CLI commands mode"
                }

        # check for Ollama mode enter triggers (exit triggers from CLI)
        cli_exit_triggers = get_cli_exit_triggers()
        for trigger in cli_exit_triggers:
            if text_lower.startswith(trigger):
                session.enter_ollama_mode()
                confirmation = await self.cli_controller.generate_mode_confirmation("ollama", session)
                return {
                    "type": "ollama_enter",
                    "result": {"interaction_mode": "ollama"},
                    "confirmation": confirmation,
                    "message": "entered Ollama mode"
                }

        # =====================================================================
        # OLLAMA MODE (default) - conversational, route to Ollama
        # =====================================================================
        if session.interaction_mode == "ollama":
            # check for "ask claude" trigger (works from any mode)
            if text_lower.startswith("ask claude"):
                question = text_stripped[len("ask claude"):].strip()
                if question.startswith(","):
                    question = question[1:].strip()
                if question:
                    claude_result = await self.claude_controller.ask(question, session)
                    return {
                        "type": "claude",
                        "result": claude_result,
                        "message": "claude response"
                    }

            # default: route to Ollama for conversation
            session.logger.info(f"Ollama mode routing: {text}")
            ollama_result = await self.ollama_controller.chat(text, session)
            return {
                "type": "ollama",
                "result": ollama_result,
                "message": "ollama response"
            }

        # =====================================================================
        # CLI MODE - execute commands
        # =====================================================================
        if session.interaction_mode == "cli":
            # check for "ask claude" trigger (works from any mode)
            if text_lower.startswith("ask claude"):
                question = text_stripped[len("ask claude"):].strip()
                if question.startswith(","):
                    question = question[1:].strip()
                if question:
                    claude_result = await self.claude_controller.ask(question, session)
                    return {
                        "type": "claude",
                        "result": claude_result,
                        "message": "claude response"
                    }

            # parse and route command
            command_type, command_text, params = self.parse_command(text)
            session.logger.info(f"CLI routing: type={command_type}, command={command_text}")

            if command_type is None:
                return {
                    "type": "error",
                    "result": None,
                    "message": "could not parse command"
                }

            # handle triggered command (with template)
            if command_type == "trigger":
                session.logger.info(f"executing triggered command: {command_text}")
                cli_result = await self.cli_controller.execute_with_fallback(
                    command_text, session, original_voice
                )
                # generate voice-friendly summary
                summary_result = await self.cli_controller.summarize_output(
                    command=cli_result.get("command", command_text),
                    output=cli_result.get("output", ""),
                    exit_code=cli_result.get("exit_code"),
                    session=session
                )
                return {
                    "type": "trigger",
                    "result": cli_result,
                    "summary": summary_result,
                    "message": "triggered command executed"
                }

            # handle CLI command (default in CLI mode)
            if command_type == "cli":
                cli_result = await self.cli_controller.execute_with_fallback(
                    command_text, session, original_voice
                )
                # generate voice-friendly summary
                summary_result = await self.cli_controller.summarize_output(
                    command=cli_result.get("command", command_text),
                    output=cli_result.get("output", ""),
                    exit_code=cli_result.get("exit_code"),
                    session=session
                )
                return {
                    "type": "cli",
                    "result": cli_result,
                    "summary": summary_result,
                    "message": "command executed"
                }

        # =====================================================================
        # CLAUDE CODE MODE - route to Claude Code SDK
        # =====================================================================
        if session.interaction_mode == "claude_code":
            # check for "ask claude" trigger (works from any mode)
            if text_lower.startswith("ask claude"):
                question = text_stripped[len("ask claude"):].strip()
                if question.startswith(","):
                    question = question[1:].strip()
                if question:
                    claude_result = await self.claude_controller.ask(question, session)
                    return {
                        "type": "claude",
                        "result": claude_result,
                        "message": "claude response"
                    }

            # check for confirmation responses (affirmative/negative)
            if self.claude_code_controller.has_pending_confirmation(session):
                if text_lower in ("affirmative", "negative"):
                    result = await self.claude_code_controller.handle_confirmation(
                        text_lower, session
                    )
                    return {
                        "type": "claude_code",
                        "result": result,
                        "message": "confirmation handled"
                    }

            # default: route to Claude Code
            session.logger.info(f"Claude Code mode routing: {text}")
            claude_code_result = await self.claude_code_controller.query(text, session)
            return {
                "type": "claude_code",
                "result": claude_code_result,
                "message": "claude code response"
            }

        return {
            "type": "error",
            "result": None,
            "message": f"unknown interaction mode: {session.interaction_mode}"
        }
