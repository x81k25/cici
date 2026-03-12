"""Configuration loader for MOUTH TTS service.

Loads configuration from:
1. Root .env file (shared across services)
2. Module config/config.yaml (MOUTH-specific settings)
3. TTS_* environment variables (legacy support via pydantic-settings)
"""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


# -----------------------------------------------------------------------------
# Path Resolution
# -----------------------------------------------------------------------------

def get_project_root() -> Path:
    """Get the project root directory (cici/)."""
    # mouth/mouth/config.py -> mouth/mouth -> mouth -> cici
    return Path(__file__).parent.parent.parent


def get_module_root() -> Path:
    """Get the module root directory (mouth/)."""
    return Path(__file__).parent.parent


# -----------------------------------------------------------------------------
# Environment Settings (from root .env)
# -----------------------------------------------------------------------------

class EnvSettings(BaseSettings):
    """Settings loaded from root .env file."""

    # Service endpoints
    mouth_host: str = "0.0.0.0"
    mouth_port: int = 8001

    # Piper TTS settings
    piper_voice: str = "en_GB-jenny_dioco-medium"
    piper_sample_rate: int = 22050

    # General settings
    log_level: str = "INFO"

    class Config:
        env_file = str(get_project_root() / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


# -----------------------------------------------------------------------------
# Legacy TTS Settings (env vars with TTS_ prefix)
# -----------------------------------------------------------------------------

class LegacyTTSSettings(BaseSettings):
    """Legacy TTS_* environment variable support."""

    max_queue_depth: Optional[int] = None
    piper_model_path: Optional[str] = None
    piper_config_path: Optional[str] = None
    sample_rate: Optional[int] = None
    host: Optional[str] = None
    port: Optional[int] = None

    class Config:
        env_prefix = "TTS_"
        extra = "ignore"


# -----------------------------------------------------------------------------
# YAML Config Models
# -----------------------------------------------------------------------------

class QueueConfig(BaseModel):
    """Queue configuration."""
    max_depth: int = 10


class PiperConfig(BaseModel):
    """Piper TTS configuration."""
    model_path: str = "models/en_GB-jenny_dioco-medium.onnx"
    config_path: str = "models/en_GB-jenny_dioco-medium.onnx.json"
    sample_rate: int = 22050
    audio_format: str = "wav"


class ModuleConfig(BaseModel):
    """Module-specific configuration from config.yaml."""
    queue: QueueConfig = QueueConfig()
    piper: PiperConfig = PiperConfig()


# -----------------------------------------------------------------------------
# Config Loader
# -----------------------------------------------------------------------------

def load_module_config() -> ModuleConfig:
    """Load module configuration from config/config.yaml."""
    config_path = get_module_root() / "config" / "config.yaml"

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return ModuleConfig(**data)

    return ModuleConfig()


# -----------------------------------------------------------------------------
# Combined Settings (backward compatible)
# -----------------------------------------------------------------------------

class Settings:
    """
    Combined configuration for MOUTH TTS service.

    Maintains backward compatibility with existing TTS_* env vars while
    supporting new root .env and config.yaml approach.
    """

    def __init__(self):
        self._env: Optional[EnvSettings] = None
        self._legacy: Optional[LegacyTTSSettings] = None
        self._module: Optional[ModuleConfig] = None

    @property
    def env(self) -> EnvSettings:
        if self._env is None:
            self._env = EnvSettings()
        return self._env

    @property
    def legacy(self) -> LegacyTTSSettings:
        if self._legacy is None:
            self._legacy = LegacyTTSSettings()
        return self._legacy

    @property
    def module(self) -> ModuleConfig:
        if self._module is None:
            self._module = load_module_config()
        return self._module

    # Queue settings (legacy override > yaml)
    @property
    def max_queue_depth(self) -> int:
        return self.legacy.max_queue_depth or self.module.queue.max_depth

    # Piper settings (legacy override > env var > yaml)
    @property
    def piper_model_path(self) -> Path:
        if self.legacy.piper_model_path:
            return Path(self.legacy.piper_model_path)
        # Check Docker location first (/models/), then local dev (mouth/models/)
        voice = self.env.piper_voice
        docker_path = Path(f"/models/{voice}.onnx")
        if docker_path.exists():
            return docker_path
        return get_module_root() / "models" / f"{voice}.onnx"

    @property
    def piper_config_path(self) -> Path:
        if self.legacy.piper_config_path:
            return Path(self.legacy.piper_config_path)
        # Check Docker location first (/models/), then local dev (mouth/models/)
        voice = self.env.piper_voice
        docker_path = Path(f"/models/{voice}.onnx.json")
        if docker_path.exists():
            return docker_path
        return get_module_root() / "models" / f"{voice}.onnx.json"

    @property
    def sample_rate(self) -> int:
        return self.legacy.sample_rate or self.env.piper_sample_rate

    @property
    def audio_format(self) -> str:
        return self.module.piper.audio_format

    # Server settings (legacy override > root .env)
    @property
    def host(self) -> str:
        return self.legacy.host or self.env.mouth_host

    @property
    def port(self) -> int:
        return self.legacy.port or self.env.mouth_port

    @property
    def log_level(self) -> str:
        return self.env.log_level


# Global settings instance
settings = Settings()
