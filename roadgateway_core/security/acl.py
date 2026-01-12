"""Access Control List - Permission and authorization management.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class Action(Enum):
    """Common actions."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    EXECUTE = "execute"
    ADMIN = "admin"
    ALL = "*"


class Effect(Enum):
    """Policy effect."""

    ALLOW = auto()
    DENY = auto()


@dataclass
class Permission:
    """A permission definition."""

    resource: str  # Resource pattern (e.g., "users/*", "api/v1/orders")
    action: str    # Action (e.g., "read", "write", "*")
    effect: Effect = Effect.ALLOW
    conditions: Dict[str, Any] = field(default_factory=dict)

    def matches(self, resource: str, action: str) -> bool:
        """Check if permission matches request."""
        # Check resource pattern
        if not fnmatch.fnmatch(resource, self.resource):
            if self.resource != "*":
                return False

        # Check action
        if self.action != "*" and self.action != action:
            return False

        return True


@dataclass
class Role:
    """A role with permissions."""

    name: str
    permissions: List[Permission] = field(default_factory=list)
    parent_roles: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_permission(self, permission: Permission) -> "Role":
        """Add permission to role."""
        self.permissions.append(permission)
        return self

    def has_permission(
        self,
        resource: str,
        action: str,
        resolver: Optional[Callable[[str], "Role"]] = None,
    ) -> bool:
        """Check if role has permission."""
        # Check direct permissions
        for perm in self.permissions:
            if perm.matches(resource, action):
                return perm.effect == Effect.ALLOW

        # Check parent roles
        if resolver:
            for parent_name in self.parent_roles:
                parent = resolver(parent_name)
                if parent and parent.has_permission(resource, action, resolver):
                    return True

        return False


@dataclass
class Policy:
    """An access control policy."""

    name: str
    effect: Effect
    principals: Set[str] = field(default_factory=set)  # Users/roles
    resources: Set[str] = field(default_factory=set)
    actions: Set[str] = field(default_factory=set)
    conditions: Dict[str, Any] = field(default_factory=dict)

    def matches(
        self,
        principal: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Effect]:
        """Check if policy matches request."""
        # Check principal
        principal_match = False
        for p in self.principals:
            if p == "*" or fnmatch.fnmatch(principal, p):
                principal_match = True
                break
        if not principal_match:
            return None

        # Check resource
        resource_match = False
        for r in self.resources:
            if r == "*" or fnmatch.fnmatch(resource, r):
                resource_match = True
                break
        if not resource_match:
            return None

        # Check action
        action_match = "*" in self.actions or action in self.actions
        if not action_match:
            return None

        # Check conditions
        if self.conditions and context:
            if not self._evaluate_conditions(context):
                return None

        return self.effect

    def _evaluate_conditions(self, context: Dict[str, Any]) -> bool:
        """Evaluate policy conditions."""
        for key, expected in self.conditions.items():
            actual = context.get(key)
            
            if isinstance(expected, dict):
                # Condition operators
                if "equals" in expected and actual != expected["equals"]:
                    return False
                if "not_equals" in expected and actual == expected["not_equals"]:
                    return False
                if "in" in expected and actual not in expected["in"]:
                    return False
                if "not_in" in expected and actual in expected["not_in"]:
                    return False
                if "contains" in expected and expected["contains"] not in str(actual):
                    return False
            else:
                if actual != expected:
                    return False

        return True


