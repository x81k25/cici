"""HTTP client for MOUTH TTS service.

MOUTH provides text-to-speech audio synthesis.
FACE polls GET /audio/next to retrieve completed audio chunks.
"""

import httpx


class MouthClient:
    """Client for fetching audio from MOUTH TTS service."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url

    def get_next_audio(self) -> tuple[bytes | None, dict]:
        """Fetch next audio chunk from TTS service.

        Returns:
            Tuple of (audio_bytes or None, metadata dict)
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/audio/next")

                metadata = {
                    "pending": int(response.headers.get("X-Pending-Count", 0)),
                    "completed": int(response.headers.get("X-Completed-Count", 0)),
                }

                if response.status_code == 200:
                    return response.content, metadata
                elif response.status_code == 204:
                    return None, metadata
                else:
                    return None, metadata

        except Exception as e:
            return None, {"error": str(e)}

    def health_check(self) -> bool:
        """Check if MOUTH TTS service is available."""
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False
