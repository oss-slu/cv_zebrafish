"""Tests for labeling controller rename."""

from ui.components.pose.labeling_controller import LabelingController
from core.pose.labeling.schema import default_lab_schema


def test_rename_bodypart():
    ctrl = LabelingController()
    ctrl.dataset.schema = default_lab_schema()
    ctrl.dataset.set_point(0, "Head", 1.0, 2.0)
    ctrl.active_bodypart = "Head"
    assert ctrl.rename_bodypart("Head", "Snout")
    assert ctrl.dataset.get_point(0, "Snout") == (1.0, 2.0)
    assert ctrl.active_bodypart == "Snout"
    assert "Snout" in ctrl.dataset.bodyparts()
    assert not ctrl.rename_bodypart("Snout", "BF")


def test_switch_bodypart_keeps_current_frame():
    ctrl = LabelingController()
    ctrl.dataset.schema = default_lab_schema()
    ctrl.frame_queue = [0, 100, 200, 300]
    ctrl.active_bodypart = "Head"
    ctrl.place_active_point(1.0, 2.0)
    ctrl.place_active_point(3.0, 4.0)
    assert ctrl.queue_index == 2
    ctrl.set_active_bodypart("BF")
    assert ctrl.active_bodypart == "BF"
    assert ctrl.queue_index == 2
    assert ctrl.current_frame_index() == 200


def test_go_prev_next_frame():
    ctrl = LabelingController()
    ctrl.dataset.schema = default_lab_schema()
    ctrl.frame_queue = [0, 100, 200, 300]
    ctrl.queue_index = 2
    ctrl.go_next_frame()
    assert ctrl.queue_index == 3
    assert ctrl.current_frame_index() == 300
    ctrl.go_next_frame()
    assert ctrl.queue_index == 3
    ctrl.go_prev_frame()
    assert ctrl.queue_index == 2
    assert ctrl.current_frame_index() == 200
    ctrl.go_prev_frame()
    ctrl.go_prev_frame()
    assert ctrl.queue_index == 0


def test_auto_advance_off_keeps_queue_index():
    ctrl = LabelingController()
    ctrl.dataset.schema = default_lab_schema()
    ctrl.frame_queue = [0, 100, 200]
    ctrl.active_bodypart = "Head"
    ctrl.auto_advance_frames = False
    ctrl.place_active_point(1.0, 2.0)
    assert ctrl.queue_index == 0
    assert ctrl.current_frame_index() == 0
    ctrl.auto_advance_frames = True
    ctrl.place_active_point(3.0, 4.0)
    assert ctrl.queue_index == 1


def test_delete_active_point_on_current_frame():
    ctrl = LabelingController()
    ctrl.dataset.schema = default_lab_schema()
    ctrl.frame_queue = [0, 100]
    ctrl.active_bodypart = "Head"
    ctrl.dataset.set_point(0, "Head", 1.0, 2.0)
    assert ctrl.delete_active_point()
    assert ctrl.dataset.get_point(0, "Head") is None
    assert not ctrl.delete_active_point()


def test_place_active_point_advances_queue_only():
    ctrl = LabelingController()
    ctrl.dataset.schema = default_lab_schema()
    ctrl.frame_queue = [0, 1]
    ctrl.queue_index = 1
    ctrl.active_bodypart = "Head"
    ctrl.place_active_point(10.0, 20.0)
    assert ctrl.active_bodypart == "Head"
    assert ctrl.queue_index == 1


def test_remove_bodypart_tail_point():
    ctrl = LabelingController()
    ctrl.dataset.schema = default_lab_schema()
    assert ctrl.remove_bodypart("T5")
    assert "T5" not in ctrl.dataset.bodyparts()
    assert len(ctrl.dataset.bodyparts()) == 10


def test_add_and_remove_bone():
    ctrl = LabelingController()
    ctrl.dataset.schema.bodyparts = ["A", "B", "C"]
    ctrl.dataset.schema.edges = []
    assert ctrl.add_bone("A", "B")
    assert ("A", "B") in ctrl.bone_name_pairs()
    assert not ctrl.add_bone("A", "B")
    assert ctrl.remove_bone("A", "B")
    assert ctrl.bone_name_pairs() == []


def test_add_bone_exits_bone_mode_and_restores_selection():
    ctrl = LabelingController()
    ctrl.dataset.schema.bodyparts = ["A", "B", "C"]
    ctrl.dataset.schema.edges = []
    ctrl.active_bodypart = "A"
    ctrl.enter_bone_mode()
    assert ctrl.bone_mode
    assert ctrl.active_bodypart is None
    assert ctrl.add_bone("B", "C")
    assert not ctrl.bone_mode
    assert ctrl.active_bodypart == "A"


def test_reorder_bodypart_preserves_edges_by_name():
    ctrl = LabelingController()
    ctrl.dataset.schema.bodyparts = ["A", "B", "C"]
    ctrl.dataset.schema.edges = []
    ctrl.add_bone("A", "C")
    assert ctrl.reorder_bodypart("C", 0)
    assert ctrl.dataset.bodyparts() == ["C", "A", "B"]
    assert ("C", "A") in ctrl.bone_name_pairs()


def test_remove_bodypart_drops_incident_bones():
    ctrl = LabelingController()
    ctrl.dataset.schema = default_lab_schema()
    ctrl.dataset.schema.edges = []
    ctrl.add_bone("Head", "BF")
    ctrl.remove_bodypart("BF")
    assert ("Head", "BF") not in ctrl.bone_name_pairs()
