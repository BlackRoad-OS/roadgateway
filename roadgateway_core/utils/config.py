"""Configuration utilities.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Config")


class ConfigSource(Enum):
    """Configuration sources."""

    FILE = auto()
    ENV = auto()
    DICT = auto()
    DEFAULT = auto()


@dataclass
class Config:
    """Gateway configuration."""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4
    backlog: int = 1024

    # Timeouts
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    idle_timeout: float = 300.0

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 1000
    rate_limit_period: float = 60.0

    # Health checks
    health_check_enabled: bool = True
    health_check_interval: float = 10.0
    health_check_timeout: float = 5.0

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    access_log: bool = True

    # Security
    cors_enabled: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    ssl_enabled: bool = False
    ssl_cert: str = ""
    ssl_key: str = ""

    # Plugins
    plugins_enabled: bool = True
    plugins_path: str = "./plugins"

    # Metrics
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Create config from dictionary."""
        # Filter to only valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    @classmethod
    def from_json(cls: Type[T], path: str) -> T:
        """Load config from JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_yaml(cls: Type[T], path: str) -> T:
        """Load config from YAML file."""
        try:
            import yaml
            with open(path, "r") as f:
                data = yaml.safe_load(f)
            return cls.from_dict(data)
        except ImportError:
            raise ImportError("PyYAML required for YAML config")

    @classmethod
    def from_env(cls: Type[T], prefix: str = "GATEWAY_") -> T:
        """Load config from environment variables."""
        data = {}
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                
                # Type conversion
                if value.lower() in ("true", "false"):
                    data[config_key] = value.lower() == "true"
                elif value.isdigit():
                    data[config_key] = int(value)
                else:
                    try:
                        data[config_key] = float(value)
                    except ValueError:
                        data[config_key] = value

        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {}
        for field_name in self.__dataclass_fields__:
            result[field_name] = getattr(self, field_name)
        return result

    def merge(self, other: "Config") -> "Config":
        """Merge with another config (other takes precedence)."""
        data = self.to_dict()
        data.update(other.to_dict())
        return Config.from_dict(data)


def load_config(
    path: Optional[str] = None,
    env_prefix: str = "GATEWAY_",
) -> Config:
    """Load configuration from multiple sources.

    Priority (highest to lowest):
    1. Environment variables
    2. Config file (if provided)
    3. Defaults
    """
    config = Config()

    # Load from file if provided
    if path:
        path_obj = Path(path)
        if path_obj.exists():
            if path.endswith(".json"):
                config = Config.from_json(path)
            elif path.endswith((".yaml", ".yml")):
                config = Config.from_yaml(path)
            else:
                logger.warning(f"Unknown config format: {path}")

    # Override with environment variables
    env_config = Config.from_env(env_prefix)
    config = config.merge(env_config)

    return config


__all__ = [
    "Config",
    "ConfigSource",
    "load_config",
]
