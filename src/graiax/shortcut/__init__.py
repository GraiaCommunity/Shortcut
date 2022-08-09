"""Utilities for Graia Framework Community."""

import contextlib

from .interrupt import AnnotationWaiter as AnnotationWaiter
from .interrupt import EventWaiter as EventWaiter
from .interrupt import FunctionWaiter as FunctionWaiter

with contextlib.suppress(ImportError):
    from .saya import decorate as decorate
    from .saya import dispatch as dispatch
    from .saya import listen as listen
    from .saya import priority as priority

# TODO: message parsers using Amnesia
