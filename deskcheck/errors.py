"""Shared error types for deskcheck-ai."""


class DeskcheckError(Exception):
    """Base error; message is shown to the agent and recorded in the report."""


class ParseError(DeskcheckError):
    """A test file is malformed, or contains a step/key deskcheck does not allow."""


class PermissionDenied(DeskcheckError):
    """An app or input step was blocked by the allowlist (default deny)."""


class DriverUnavailable(DeskcheckError):
    """No usable desktop driver is present on this machine."""


class AssertionFailed(DeskcheckError):
    """An assertion step failed; the run fails (exit 1)."""


class TimeoutError_(DeskcheckError):
    """A step exceeded its timeout (kept distinct from builtin TimeoutError)."""


# Backwards-friendly alias (tests import DeskcheckTimeout).
DeskcheckTimeout = TimeoutError_