class AccessControl:
    """Access Control System.

    Features:
    - Role-based access control (RBAC)
    - Policy-based access control
    - Hierarchical roles
    - Resource patterns
    - Conditional permissions

    Architecture:
    ┌────────────────────────────────────────────────────────────┐
    │                    Access Control                           │
    ├────────────────────────────────────────────────────────────┤
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
    │  │    Users     │  │    Roles     │  │  Policies    │     │
    │  │              │──│              │──│              │     │
    │  │ - Identity   │  │ - Perms      │  │ - Effect     │     │
    │  │ - Roles      │  │ - Parents    │  │ - Conditions │     │
    │  └──────────────┘  └──────────────┘  └──────────────┘     │
    │                                                             │
    │  ┌─────────────────────────────────────────────────────┐   │
    │  │                 Permission Check                     │   │
    │  │  Request(user, resource, action)                     │   │
    │  │       │                                              │   │
    │  │       ├──▶ Check user roles                         │   │
    │  │       ├──▶ Check policies (DENY first)              │   │
    │  │       └──▶ Return ALLOW/DENY                        │   │
    │  └─────────────────────────────────────────────────────┘   │
    └────────────────────────────────────────────────────────────┘
    """

    def __init__(self):
        self._roles: Dict[str, Role] = {}
        self._policies: List[Policy] = []
        self._user_roles: Dict[str, Set[str]] = {}
        self._lock = threading.RLock()

    def add_role(self, role: Role) -> "AccessControl":
        """Add a role."""
        with self._lock:
            self._roles[role.name] = role
        return self

    def remove_role(self, name: str) -> bool:
        """Remove a role."""
        with self._lock:
            if name in self._roles:
                del self._roles[name]
                return True
        return False

    def get_role(self, name: str) -> Optional[Role]:
        """Get a role by name."""
        return self._roles.get(name)

    def add_policy(self, policy: Policy) -> "AccessControl":
        """Add a policy."""
        with self._lock:
            self._policies.append(policy)
        return self

    def assign_role(self, user: str, role: str) -> "AccessControl":
        """Assign role to user."""
        with self._lock:
            if user not in self._user_roles:
                self._user_roles[user] = set()
            self._user_roles[user].add(role)
        return self

    def revoke_role(self, user: str, role: str) -> bool:
        """Revoke role from user."""
        with self._lock:
            if user in self._user_roles:
                self._user_roles[user].discard(role)
                return True
        return False

    def get_user_roles(self, user: str) -> Set[str]:
        """Get roles for user."""
        return self._user_roles.get(user, set()).copy()

    def is_allowed(
        self,
        user: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if user is allowed to perform action on resource.

        Uses deny-first policy evaluation:
        1. Check explicit DENY policies
        2. Check ALLOW policies
        3. Default to DENY
        """
        with self._lock:
            # Check policies (deny takes precedence)
            allow_found = False
            
            for policy in self._policies:
                effect = policy.matches(user, resource, action, context)
                
                if effect == Effect.DENY:
                    return False
                elif effect == Effect.ALLOW:
                    allow_found = True

            # Check role-based permissions
            if user in self._user_roles:
                for role_name in self._user_roles[user]:
                    role = self._roles.get(role_name)
                    if role and role.has_permission(
                        resource, action, lambda n: self._roles.get(n)
                    ):
                        allow_found = True

            return allow_found

    def check(
        self,
        user: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Check permission and raise if denied."""
        if not self.is_allowed(user, resource, action, context):
            raise AccessDeniedError(
                f"User '{user}' denied '{action}' on '{resource}'"
            )

    def create_admin_role(self) -> Role:
        """Create an admin role with all permissions."""
        role = Role(name="admin")
        role.add_permission(Permission(resource="*", action="*"))
        self.add_role(role)
        return role

    def create_readonly_role(self, name: str = "readonly") -> Role:
        """Create a read-only role."""
        role = Role(name=name)
        role.add_permission(Permission(resource="*", action="read"))
        role.add_permission(Permission(resource="*", action="list"))
        self.add_role(role)
        return role


class AccessDeniedError(Exception):
    """Access denied error."""
    pass


# Predefined policies
def allow_all_policy() -> Policy:
    """Policy that allows everything."""
    return Policy(
        name="allow_all",
        effect=Effect.ALLOW,
        principals={"*"},
        resources={"*"},
        actions={"*"},
    )


def deny_all_policy() -> Policy:
    """Policy that denies everything."""
    return Policy(
        name="deny_all",
        effect=Effect.DENY,
        principals={"*"},
        resources={"*"},
        actions={"*"},
    )


def ip_whitelist_policy(
    name: str,
    allowed_ips: Set[str],
) -> Policy:
    """Policy that allows only from specific IPs."""
    return Policy(
        name=name,
        effect=Effect.ALLOW,
        principals={"*"},
        resources={"*"},
        actions={"*"},
        conditions={"client_ip": {"in": list(allowed_ips)}},
    )


__all__ = [
    "AccessControl",
    "Permission",
    "Role",
    "Policy",
    "Action",
    "Effect",
    "AccessDeniedError",
    "allow_all_policy",
    "deny_all_policy",
    "ip_whitelist_policy",
]
