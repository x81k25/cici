# standard library imports
import asyncio
import re
from typing import TYPE_CHECKING

# 3rd-party imports
import httpx
from loguru import logger

# local imports
from mind.core.commands import execute_command as sync_execute_command
from mind.core.prompts import get_prompt

if TYPE_CHECKING:
    from mind.session import Session


# Ollama configuration (same as llm.py)
OLLAMA_HOST = "http://192.168.50.2:31435"
OLLAMA_MODEL = "phi3"


# dangerous patterns that should be blocked
DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "sudo rm",
    "mkfs",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "> /dev/sda",
    "chmod -R 777 /",
    ":(){:|:&};:",  # fork bomb
]


class CLIController:
    """
    Executes CLI commands via tmux session.

    Provides async interface to the synchronous tmux execution,
    with safety checks for dangerous commands.
    """

    def __init__(self):
        """Initialize the CLI controller."""
        self.blocked_commands: list[str] = DANGEROUS_PATTERNS.copy()

    def is_safe(self, command: str) -> tuple[bool, str | None]:
        """
        Check if a command is safe to execute.

        Args:
            command: The command to check.

        Returns:
            Tuple of (is_safe, reason if unsafe).
        """
        command_lower = command.lower()
        for pattern in self.blocked_commands:
            if pattern.lower() in command_lower:
                return False, f"blocked pattern: {pattern}"
        return True, None

    async def execute(self, command: str, session: "Session") -> dict:
        """
        Execute a CLI command in the session's tmux instance.

        Args:
            command: The command to execute.
            session: The session context.

        Returns:
            Dict with execution result:
            {
                "success": bool,
                "output": str,
                "command": str,
                "error": str | None
            }
        """
        session.logger.info(f"executing command: {command}")

        # safety check
        is_safe, reason = self.is_safe(command)
        if not is_safe:
            session.logger.warning(f"blocked unsafe command: {command} ({reason})")
            return {
                "success": False,
                "output": "",
                "command": command,
                "error": f"command blocked for safety: {reason}"
            }

        try:
            # run tmux execution in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: session.tmux.execute_with_status(command, wait_seconds=0.5)
            )

            output = result["output"]
            exit_code = result["exit_code"]
            success = result["success"]

            session.logger.info(
                f"command output (exit={exit_code}): "
                f"{output[:200]}..." if len(output) > 200 else f"command output (exit={exit_code}): {output}"
            )

            return {
                "success": success,
                "output": output,
                "command": command,
                "exit_code": exit_code,
                "error": None if success else f"command exited with code {exit_code}"
            }

        except Exception as e:
            session.logger.error(f"command execution failed: {e}")
            return {
                "success": False,
                "output": "",
                "command": command,
                "exit_code": None,
                "error": str(e)
            }

    async def execute_raw(self, command: str, session: "Session") -> str:
        """
        Execute a command and return just the output string.

        Convenience method that wraps execute() for simpler use cases.

        Args:
            command: The command to execute.
            session: The session context.

        Returns:
            The command output or error message.
        """
        result = await self.execute(command, session)
        if result["success"]:
            return result["output"]
        else:
            return f"error: {result['error']}"

    async def generate_mode_confirmation(
        self,
        mode: str,
        session: "Session"
    ) -> dict:
        """
        Generate a short confirmation for mode switches.

        Args:
            mode: The mode being entered ("cli" or "ollama").
            session: The session context.

        Returns:
            Dict with confirmation:
            {
                "success": bool,
                "message": str | None,
                "error": str | None
            }
        """
        session.logger.info(f"generating mode confirmation for: {mode}")

        if mode == "cli":
            prompt = get_prompt("mode_confirm_cli")
        else:
            prompt = get_prompt("mode_confirm_ollama")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False
                    }
                )
                response.raise_for_status()
                data = response.json()

            message = data.get("response", "").strip()
            message = message.strip('"\'')

            session.logger.info(f"mode confirmation: {message}")
            return {
                "success": True,
                "message": message,
                "error": None
            }

        except Exception as e:
            session.logger.warning(f"mode confirmation failed: {e}")
            # fallback to static message
            fallback = "Command mode active" if mode == "cli" else "Chat mode active"
            return {
                "success": True,
                "message": fallback,
                "error": None
            }

    async def summarize_output(
        self,
        command: str,
        output: str,
        exit_code: int | None,
        session: "Session"
    ) -> dict:
        """
        Generate a voice-friendly summary of command output.

        Args:
            command: The command that was executed.
            output: The raw command output.
            exit_code: The exit code (0 = success).
            session: The session context.

        Returns:
            Dict with summary result:
            {
                "success": bool,
                "summary": str | None,
                "error": str | None
            }
        """
        session.logger.info(f"generating summary for: {command}")

        success = exit_code == 0 if exit_code is not None else False
        status = "succeeded" if success else "failed"

        prompt = get_prompt(
            "cli_summarize",
            command=command,
            status=status,
            exit_code=exit_code,
            output=output[:1000]
        )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False
                    }
                )
                response.raise_for_status()
                data = response.json()

            summary = data.get("response", "").strip()
            summary = summary.strip('"\'')  # remove any quotes

            session.logger.info(f"command summary: {summary}")
            return {
                "success": True,
                "summary": summary,
                "error": None
            }

        except httpx.TimeoutException:
            session.logger.warning("summary generation timed out")
            return {
                "success": False,
                "summary": None,
                "error": "summary timed out"
            }
        except Exception as e:
            session.logger.warning(f"summary generation failed: {e}")
            return {
                "success": False,
                "summary": None,
                "error": str(e)
            }

    async def get_llm_correction(
        self,
        original_voice: str,
        translated_command: str,
        error_output: str,
        session: "Session"
    ) -> dict:
        """
        Request command correction from Ollama.

        Args:
            original_voice: The original voice transcription.
            translated_command: The command that was attempted.
            error_output: The error output from the failed command.
            session: The session context.

        Returns:
            Dict with correction result:
            {
                "success": bool,
                "corrected_command": str | None,
                "explanation": str | None,
                "error": str | None
            }
        """
        session.logger.info(f"requesting LLM correction for: {translated_command}")

        prompt = get_prompt(
            "cli_correction",
            original_voice=original_voice,
            translated_command=translated_command,
            error_output=error_output
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False
                    }
                )
                response.raise_for_status()
                data = response.json()

            corrected = data.get("response", "").strip()

            # clean up the response - remove any quotes or extra whitespace
            corrected = corrected.strip('"\'`')
            corrected = corrected.split('\n')[0].strip()  # take only first line

            if corrected == "CANNOT_CORRECT" or not corrected:
                session.logger.info("LLM could not determine correction")
                return {
                    "success": False,
                    "corrected_command": None,
                    "explanation": "could not determine correction",
                    "error": None
                }

            session.logger.info(f"LLM suggested correction: {corrected}")
            return {
                "success": True,
                "corrected_command": corrected,
                "explanation": None,
                "error": None
            }

        except httpx.TimeoutException:
            session.logger.error("LLM correction request timed out")
            return {
                "success": False,
                "corrected_command": None,
                "explanation": None,
                "error": "LLM request timed out"
            }
        except Exception as e:
            session.logger.error(f"LLM correction failed: {e}")
            return {
                "success": False,
                "corrected_command": None,
                "explanation": None,
                "error": str(e)
            }

    async def execute_with_fallback(
        self,
        command: str,
        session: "Session",
        original_voice: str | None = None
    ) -> dict:
        """
        Execute a command with LLM fallback on failure.

        If the command fails, attempts to get a correction from Ollama
        and optionally re-executes the corrected command.

        Args:
            command: The command to execute.
            session: The session context.
            original_voice: The original voice transcription (for LLM context).

        Returns:
            Dict with execution result, including any correction attempts:
            {
                "success": bool,
                "output": str,
                "command": str,
                "error": str | None,
                "correction_attempted": bool,
                "original_command": str | None,
                "corrected_command": str | None
            }
        """
        # first attempt - now uses exit code to determine success
        result = await self.execute(command, session)

        # SECURITY: Never attempt LLM correction for blocked commands
        # This prevents the LLM from suggesting alternate dangerous commands
        if result.get("error") and "blocked" in result["error"].lower():
            result["correction_attempted"] = False
            result["original_command"] = None
            result["corrected_command"] = None
            return result

        # if failed and we have voice context, try LLM correction
        if not result["success"] and original_voice:
            session.logger.info("attempting LLM correction for failed command")

            correction = await self.get_llm_correction(
                original_voice=original_voice,
                translated_command=command,
                error_output=result.get("output", "") or result.get("error", ""),
                session=session
            )

            if correction["success"] and correction["corrected_command"]:
                corrected_cmd = correction["corrected_command"]
                session.logger.info(f"retrying with corrected command: {corrected_cmd}")

                # execute corrected command
                corrected_result = await self.execute(corrected_cmd, session)

                return {
                    "success": corrected_result["success"],
                    "output": corrected_result["output"],
                    "command": corrected_cmd,
                    "error": corrected_result["error"],
                    "correction_attempted": True,
                    "original_command": command,
                    "corrected_command": corrected_cmd
                }

            # correction failed, return original result with note
            result["correction_attempted"] = True
            result["original_command"] = command
            result["corrected_command"] = None
        else:
            result["correction_attempted"] = False
            result["original_command"] = None
            result["corrected_command"] = None

        return result
