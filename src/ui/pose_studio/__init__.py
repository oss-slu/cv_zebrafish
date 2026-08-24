"""Pose Studio overhaul — shared chrome and per-scene panels.

Hierarchy
---------
pose_studio/
  chrome/     context bar, scene shell (side | main | advanced), task progress
  scenes/     Start, Video, Label, Model, Auto Label
"""

from ui.pose_studio.chrome.context_bar import PoseContextBar, ContextChip
from ui.pose_studio.chrome.scene_shell import PoseSceneShell
from ui.pose_studio.chrome.task_progress_bar import TaskProgressBar

__all__ = [
    "PoseContextBar",
    "ContextChip",
    "PoseSceneShell",
    "TaskProgressBar",
]
