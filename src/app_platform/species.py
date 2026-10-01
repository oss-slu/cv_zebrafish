"""Species selection for the landing page (issue #117).

Keeps the chosen species as a real value instead of hard-coded strings, so
later code (routing, future mouse-specific modules) can read it directly.
"""

from __future__ import annotations

from enum import Enum


class Species(Enum):
    ZEBRAFISH = "zebrafish"
    MOUSE = "mouse"

    @property
    def display_name(self) -> str:
        """Label shown in the dropdown."""
        return "Zebrafish" if self is Species.ZEBRAFISH else "Mouse"