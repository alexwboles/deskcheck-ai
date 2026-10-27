"""YAML test-file parser. Steps are DATA, never code.

There is deliberately no shell/exec/run/command step type. The parser
rejects any unknown step type, any unknown key (at top level or inside a
step), and any non-step content (e.g. a stray ``exec:`` / ``shell:`` key)
with a clear ParseError naming the offending key, so a malformed or
hostile test file fails before anything runs.
"""
from __future__ import annotations

import yaml

from .errors import ParseError

TOP_KEYS = {"version", "name", "app", "steps"}
REQUIRED_TOP = {"version", "name", "app", "steps"}

# step type -> allowed keys (besides "type") and required keys
STEP_SPECS = {
    "launch": ({"app"}, {"app"}),
    "wait": ({"ms", "window"}, set()),
    "click": ({"x", "y"}, {"x", "y"}),
    "type": ({"text"}, {"text"}),
    "key": ({"key"}, {"key"}),
    "screenshot": ({"name"}, {"name"}),
    "assert": ({"kind", "window", "screenshot", "baseline", "tolerance",
                "max_diff_ratio"}, {"kind"}),
}
ASSERT_KINDS = {"window-visible", "screenshot-saved", "pixel-diff"}
# Keys that look like code execution; rejected with an explicit message
# even when they appear outside a step.
FORBIDDEN_KEYS = {"shell", "exec", "command", "run", "eval", "system",
                  "subprocess", "script", "code", "import", "os_system"}


def _reject_forbidden(obj, where):
    if isinstance(obj, dict):
        for k in obj:
            if k in FORBIDDEN_KEYS:
                raise ParseError(
                    f"{where}: forbidden key '{k}' — test steps are data, "
                    "never code; there is no shell/exec step in deskcheck")
            _reject_forbidden(obj[k], where)
    elif isinstance(obj, list):
        for item in obj:
            _reject_forbidden(item, where)


def _check_int(value, field, where):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParseError(f"{where}: '{field}' must be an integer, got {value!r}")
    return value


def _check_str(value, field, where):
    if not isinstance(value, str) or not value:
        raise ParseError(f"{where}: '{field}' must be a non-empty string, got {value!r}")
    return value


def parse_test(text: str, source: str = "<test>") -> dict:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ParseError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError(f"{source}: test file must be a YAML mapping, got "
                         f"{type(data).__name__}")
    _reject_forbidden(data, source)
    unknown = set(data) - TOP_KEYS
    if unknown:
        raise ParseError(f"{source}: unknown top-level key(s): "
                         f"{sorted(unknown)} (allowed: {sorted(TOP_KEYS)})")
    missing = REQUIRED_TOP - set(data)
    if missing:
        raise ParseError(f"{source}: missing top-level key(s): {sorted(missing)}")
    if data["version"] not in (1, "1", "1.0"):
        raise ParseError(f"{source}: unsupported version {data['version']!r} (expected 1)")
    _check_str(data["name"], "name", source)
    _check_str(data["app"], "app", source)
    steps = data["steps"]
    if not isinstance(steps, list):
        raise ParseError(f"{source}: 'steps' must be a list")
    parsed = []
    for i, raw in enumerate(steps):
        where = f"{source} step {i}"
        if not isinstance(raw, dict):
            raise ParseError(f"{where}: each step must be a mapping, got "
                             f"{type(raw).__name__}")
        _reject_forbidden(raw, where)
        stype = raw.get("type")
        if stype not in STEP_SPECS:
            raise ParseError(
                f"{where}: unknown step type {stype!r} "
                f"(allowed: {sorted(STEP_SPECS)}). There is no shell/exec step.")
        allowed, required = STEP_SPECS[stype]
        unknown_keys = set(raw) - allowed - {"type"}
        if unknown_keys:
            raise ParseError(f"{where} ({stype}): unknown key(s): "
                             f"{sorted(unknown_keys)} (allowed: {sorted(allowed)})")
        missing_keys = required - set(raw)
        if missing_keys:
            raise ParseError(f"{where} ({stype}): missing key(s): {sorted(missing_keys)}")
        step = {"type": stype}
        if stype == "launch":
            step["app"] = _check_str(raw["app"], "app", where)
        elif stype == "wait":
            if "ms" not in raw and "window" not in raw:
                raise ParseError(f"{where} (wait): need 'ms' and/or 'window'")
            if "ms" in raw:
                ms = _check_int(raw["ms"], "ms", where)
                if ms < 0:
                    raise ParseError(f"{where} (wait): 'ms' must be >= 0")
                step["ms"] = ms
            if "window" in raw:
                step["window"] = _check_str(raw["window"], "window", where)
        elif stype == "click":
            for f in ("x", "y"):
                v = _check_int(raw[f], f, where)
                if v < 0:
                    raise ParseError(f"{where} (click): '{f}' must be >= 0")
                step[f] = v
        elif stype == "type":
            if not isinstance(raw["text"], str):
                raise ParseError(f"{where} (type): 'text' must be a string")
            step["text"] = raw["text"]
        elif stype == "key":
            step["key"] = _check_str(raw["key"], "key", where)
        elif stype == "screenshot":
            step["name"] = _check_str(raw["name"], "name", where)
        elif stype == "assert":
            kind = raw["kind"]
            if kind not in ASSERT_KINDS:
                raise ParseError(f"{where} (assert): unknown kind {kind!r} "
                                 f"(allowed: {sorted(ASSERT_KINDS)})")
            step["kind"] = kind
            if kind == "window-visible":
                if "window" not in raw:
                    raise ParseError(f"{where} (assert window-visible): 'window' required")
                step["window"] = _check_str(raw["window"], "window", where)
            elif kind == "screenshot-saved":
                if "screenshot" not in raw:
                    raise ParseError(f"{where} (assert screenshot-saved): 'screenshot' required")
                step["screenshot"] = _check_str(raw["screenshot"], "screenshot", where)
            else:  # pixel-diff
                for f in ("screenshot", "baseline"):
                    if f not in raw:
                        raise ParseError(f"{where} (assert pixel-diff): '{f}' required")
                    step[f] = _check_str(raw[f], f, where)
                for f in ("tolerance", "max_diff_ratio"):
                    if f in raw:
                        v = raw[f]
                        if isinstance(v, bool) or not isinstance(v, (int, float)) \
                                or not (0.0 <= float(v) <= 1.0):
                            raise ParseError(f"{where} (assert pixel-diff): '{f}' "
                                             "must be a number between 0 and 1")
                        step[f] = float(v)
        parsed.append(step)
    return {"version": 1, "name": data["name"], "app": data["app"], "steps": parsed}


def load_test(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return parse_test(fh.read(), source=path)
