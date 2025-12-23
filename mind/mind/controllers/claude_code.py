# standard library imports
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

# 3rd-party imports
from loguru import logger

# local imports
from mind.config import config

if TYPE_CHECKING:
    from mind.session import Session


class ClaudeCodeController:
    """
    Claude Code controller using the Claude Agent SDK.

    Provides voice-friendly interaction with Claude Code for coding tasks.
    Uses ClaudeSDKClient for session continuity across multiple exchanges.
    """

    def __init__(self):
        """Initialize the Claude Code controller."""
        self.model = config.claude_model
        self.display_name = "claude-code"
        self._clients: dict[str, Any] = {}  # session_id -> ClaudeSDKClient
        self._pending_confirmations: dict[str, dict] = {}  # session_id -> confirmation data

    async def _get_working_directory(self, session: "Session") -> Path:
        """
        Get the working directory for Claude Code.

        Priority:
        1. Use session's current_directory (synced from tmux)
        2. Sync from tmux if session directory is default
        3. Fall back to default cici directory

        Args:
            session: The session context.

        Returns:
            Path to the working directory.
        """
        # first, try to sync from tmux to get latest directory
        session.sync_directory_from_tmux()

        # use session's current_directory if it exists
        if session.current_directory and Path(session.current_directory).exists():
            session.logger.info(f"using session directory: {session.current_directory}")
            return Path(session.current_directory)

        session.logger.info(f"using default cwd: {config.default_cwd}")
        return config.default_cwd

    async def _get_or_create_client(self, session: "Session") -> Any:
        """
        Get or create a ClaudeSDKClient for the session.

        Args:
            session: The session context.

        Returns:
            ClaudeSDKClient instance.
        """
        if session.id in self._clients:
            return self._clients[session.id]

        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

            cwd = await self._get_working_directory(session)

            options = ClaudeAgentOptions(
                model=self.model,
                cwd=str(cwd),
                permission_mode="acceptEdits",
                allowed_tools=[
                    "Read", "Write", "Edit", "Glob", "Grep",
                    "Bash", "TodoWrite", "WebSearch", "WebFetch"
                ],
                setting_sources=["project"],  # load CLAUDE.md from project
            )

            client = ClaudeSDKClient(options=options)
            await client.connect()
            self._clients[session.id] = client
            session.logger.info(f"created Claude Code client for session {session.id}")
            return client

        except ImportError as e:
            session.logger.error(f"claude-agent-sdk not installed: {e}")
            raise
        except Exception as e:
            session.logger.error(f"failed to create Claude Code client: {e}")
            raise

    async def _cleanup_client(self, session: "Session") -> None:
        """
        Cleanup the ClaudeSDKClient for a session.

        Args:
            session: The session context.
        """
        client = self._clients.pop(session.id, None)
        if client:
            try:
                await client.disconnect()
                session.logger.info(f"disconnected Claude Code client for session {session.id}")
            except Exception as e:
                session.logger.warning(f"error disconnecting client: {e}")

        # also clear any pending confirmations
        self._pending_confirmations.pop(session.id, None)

    async def query(self, prompt: str, session: "Session") -> dict:
        """
        Send a query to Claude Code and get a response.

        Args:
            prompt: The user's prompt/request.
            session: The session context.

        Returns:
            Dict with response:
            {
                "success": bool,
                "content": str | None,  # brief spoken summary
                "model": str,
                "error": str | None,
                "awaiting_confirmation": bool,
                "confirmation_prompt": str | None
            }
        """
        session.logger.info(f"Claude Code query: {prompt}")

        try:
            client = await self._get_or_create_client(session)

            # send query
            await client.query(prompt)

            # collect response
            response_text = ""
            actions_taken = []

            from claude_agent_sdk import (
                AssistantMessage,
                TextBlock,
                ToolUseBlock,
                ResultMessage
            )

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            actions_taken.append(block.name)

                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        return {
                            "success": False,
                            "response": None,
                            "model": self.display_name,
                            "error": message.result or "Claude Code encountered an error",
                            "awaiting_confirmation": False,
                            "confirmation_prompt": None
                        }

            # generate brief summary for voice
            summary = self._generate_brief_summary(response_text, actions_taken)

            # use full response_text for frontend, summary for voice
            display_response = response_text.strip() if response_text.strip() else summary

            session.logger.info(f"Claude Code response: {summary}")

            return {
                "success": True,
                "response": display_response,
                "brief_summary": summary,  # keep brief version for potential voice use
                "model": self.display_name,
                "error": None,
                "awaiting_confirmation": False,
                "confirmation_prompt": None
            }

        except ImportError:
            error_msg = "Claude Agent SDK not installed. Run: pip install claude-agent-sdk"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "model": self.display_name,
                "error": error_msg,
                "awaiting_confirmation": False,
                "confirmation_prompt": None
            }

        except Exception as e:
            error_msg = f"Claude Code error: {str(e)}"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "model": self.display_name,
                "error": error_msg,
                "awaiting_confirmation": False,
                "confirmation_prompt": None
            }

    def _generate_brief_summary(self, response_text: str, actions_taken: list[str]) -> str:
        """
        Generate a brief, voice-friendly summary of the response.

        Args:
            response_text: The full response text from Claude.
            actions_taken: List of tool names that were used.

        Returns:
            Brief summary suitable for TTS.
        """
        # if there's response text, use first 1-2 sentences
        if response_text:
            # split into sentences
            sentences = response_text.replace("\n", " ").split(". ")
            # take first 2 sentences max
            summary_sentences = sentences[:2]
            summary = ". ".join(s.strip() for s in summary_sentences if s.strip())
            if summary and not summary.endswith("."):
                summary += "."

            # truncate if too long (for voice)
            if len(summary) > 200:
                summary = summary[:197] + "..."

            return summary

        # if no text but actions were taken, summarize actions
        if actions_taken:
            unique_actions = list(dict.fromkeys(actions_taken))  # preserve order, remove dupes
            action_counts = {a: actions_taken.count(a) for a in unique_actions}

            summaries = []
            for action, count in action_counts.items():
                if action == "Read":
                    summaries.append(f"read {count} file{'s' if count > 1 else ''}")
                elif action == "Write":
                    summaries.append(f"wrote {count} file{'s' if count > 1 else ''}")
                elif action == "Edit":
                    summaries.append(f"made {count} edit{'s' if count > 1 else ''}")
                elif action == "Bash":
                    summaries.append(f"ran {count} command{'s' if count > 1 else ''}")
                elif action == "Grep":
                    summaries.append(f"searched {count} time{'s' if count > 1 else ''}")
                elif action == "Glob":
                    summaries.append(f"found files")
                else:
                    summaries.append(f"used {action}")

            return "Done. " + ", ".join(summaries) + "."

        return "Done."

    async def handle_confirmation(self, response: str, session: "Session") -> dict:
        """
        Handle a confirmation response (affirmative/negative).

        Args:
            response: The user's response ("affirmative" or "negative").
            session: The session context.

        Returns:
            Dict with result of the confirmation.
        """
        response_lower = response.lower().strip()

        if response_lower == "affirmative":
            # user confirmed - proceed with pending action
            pending = self._pending_confirmations.pop(session.id, None)
            if pending:
                session.logger.info("user confirmed action")
                # TODO: implement actual confirmation flow when SDK supports it
                return {
                    "success": True,
                    "response": "Confirmed. Proceeding.",
                    "model": self.display_name,
                    "error": None,
                    "awaiting_confirmation": False,
                    "confirmation_prompt": None
                }
            else:
                return {
                    "success": True,
                    "response": "Nothing pending to confirm.",
                    "model": self.display_name,
                    "error": None,
                    "awaiting_confirmation": False,
                    "confirmation_prompt": None
                }

        elif response_lower == "negative":
            # user declined
            self._pending_confirmations.pop(session.id, None)
            session.logger.info("user declined action")
            return {
                "success": True,
                "response": "Cancelled.",
                "model": self.display_name,
                "error": None,
                "awaiting_confirmation": False,
                "confirmation_prompt": None
            }

        else:
            # not a confirmation response - treat as regular query
            return await self.query(response, session)

    def has_pending_confirmation(self, session: "Session") -> bool:
        """Check if there's a pending confirmation for the session."""
        return session.id in self._pending_confirmations

    async def interrupt(self, session: "Session") -> dict:
        """
        Interrupt the current Claude Code operation.

        Args:
            session: The session context.

        Returns:
            Dict with interrupt result.
        """
        client = self._clients.get(session.id)
        if client:
            try:
                await client.interrupt()
                session.logger.info("interrupted Claude Code operation")
                return {
                    "success": True,
                    "response": "Operation interrupted.",
                    "model": self.display_name,
                    "error": None,
                    "awaiting_confirmation": False,
                    "confirmation_prompt": None
                }
            except Exception as e:
                session.logger.warning(f"failed to interrupt: {e}")

        return {
            "success": True,
            "response": "Nothing to interrupt.",
            "model": self.display_name,
            "error": None,
            "awaiting_confirmation": False,
            "confirmation_prompt": None
        }

    async def is_available(self) -> bool:
        """Check if the Claude Agent SDK is available."""
        try:
            from claude_agent_sdk import ClaudeSDKClient
            return True
        except ImportError:
            return False

    async def cleanup_session(self, session: "Session") -> None:
        """
        Cleanup resources for a session.

        Called when a session is being removed.

        Args:
            session: The session being cleaned up.
        """
        await self._cleanup_client(session)
