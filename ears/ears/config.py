"""Configuration loader for EARS service.

Loads configuration from:
1. Root .env file (shared across services)
2. Module config/config.yaml (EARS-specific settings)
"""

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# -----------------------------------------------------------------------------
# Path Resolution
# -----------------------------------------------------------------------------

def get_project_root() -> Path:
    """Get the project root directory (cici/)."""
    # ears/ears/config.py -> ears/ears -> ears -> cici
    return Path(__file__).parent.parent.parent.parent


def get_module_root() -> Path:
    """Get the module root directory (ears/)."""
    return Path(__file__).parent.parent


# -----------------------------------------------------------------------------
# Environment Settings (from root .env)
# -----------------------------------------------------------------------------

class EnvSettings(BaseSettings):
    """Settings loaded from root .env file."""

    # Service endpoints
    ears_host: str = "localhost"
    ears_port: int = 8766
    mind_host: str = "localhost"
    mind_port: int = 8765

    # Audio settings
    sample_rate: int = 16000
    ears_silence_duration_ms: int = 1000

    # General settings
    log_level: str = "INFO"

    class Config:
        env_file = str(get_project_root() / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


# -----------------------------------------------------------------------------
# YAML Config Models
# -----------------------------------------------------------------------------

class VADConfig(BaseModel):
    """Voice Activity Detection configuration."""
    speech_threshold: float = 0.5
    min_speech_duration_ms: int = 250
    speech_pad_ms: int = 100
    max_buffer_seconds: float = 30.0


class WhisperConfig(BaseModel):
    """Whisper transcription configuration."""
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "en"
    beam_size: int = 5
    vad_min_silence_duration_ms: int = 500
    vad_speech_pad_ms: int = 200


class WebSocketConfig(BaseModel):
    """WebSocket server configuration."""
    ping_interval: int = 30
    ping_timeout: int = 120


class ModuleConfig(BaseModel):
    """Module-specific configuration from config.yaml."""
    vad: VADConfig = VADConfig()
    whisper: WhisperConfig = WhisperConfig()
    websocket: WebSocketConfig = WebSocketConfig()
    hallucination_phrases: List[str] = [
        "thank you",
        "thanks for watching",
        "subscribe",
        "see you next time",
        "bye",
        "goodbye",
        "thank you for watching",
        "thanks for listening",
    ]


# -----------------------------------------------------------------------------
# Config Loader
# -----------------------------------------------------------------------------

def load_module_config() -> ModuleConfig:
    """Load module configuration from config/config.yaml."""
    config_path = get_module_root() / "ears" / "config" / "config.yaml"

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return ModuleConfig(**data)

    return ModuleConfig()


# -----------------------------------------------------------------------------
# Global Config Instance
# -----------------------------------------------------------------------------

class Config:
    """Combined configuration for EARS service."""

    def __init__(self):
        self._env: Optional[EnvSettings] = None
        self._module: Optional[ModuleConfig] = None

    @property
    def env(self) -> EnvSettings:
        """Environment settings from root .env."""
        if self._env is None:
            self._env = EnvSettings()
        return self._env

    @property
    def module(self) -> ModuleConfig:
        """Module settings from config.yaml."""
        if self._module is None:
            self._module = load_module_config()
        return self._module

    # Convenience properties - Environment
    @property
    def ears_host(self) -> str:
        return self.env.ears_host

    @property
    def ears_port(self) -> int:
        return self.env.ears_port

    @property
    def mind_url(self) -> str:
        return f"http://{self.env.mind_host}:{self.env.mind_port}"

    @property
    def sample_rate(self) -> int:
        return self.env.sample_rate

    @property
    def silence_duration_ms(self) -> int:
        return self.env.ears_silence_duration_ms

    @property
    def log_level(self) -> str:
        return self.env.log_level

    # Convenience properties - VAD
    @property
    def vad(self) -> VADConfig:
        return self.module.vad

    # Convenience properties - Whisper
    @property
    def whisper(self) -> WhisperConfig:
        return self.module.whisper

    # Convenience properties - WebSocket
    @property
    def websocket(self) -> WebSocketConfig:
        return self.module.websocket

    @property
    def hallucination_phrases(self) -> List[str]:
        return self.module.hallucination_phrases


# Global config instance
config = Config()
