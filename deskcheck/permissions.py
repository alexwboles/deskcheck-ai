"""Permission model: named-app allowlist, DEFAULT DENY.

Headline feature. Nothing runs unless it is explicitly allowlisted, and
whole categories are denied no matter what the config says:

* password managers — always denied
* credential stores (keychains, vaults, secret stores) — always denied
* system-settings apps (Settings, Control Panel, registry editors) — always denied
* browsers carrying an existing profile/session — denied unless the entry
  sets ``throwaway_profile: true`` (a fresh, throwaway profile only)

Config denials are checked at launch AND at every input step. Categories
and the throwaway-profile flag are operator assertions, not automatic OS
identity/profile verification. Runner and MCP additionally require the
driver's input-target guard; native input is currently disabled because
its process/window isolation is unverified. See docs/SECURITY.md.
"""
from __future__ import annotations

import yaml

from .errors import PermissionDenied

ALWAYS_DENIED_CATEGORIES = {"password-manager", "credential-store", "system-settings"}
# A browser is only allowlistable with a fresh throwaway profile.
BROWSER_CATEGORY = "browser"


class AppEntry:
    def __init__(self, name, command=None, category="app", throwaway_profile=False):
        self.name = name
        self.command = command
        self.category = category
        self.throwaway_profile = bool(throwaway_profile)

    def denial_reason(self):
        if self.category in ALWAYS_DENIED_CATEGORIES:
            return (f"app '{self.name}' is in denied category "
                    f"'{self.category}' (see docs/SECURITY.md)")
        if self.category == BROWSER_CATEGORY and not self.throwaway_profile:
            return (f"browser '{self.name}' is denied: browsers may only be "
                    "allowlisted with throwaway_profile: true (a fresh "
                    "throwaway profile, never an existing profile/session)")
        return None


class PermissionConfig:
    def __init__(self, apps: dict):
        self.apps = apps  # name -> AppEntry

    @classmethod
    def from_dict(cls, data: dict) -> "PermissionConfig":
        apps = {}
        raw = (data or {}).get("apps") or {}
        if not isinstance(raw, dict):
            raise ValueError("config 'apps' must be a mapping")
        for name, entry in raw.items():
            if not isinstance(entry, dict):
                entry = {"command": entry}
            apps[name] = AppEntry(
                name=name,
                command=entry.get("command"),
                category=entry.get("category", "app"),
                throwaway_profile=entry.get("throwaway_profile", False),
            )
        return cls(apps)

    @classmethod
    def from_file(cls, path: str) -> "PermissionConfig":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(yaml.safe_load(fh.read()) or {})

    @classmethod
    def empty(cls) -> "PermissionConfig":
        return cls({})

    def check_launch(self, name: str) -> AppEntry:
        """Return the entry if launch is allowed, else raise PermissionDenied."""
        entry = self.apps.get(name)
        if entry is None:
            raise PermissionDenied(
                f"launch denied: app '{name}' is not on the allowlist "
                "(default deny — add it to the config to allow it)")
        reason = entry.denial_reason()
        if reason:
            raise PermissionDenied(f"launch denied: {reason}")
        return entry

    def check_input(self, current_app: str | None) -> AppEntry:
        """Input steps are only allowed while an allowlisted app is focused."""
        if not current_app:
            raise PermissionDenied(
                "input denied: no allowlisted app is focused — "
                "launch an allowlisted app first")
        return self.check_launch(current_app)
