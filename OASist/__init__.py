"""OASist Client Generator package."""

__all__ = [
    "ClientGenerator",
    "ServiceConfig",
]

from .oasist import ClientGenerator, ServiceConfig  # re-export for convenience

__version__ = "1.0.0"
