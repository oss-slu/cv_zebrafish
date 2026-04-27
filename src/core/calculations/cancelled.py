"""User-initiated cancellation of long calculation work (cooperative, checked on the run path)."""


class CalculationAborted(Exception):
    """Raised when the user stops a calculation before it completes."""

    pass
