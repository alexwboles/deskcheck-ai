"""Shared trust boundaries: bounded YAML, literal arguments and contained files."""
from __future__ import annotations

import ntpath
import os
from pathlib import Path
import re
import tempfile

import yaml

from .errors import ParseError, PermissionDenied

MAX_TEXT = 10000
KEYS = {"Enter", "Return", "Tab", "Escape", "Backspace", "Delete", "Left",
        "Right", "Up", "Down", "Home", "End", "PageUp", "PageDown", "Space"}
KEYS.update(f"F{i}" for i in range(1, 13))


class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise ParseError("YAML aliases are not supported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ParseError("YAML mapping keys must be unique strings")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def load_yaml(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 1024 * 1024:
        raise ParseError("YAML exceeds the 1 MiB limit")
    try:
        return yaml.load(text, Loader=StrictLoader)
    except (yaml.YAMLError, RecursionError, ValueError) as exc:
        raise ParseError("Invalid or excessively nested YAML") from exc


def safe_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name):
        raise ParseError("Names must use 1-80 ASCII letters, digits, underscores or hyphens")
    return name


def literal_text(text):
    if not isinstance(text, str) or len(text) > MAX_TEXT or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ParseError("Text must be literal printable text, at most 10000 characters; use named keys for controls")
    return text


def named_key(key):
    if not isinstance(key, str) or key not in KEYS:
        raise ParseError("Unsupported key; use a documented single named key, not scripts or chords")
    return key


def contained(root, relative):
    """Resolve under an operator-selected root; reject cross-platform escapes."""
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise PermissionDenied("Invalid output path")
    if ntpath.splitdrive(relative)[0] or relative.startswith(("/", "\\")) or ":" in relative:
        raise PermissionDenied("Absolute paths and alternate streams are not allowed")
    parts = relative.replace("\\", "/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise PermissionDenied("Path traversal is not allowed")
    base = Path(root).resolve()
    if Path(root).absolute() != base:
        raise PermissionDenied("Selected root must not pass through links/junctions")
    result = base.joinpath(*parts)
    # Reject links/junctions even when they happen to point within the root.
    cursor = result
    while cursor != base:
        if cursor.is_symlink() or cursor.exists() and getattr(cursor.lstat(),"st_file_attributes",0) & 0x400:
            raise PermissionDenied("Linked output paths are not allowed")
        cursor = cursor.parent
    if not result.resolve().is_relative_to(base):
        raise PermissionDenied("Path leaves the selected root")
    return result


def atomic_bytes(path, data, *, replace=False):
    """No silent overwrite; explicit baseline acceptance uses atomic replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise PermissionDenied("Refusing linked file")
    if not replace:
        with path.open("xb") as fh:
            fh.write(data)
        return
    fd, temp = tempfile.mkstemp(prefix=".deskcheck-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
