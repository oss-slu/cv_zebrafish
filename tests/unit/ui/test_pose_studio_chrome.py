"""Smoke tests for Pose Studio overhaul chrome / scene hierarchy."""



from __future__ import annotations



import sys



import pytest



pytest.importorskip("PyQt5.QtWidgets")



from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QLabel





@pytest.fixture(scope="module")

def qapp():

    app = QApplication.instance()

    if app is None:

        app = QApplication(sys.argv)

    return app





def test_pose_scene_shell_layout(qapp):

    from ui.pose_studio.chrome.scene_shell import PoseSceneShell



    shell = PoseSceneShell(side_width=360)

    assert shell.context_bar is not None

    shell.add_side_widget(QLabel("side"))

    shell.add_main_widget(QLabel("main"))

    shell.add_advanced_widget(QLabel("adv"))

    assert shell.advanced_layout.count() >= 1

    shell.resize(1000, 600)

    shell.show()

    qapp.processEvents()

    shell._ensure_side_sizes(force=True)

    qapp.processEvents()

    sizes = shell._splitter.sizes()

    assert sizes[0] >= 300

    assert sizes[1] >= 200

    assert shell.main_host.x() >= shell.side_host.width() - 2

    handle = shell._splitter.handle(1)

    assert handle is not None

    assert handle.cursor().shape() == Qt.SizeHorCursor

    # Left panel is user-adjustable via the splitter handle.

    shell._splitter.setSizes([360, 640])

    qapp.processEvents()

    assert shell._splitter.sizes()[0] >= 300

    shell.set_advanced_visible(True)

    assert shell._advanced_wrap.isVisible()

    shell.close()





def test_context_bar_chips(qapp):

    from ui.pose_studio.chrome.context_bar import PoseContextBar



    bar = PoseContextBar()

    bar.set_chip("video", label="fish_vid", full_text="fish_vid (2336x1728)", active=True)

    bar.set_chip("labels", label="human_1")

    assert "fish" in bar._labels["video"].text()

    bar.close()





def test_context_bar_compress_and_hover_expand(qapp):

    from ui.pose_studio.chrome.context_bar import PoseContextBar



    bar = PoseContextBar()

    long_label = "human_labels_set_name_xyz"

    full = f"{long_label} — 10/5000 frames"

    bar.set_chip("video", label="active_video_name", full_text="active_video_name (2336x1728)", active=True)

    bar.set_chip("labels", label=long_label, full_text=full)

    assert "…" in bar._labels["labels"].text()

    bar._on_chip_hover_enter("labels")

    assert bar._labels["labels"].text() == full

    bar._on_chip_hover_leave("labels")

    assert "…" in bar._labels["labels"].text()

    bar.close()





def test_context_bar_output_chip(qapp):

    from ui.pose_studio.chrome.context_bar import PoseContextBar



    bar = PoseContextBar()

    bar.set_output_chip(

        label="AI — 4820/4820",

        full_text="Auto label: model_v3 — 4820/4820 frames",

    )

    assert bar._labels["output"].text() == "AI — 4820/4820"

    assert bar._chips["output"].full_text == "Auto label: model_v3 — 4820/4820 frames"

    bar.close()





def test_auto_label_tab_icon(qapp):
    """Icon asset still exists for optional use; Auto Label tab is text-only."""
    from ui.pose_studio.chrome.tab_icons import auto_label_tab_icon

    icon = auto_label_tab_icon()
    # Asset may be present; tab itself no longer sets an icon.
    assert icon is not None

    assert not icon.isNull()





def test_brief_busy_dialog(qapp):

    from ui.pose_studio.chrome.brief_busy_dialog import show_brief_busy_dialog



    parent = QLabel("parent")

    dlg = show_brief_busy_dialog(parent, "Deleting heatmaps…", minimum_ms=0)

    assert dlg.isVisible()

    dlg.finish(minimum_ms=0)

    assert not dlg.isVisible()

    parent.close()





def test_video_scene_import_signals(qapp):

    from ui.pose_studio.scenes.video_scene import VideoScene



    scene = VideoScene()

    hit = {"n": 0}

    scene.upload_video_requested.connect(lambda: hit.__setitem__("n", hit["n"] + 1))

    scene.upload_btn.click()

    assert hit["n"] == 1

    scene.close()





def test_pose_studio_tab_order(qapp):

    from ui.main_panels.pose_studio_panel import PoseStudioPanel



    w = PoseStudioPanel()

    names = [w._tabs.tabText(i) for i in range(w._tabs.count())]

    assert names == ["Video", "Label", "Model", "Auto Label"]

    w.close()


def test_task_progress_bar_activity_label(qapp):
    from ui.pose_studio.chrome.task_progress_bar import TaskProgressBar

    bar = TaskProgressBar()
    bar.set_progress(0, 50, activity="Training Progress", unit="Epochs")
    assert bar._progress_lbl.text() == "Training Progress - 0/50 Epochs"
    bar.set_progress(1, 50)
    assert bar._progress_lbl.text() == "Training Progress - 1/50 Epochs"
    bar.set_busy_message("Preparing training bundle…")
    assert "Preparing training bundle" in bar._progress_lbl.text()
    bar.set_progress(12, 100, activity="Loading playback overlays", unit="frames")
    assert bar._progress_lbl.text() == "Loading playback overlays - 12/100 frames"


