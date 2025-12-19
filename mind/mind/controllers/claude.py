# standard library imports
import os
from typing import TYPE_CHECKING

# 3rd-party imports
from dotenv import load_dotenv
import httpx
from loguru import logger

if TYPE_CHECKING:
    from mind.session import Session


# load environment variables
load_dotenv()

# Claude API configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MODEL_DISPLAY = "claude-sonnet"  # friendly name for responses
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


class ClaudeController:
    """
    Claude controller for Anthropic API calls.

    Stateless single-question API calls to Claude.
    """

    def __init__(self, model: str = CLAUDE_MODEL, display_name: str = CLAUDE_MODEL_DISPLAY):
        """
        Initialize the Claude controller.

        Args:
            model: Model name to use for inference.
            display_name: Friendly model name for responses.
        """
        self.model = model
        self.display_name = display_name
        self.api_key = ANTHROPIC_API_KEY
        self.timeout = 60.0

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
                        "max_tokens": 1024,
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
