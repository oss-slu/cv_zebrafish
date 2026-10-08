"""Mouse analysis workflow (issue #118).

Kept separate from the zebrafish code: nothing in this package imports from
``core`` or ``ui.main_panels``, and zebrafish modules must not import from here.
Shared UI helpers (``ui.components``, ``styles``, ``app_platform``) are fine to reuse.
"""

from mouse.mouse_analysis_page import DLC_FILE_FILTER, MouseAnalysisPage

__all__ = ["DLC_FILE_FILTER", "MouseAnalysisPage"]
