"""Linux native input is unavailable until an app-isolated backend is verified."""
from .base import Driver
from ..errors import DriverUnavailable


class LinuxDriver(Driver):
    name = "linux"

    def __init__(self):
        raise DriverUnavailable("Linux native backend is not supported in this release; use mock or Windows standard controls")
