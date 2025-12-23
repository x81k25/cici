# standard library imports
import os
from typing import TYPE_CHECKING, Optional

# 3rd-party imports
import httpx
from loguru import logger

# local imports
from mind.config import config

if TYPE_CHECKING:
    from mind.session import Session


# Claude API URL (constant, not configurable)
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


class ClaudeController:
    """
    Claude controller for Anthropic API calls.

    Stateless single-question API calls to Claude.
    """

    def __init__(self, model: Optional[str] = None, display_name: Optional[str] = None):
        """
        Initialize the Claude controller.

        Args:
            model: Model name to use for inference (defaults to config).
            display_name: Friendly model name for responses (defaults to config).
        """
        self.model = model or config.claude_model
        self.display_name = display_name or config.claude_display_name
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.timeout = config.llm_timeout

    async def ask(self, question: str, session: "Session") -> dict:
        """
        Send a single question to Claude and get a response.

        Args:
            question: The user's question.
            session: The session context (for logging).

        Returns:
            Dict with response:
            {
                "success": bool,
                "response": str | None,
                "model": str,
                "error": str | None
            }
        """
        session.logger.info(f"Claude ask: {question}")

        if not self.api_key:
            error_msg = "ANTHROPIC_API_KEY not configured"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "model": self.display_name,
                "error": error_msg
            }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    CLAUDE_API_URL,
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": config.llm_max_tokens,
                        "messages": [
                            {"role": "user", "content": question}
                        ]
                    }
                )
                response.raise_for_status()
                data = response.json()

            # extract text from response
            content = data.get("content", [])
            if content and len(content) > 0:
                text_response = content[0].get("text", "")
            else:
                text_response = ""

            session.logger.info(f"Claude response: {text_response[:100]}...")

            return {
                "success": True,
                "response": text_response,
                "model": self.display_name,
                "error": None
            }

        except httpx.TimeoutException:
            error_msg = "Claude request timed out"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "model": self.display_name,
                "error": error_msg
            }
        except httpx.HTTPStatusError as e:
            error_msg = f"Claude HTTP error: {e.response.status_code}"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "model": self.display_name,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Claude error: {str(e)}"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "model": self.display_name,
                "error": error_msg
            }

    async def is_available(self) -> bool:
        """Check if the Claude API is configured."""
        return bool(self.api_key)
