"""Plugin Loader - Load plugins from various sources.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from roadgateway_core.plugins.base import Plugin, PluginConfig

logger = logging.getLogger(__name__)


class PluginLoader(ABC):
    """Abstract plugin loader."""

    @abstractmethod
    def load(self) -> List[Plugin]:
        """Load plugins."""
        pass


@dataclass
class PluginManifest:
    """Plugin manifest information."""

    name: str
    version: str
    description: str = ""
    entry_point: str = ""
    config_schema: Dict[str, Any] = None


class FilePluginLoader(PluginLoader):
    """Load plugins from Python files."""

    def __init__(
        self,
        paths: List[str],
        config: Optional[Dict[str, PluginConfig]] = None,
    ):
        self.paths = paths
        self.config = config or {}

    def load(self) -> List[Plugin]:
        """Load plugins from configured paths."""
        plugins = []

        for path in self.paths:
            path = Path(path)
            
            if path.is_file():
                plugin = self._load_file(path)
                if plugin:
                    plugins.append(plugin)
            elif path.is_dir():
                for file in path.glob("*.py"):
                    if not file.name.startswith("_"):
                        plugin = self._load_file(file)
                        if plugin:
                            plugins.append(plugin)

        return plugins

    def _load_file(self, path: Path) -> Optional[Plugin]:
        """Load a plugin from a Python file."""
        try:
            spec = importlib.util.spec_from_file_location(
                path.stem, path
            )
            if not spec or not spec.loader:
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find Plugin subclass
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Plugin)
                    and attr is not Plugin
                ):
                    config = self.config.get(attr.name)
                    return attr(config)

        except Exception as e:
            logger.error(f"Failed to load plugin from {path}: {e}")

        return None


class ModulePluginLoader(PluginLoader):
    """Load plugins from Python modules."""

    def __init__(
        self,
        modules: List[str],
        config: Optional[Dict[str, PluginConfig]] = None,
    ):
        self.modules = modules
        self.config = config or {}

    def load(self) -> List[Plugin]:
        """Load plugins from modules."""
        plugins = []

        for module_name in self.modules:
            try:
                module = importlib.import_module(module_name)
                
                # Find Plugin subclass
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, Plugin)
                        and attr is not Plugin
                    ):
                        config = self.config.get(attr.name)
                        plugins.append(attr(config))

            except Exception as e:
                logger.error(f"Failed to load plugin module {module_name}: {e}")

        return plugins


class EntryPointPluginLoader(PluginLoader):
    """Load plugins from entry points (setuptools)."""

    def __init__(
        self,
        group: str = "roadgateway.plugins",
        config: Optional[Dict[str, PluginConfig]] = None,
    ):
        self.group = group
        self.config = config or {}

    def load(self) -> List[Plugin]:
        """Load plugins from entry points."""
        plugins = []

        try:
            from importlib.metadata import entry_points
            
            eps = entry_points()
            # Handle both old and new API
            if hasattr(eps, 'select'):
                plugin_eps = eps.select(group=self.group)
            else:
                plugin_eps = eps.get(self.group, [])

            for ep in plugin_eps:
                try:
                    plugin_class = ep.load()
                    if issubclass(plugin_class, Plugin):
                        config = self.config.get(plugin_class.name)
                        plugins.append(plugin_class(config))
                except Exception as e:
                    logger.error(f"Failed to load entry point {ep.name}: {e}")

        except ImportError:
            logger.warning("importlib.metadata not available")

        return plugins


class CompositePluginLoader(PluginLoader):
    """Combine multiple plugin loaders."""

    def __init__(self, loaders: List[PluginLoader]):
        self.loaders = loaders

    def load(self) -> List[Plugin]:
        """Load from all loaders."""
        plugins = []
        seen = set()

        for loader in self.loaders:
            for plugin in loader.load():
                if plugin.name not in seen:
                    plugins.append(plugin)
                    seen.add(plugin.name)

        return plugins


__all__ = [
    "PluginLoader",
    "FilePluginLoader",
    "ModulePluginLoader",
    "EntryPointPluginLoader",
    "CompositePluginLoader",
    "PluginManifest",
]
