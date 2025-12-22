"""Configuration settings for TTS service."""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """TTS service configuration."""

    # Queue settings
    max_queue_depth: int = 10

    # Piper model settings
    piper_model_path: Path = Path(__file__).parent.parent / "models" / "en_GB-jenny_dioco-medium.onnx"
    piper_config_path: Path = Path(__file__).parent.parent / "models" / "en_GB-jenny_dioco-medium.onnx.json"

    # Audio output settings
    sample_rate: int = 22050
    audio_format: str = "wav"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8001

    class Config:
        env_prefix = "TTS_"


settings = Settings()
