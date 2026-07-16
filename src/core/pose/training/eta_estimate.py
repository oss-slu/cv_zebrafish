"""Wall-clock ETA helpers for pose training and analyze progress."""

from __future__ import annotations


def format_duration(seconds: int) -> str:
    """Format seconds as a short human-readable duration."""
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if secs:
            return f"{hours}h {minutes}m {secs}s"
        return f"{hours}h {minutes}m"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m {secs}s"


def estimate_remaining_seconds(
    elapsed_s: float,
    completed: int,
    total: int,
) -> int | None:
    """Linear wall-clock ETA from completed steps (epochs, frames, etc.)."""
    if completed <= 0 or total <= completed:
        return None
    return max(0, int(elapsed_s / completed * (total - completed)))
