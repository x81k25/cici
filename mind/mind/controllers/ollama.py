# standard library imports
from typing import TYPE_CHECKING

# 3rd-party imports
import httpx
from loguru import logger

# local imports
from mind.core.prompts import get_prompt

if TYPE_CHECKING:
    from mind.session import Session


# Ollama server configuration
OLLAMA_HOST = "http://192.168.50.2:31435"
OLLAMA_MODEL = "phi3"


class OllamaController:
    """
    Ollama controller for LLM inference.

    Connects to a remote Ollama server to handle chat interactions.
    Maintains conversation context via session.conversation_context.
    """

    def __init__(self, host: str = OLLAMA_HOST, model: str = OLLAMA_MODEL):
        """
        Initialize the Ollama controller.

        Args:
            host: URL of the Ollama server.
            model: Model name to use for inference.
        """
        self.host = host
        self.model = model
        self.timeout = 60.0  # LLM responses can be slow

    async def connect(self) -> bool:
        """
        Check connection to the Ollama service.

        Returns:
            True if connected successfully.
        """
        return await self.is_available()

    async def chat(self, message: str, session: "Session") -> dict:
        """
        Send a message to Ollama and get a response.

        Args:
            message: The user's message.
            session: The session context (used for conversation history).

        Returns:
            Dict with response:
            {
                "success": bool,
                "response": str,
                "error": str | None
            }
        """
        session.logger.info(f"Ollama chat: {message}")

        # add user message to context
        session.add_to_context("user", message)

        # build messages for Ollama (system prompt + context, strip timestamps)
        system_prompt = get_prompt("cici_personality")
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(
            {"role": m["role"], "content": m["content"]}
            for m in session.conversation_context
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False
                    }
                )
                response.raise_for_status()
                data = response.json()

            assistant_response = data["message"]["content"]
            session.add_to_context("assistant", assistant_response)
            session.logger.info(f"Ollama response: {assistant_response[:100]}...")

            return {
                "success": True,
                "response": assistant_response,
                "error": None
            }
        except httpx.TimeoutException:
            error_msg = "Ollama request timed out"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "error": error_msg
            }
        except httpx.HTTPStatusError as e:
            error_msg = f"Ollama HTTP error: {e.response.status_code}"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Ollama error: {str(e)}"
            session.logger.error(error_msg)
            return {
                "success": False,
                "response": None,
                "error": error_msg
            }

    async def chat_stream(self, message: str, session: "Session"):
        """
        Stream a response from Ollama.

        Args:
            message: The user's message.
            session: The session context.

        Yields:
            Response chunks as they arrive.
        """
        session.logger.info(f"Ollama chat stream: {message}")

        # add user message to context
        session.add_to_context("user", message)

        # build messages for Ollama (system prompt + context, strip timestamps)
        system_prompt = get_prompt("cici_personality")
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(
            {"role": m["role"], "content": m["content"]}
            for m in session.conversation_context
        )

        full_response = ""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.host}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True
                    }
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            import json
                            chunk = json.loads(line)
                            if "message" in chunk and "content" in chunk["message"]:
                                content = chunk["message"]["content"]
                                full_response += content
                                yield content

            # add complete response to context
            session.add_to_context("assistant", full_response)

        except Exception as e:
            session.logger.error(f"Ollama stream error: {str(e)}")
            yield f"[Error: {str(e)}]"

    async def is_available(self) -> bool:
        """Check if the Ollama service is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
