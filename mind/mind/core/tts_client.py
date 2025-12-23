# standard library imports
from typing import Optional

# 3rd-party imports
import httpx
from loguru import logger

# local imports
from mind.config import config


async def send_to_tts(sentence: str, request_id: Optional[str] = None) -> bool:
    """
    Fire-and-forget sentence to TTS service.

    Args:
        sentence: Text to synthesize
        request_id: Optional ID for tracing

    Returns:
        True if accepted, False if failed (non-blocking either way)
    """
    if not config.tts_enabled:
        return False

    if not sentence or not sentence.strip():
        return False

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{config.mouth_url}/synthesize",
                json={
                    "text": sentence.strip(),
                    "request_id": request_id
                },
                timeout=config.tts_timeout
            )

            if response.status_code == 202:
                logger.debug(f"sentence queued for TTS: {sentence[:50]}...")
                return True
            else:
                logger.warning(f"TTS rejected sentence: {response.status_code}")
                return False

        except httpx.RequestError as e:
            # log and continue - don't block primary service
            logger.warning(f"TTS service unavailable: {e}")
            return False


async def check_tts_health() -> bool:
    """Check if the TTS service is available."""
    if not config.tts_enabled:
        return False

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{config.mouth_url}/health",
                timeout=2.0
            )
            return response.status_code == 200
        except httpx.RequestError:
            return False
