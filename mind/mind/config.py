"""Configuration loader for MIND service.

Loads configuration from:
1. Root .env file (shared across services)
2. Module config/config.yaml (MIND-specific settings)
"""

import os
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
    # mind/mind/config.py -> mind/mind -> mind -> cici
    return Path(__file__).parent.parent.parent.parent


def get_module_root() -> Path:
    """Get the module root directory (mind/)."""
    return Path(__file__).parent.parent


# -----------------------------------------------------------------------------
# Environment Settings (from root .env)
# -----------------------------------------------------------------------------

class EnvSettings(BaseSettings):
    """Settings loaded from root .env file."""

    # Service endpoints
    mind_host: str = "localhost"
    mind_port: int = 8765
    mouth_host: str = "localhost"
    mouth_port: int = 8001

    # External services
    ollama_host: str = "http://192.168.50.2:31435"
    ollama_model: str = "hermes3"
    claude_model: str = "claude-sonnet-4-20250514"

    # General settings
    log_level: str = "INFO"
    default_cwd: str = "/infra/experiments/cici"

    class Config:
        env_file = str(get_project_root() / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


# -----------------------------------------------------------------------------
# YAML Config Models
# -----------------------------------------------------------------------------

class LLMConfig(BaseModel):
    """LLM-specific configuration."""
    timeout: float = 60.0
    max_tokens: int = 1024
    claude_display_name: str = "claude-sonnet"


class TTSConfig(BaseModel):
    """TTS client configuration."""
    enabled: bool = True
    timeout: float = 5.0


class ModuleConfig(BaseModel):
    """Module-specific configuration from config.yaml."""
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()


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
    """Combined configuration for MIND service."""

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

    # Convenience properties
    @property
    def mind_host(self) -> str:
        return self.env.mind_host

    @property
    def mind_port(self) -> int:
        return self.env.mind_port

    @property
    def mouth_url(self) -> str:
        return f"http://{self.env.mouth_host}:{self.env.mouth_port}"

    @property
    def ollama_host(self) -> str:
        return self.env.ollama_host

    @property
    def ollama_model(self) -> str:
        return self.env.ollama_model

    @property
    def claude_model(self) -> str:
        return self.env.claude_model

    @property
    def log_level(self) -> str:
        return self.env.log_level

    @property
    def default_cwd(self) -> Path:
        return Path(self.env.default_cwd)

    @property
    def llm_timeout(self) -> float:
        return self.module.llm.timeout

    @property
    def llm_max_tokens(self) -> int:
        return self.module.llm.max_tokens

    @property
    def claude_display_name(self) -> str:
        return self.module.llm.claude_display_name

    @property
    def tts_enabled(self) -> bool:
        return self.module.tts.enabled

    @property
    def tts_timeout(self) -> float:
        return self.module.tts.timeout


# Global config instance
config = Config()
