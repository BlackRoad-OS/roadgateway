"""Plugin Base - Gateway plugin system.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class PluginHook(Enum):
    """Plugin hook points."""

    STARTUP = auto()
    SHUTDOWN = auto()
    PRE_REQUEST = auto()
    POST_REQUEST = auto()
    PRE_RESPONSE = auto()
    POST_RESPONSE = auto()
    ON_ERROR = auto()
    ON_ROUTE_MATCH = auto()
    ON_BACKEND_SELECT = auto()
    ON_METRICS = auto()


class PluginPriority(Enum):
    """Plugin execution priority."""

    HIGHEST = 0
    HIGH = 25
    NORMAL = 50
    LOW = 75
    LOWEST = 100


@dataclass
class PluginConfig:
    """Plugin configuration."""

    enabled: bool = True
    priority: PluginPriority = PluginPriority.NORMAL
    settings: Dict[str, Any] = field(default_factory=dict)


class Plugin(ABC):
    """Abstract gateway plugin.

    Plugins can hook into various points of request processing
    to add custom functionality.

    Architecture:
    ┌────────────────────────────────────────────────────────────┐
    │                      Plugin System                          │
    ├────────────────────────────────────────────────────────────┤
    │                                                             │
    │  Request ──▶ PRE_REQUEST ──▶ Route ──▶ Backend             │
    │                                          │                  │
    │                                          ▼                  │
    │  Response ◀── POST_RESPONSE ◀── PRE_RESPONSE               │
    │                                                             │
    │  ┌──────────────────────────────────────────────────────┐  │
    │  │                    Plugin Hooks                       │  │
    │  │  STARTUP, SHUTDOWN, PRE_REQUEST, POST_REQUEST,       │  │
    │  │  PRE_RESPONSE, POST_RESPONSE, ON_ERROR,              │  │
    │  │  ON_ROUTE_MATCH, ON_BACKEND_SELECT, ON_METRICS       │  │
    │  └──────────────────────────────────────────────────────┘  │
    └────────────────────────────────────────────────────────────┘
    """

    name: str = "base_plugin"
    version: str = "1.0.0"
    description: str = ""

    def __init__(self, config: Optional[PluginConfig] = None):
        self.config = config or PluginConfig()
        self._enabled = self.config.enabled

    @property
    def is_enabled(self) -> bool:
        """Check if plugin is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable the plugin."""
        self._enabled = True

    def disable(self) -> None:
        """Disable the plugin."""
        self._enabled = False

    def on_startup(self) -> None:
        """Called when gateway starts."""
        pass

    def on_shutdown(self) -> None:
        """Called when gateway shuts down."""
        pass

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called before request processing.
        
        Return modified request or None to continue unchanged.
        Raise exception to abort request.
        """
        return None

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Called after request processing.
        
        Return modified response or None to continue unchanged.
        """
        return None

    def on_error(
        self,
        request: Dict[str, Any],
        error: Exception,
    ) -> Optional[Dict[str, Any]]:
        """Called on error.
        
        Return response dict to handle error, or None to propagate.
        """
        return None


class PluginManager:
    """Manages gateway plugins.

    Features:
    - Plugin registration
    - Priority-based execution
    - Hook dispatching
    - Hot reload support
    """

    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._hooks: Dict[PluginHook, List[Plugin]] = {
            hook: [] for hook in PluginHook
        }
        self._lock = threading.RLock()

    def register(self, plugin: Plugin) -> "PluginManager":
        """Register a plugin."""
        with self._lock:
            self._plugins[plugin.name] = plugin
            self._rebuild_hooks()
        logger.info(f"Registered plugin: {plugin.name} v{plugin.version}")
        return self

    def unregister(self, name: str) -> bool:
        """Unregister a plugin."""
        with self._lock:
            if name in self._plugins:
                del self._plugins[name]
                self._rebuild_hooks()
                return True
        return False

    def get(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def get_all(self) -> List[Plugin]:
        """Get all registered plugins."""
        return list(self._plugins.values())

    def _rebuild_hooks(self) -> None:
        """Rebuild hook lists by priority."""
        for hook in PluginHook:
            self._hooks[hook] = sorted(
                [p for p in self._plugins.values() if p.is_enabled],
                key=lambda p: p.config.priority.value,
            )

    def dispatch(
        self,
        hook: PluginHook,
        *args,
        **kwargs,
    ) -> Optional[Any]:
        """Dispatch a hook to all registered plugins."""
        with self._lock:
            plugins = self._hooks.get(hook, [])

        for plugin in plugins:
            try:
                method = self._get_hook_method(plugin, hook)
                if method:
                    result = method(*args, **kwargs)
                    if result is not None:
                        return result
            except Exception as e:
                logger.error(f"Plugin {plugin.name} error in {hook.name}: {e}")

        return None

    def _get_hook_method(
        self,
        plugin: Plugin,
        hook: PluginHook,
    ) -> Optional[Callable]:
        """Get the method for a hook."""
        method_map = {
            PluginHook.STARTUP: plugin.on_startup,
            PluginHook.SHUTDOWN: plugin.on_shutdown,
            PluginHook.PRE_REQUEST: plugin.pre_request,
            PluginHook.POST_REQUEST: plugin.post_request,
            PluginHook.ON_ERROR: plugin.on_error,
        }
        return method_map.get(hook)

    def startup(self) -> None:
        """Call startup on all plugins."""
        self.dispatch(PluginHook.STARTUP)

    def shutdown(self) -> None:
        """Call shutdown on all plugins."""
        self.dispatch(PluginHook.SHUTDOWN)


# Example plugins

class LoggingPlugin(Plugin):
    """Plugin that logs all requests."""

    name = "logging"
    version = "1.0.0"
    description = "Logs all requests and responses"

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = request.get("method", "?")
        path = request.get("path", "?")
        logger.info(f"Request: {method} {path}")
        return None

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        status = response.get("status", 0)
        logger.info(f"Response: {status}")
        return None


class RequestIDPlugin(Plugin):
    """Plugin that adds request IDs."""

    name = "request_id"
    version = "1.0.0"
    description = "Adds unique request ID to each request"

    def __init__(self, config: Optional[PluginConfig] = None):
        super().__init__(config)
        self._counter = 0

    def pre_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        import uuid
        request_id = str(uuid.uuid4())
        
        headers = request.get("headers", {})
        headers["X-Request-ID"] = request_id
        request["headers"] = headers
        request["request_id"] = request_id
        
        return request


class CompressionPlugin(Plugin):
    """Plugin that handles compression."""

    name = "compression"
    version = "1.0.0"
    description = "Handles request/response compression"

    def post_request(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        # Check if client accepts compression
        accept_encoding = request.get("headers", {}).get("Accept-Encoding", "")
        
        if "gzip" in accept_encoding:
            # Would compress response here
            response.setdefault("headers", {})["Content-Encoding"] = "gzip"

        return response


__all__ = [
    "Plugin",
    "PluginManager",
    "PluginConfig",
    "PluginHook",
    "PluginPriority",
    "LoggingPlugin",
    "RequestIDPlugin",
    "CompressionPlugin",
]
