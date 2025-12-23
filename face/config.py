"""Configuration loader for FACE frontend service.

Loads configuration from:
1. Root .env file (shared across services)
2. Module config/config.yaml (FACE-specific settings)
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
    # face/config.py -> face -> cici
    return Path(__file__).parent.parent.parent


def get_module_root() -> Path:
    """Get the module root directory (face/)."""
    return Path(__file__).parent


# -----------------------------------------------------------------------------
# Environment Settings (from root .env)
# -----------------------------------------------------------------------------

class EnvSettings(BaseSettings):
    """Settings loaded from root .env file."""

    # Service endpoints
    mind_host: str = "localhost"
    mind_port: int = 8765
    ears_host: str = "localhost"
    ears_port: int = 8766
    mouth_host: str = "localhost"
    mouth_port: int = 8001

    # Audio settings
    sample_rate: int = 16000
    ears_debug: bool = True

    # General settings
    log_level: str = "INFO"

    # Browser-accessible URL overrides (for non-localhost deployments)
    cici_ears_ws_url: Optional[str] = None
    cici_mouth_url: Optional[str] = None

    class Config:
        env_file = str(get_project_root() / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


# -----------------------------------------------------------------------------
# YAML Config Models
# -----------------------------------------------------------------------------

class AudioConfig(BaseModel):
    """Audio processing configuration."""
    chunk_duration_ms: int = 100
    echo_cancellation: bool = True
    noise_suppression: bool = True
    auto_gain_control: bool = True


class WebRTCConfig(BaseModel):
    """WebRTC configuration."""
    ice_servers: List[str] = ["stun:stun.l.google.com:19302"]


class TimeoutsConfig(BaseModel):
    """HTTP timeout configuration."""
    connect: float = 5.0
    llm_request: float = 120.0
    health_check: float = 2.0


class UIConfig(BaseModel):
    """UI configuration."""
    max_log_messages: int = 50
    audio_refresh_interval: float = 1.0


class ModuleConfig(BaseModel):
    """Module-specific configuration from config.yaml."""
    audio: AudioConfig = AudioConfig()
    webrtc: WebRTCConfig = WebRTCConfig()
    timeouts: TimeoutsConfig = TimeoutsConfig()
    ui: UIConfig = UIConfig()


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
# Global Config Instance
# -----------------------------------------------------------------------------

class Config:
    """Combined configuration for FACE frontend service."""

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

    # Convenience properties - Service URLs
    @property
    def mind_url(self) -> str:
        return f"http://{self.env.mind_host}:{self.env.mind_port}"

    @property
    def ears_ws_url(self) -> str:
        """Get EARS WebSocket URL (with optional override for browser access)."""
        if self.env.cici_ears_ws_url:
            base_url = self.env.cici_ears_ws_url
        else:
            base_url = f"ws://{self.env.ears_host}:{self.env.ears_port}"

        # Append debug query param if enabled
        if self.env.ears_debug:
            return f"{base_url}/?debug=true"
        return base_url

    @property
    def mouth_url(self) -> str:
        """Get MOUTH HTTP URL (with optional override for browser access)."""
        if self.env.cici_mouth_url:
            return self.env.cici_mouth_url
        return f"http://{self.env.mouth_host}:{self.env.mouth_port}"

    # Audio settings
    @property
    def sample_rate(self) -> int:
        return self.env.sample_rate

    @property
    def ears_debug(self) -> bool:
        return self.env.ears_debug

    @property
    def log_level(self) -> str:
        return self.env.log_level

    # Module config shortcuts
    @property
    def audio(self) -> AudioConfig:
        return self.module.audio

    @property
    def webrtc(self) -> WebRTCConfig:
        return self.module.webrtc

    @property
    def timeouts(self) -> TimeoutsConfig:
        return self.module.timeouts

    @property
    def ui(self) -> UIConfig:
        return self.module.ui


# Global config instance
config = Config()
