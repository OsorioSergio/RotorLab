from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from rotorlab_app.ui.main_window import RotorLabMainWindow
from rotorlab_app.ui.orchestrate import WorkflowCanvasScene
from rotorlab_app.ui.typography import default_typography_profile


@pytest.fixture
def window(qtbot):
    main_window = RotorLabMainWindow(typography_profile=default_typography_profile())
    qtbot.addWidget(main_window)
    main_window.show()
    qtbot.wait(50)
    return main_window


def _drop_module(
    window: RotorLabMainWindow,
    name: str,
    category: str,
    target_kind: str,
    row: int,
    col: int,
) -> None:
    scene = window.orchestrate.scene
    target = next(
        candidate
        for candidate in scene.overlay_targets()
        if candidate.kind == target_kind and candidate.row == row and candidate.col == col
    )
    point = scene.overlay_center_for_target(target)
    assert point is not None
    scene.update_drag_position(point)
    assert window.orchestrate.canvas.drop_module_at_scene_point(name, point, category)


def test_port_visibility_by_module_capability(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_module(window, "Geom", "Geometry", WorkflowCanvasScene.PLACEMENT_EMPTY, 0, 0)

    scene.begin_module_drag()
    _drop_module(window, "AnalysisA", "Analysis", WorkflowCanvasScene.PLACEMENT_COLUMN, 0, 1)

    scene.begin_module_drag()
    _drop_module(window, "ResultA", "Results", WorkflowCanvasScene.PLACEMENT_COLUMN, 0, 2)

    geom_id = scene.node_id_by_name("Geom")
    analysis_id = scene.node_id_by_name("AnalysisA")
    result_id = scene.node_id_by_name("ResultA")
    assert geom_id is not None
    assert analysis_id is not None
    assert result_id is not None

    assert not scene.has_input_port(geom_id)
    assert scene.has_output_port(geom_id)
    assert scene.has_input_port(analysis_id)
    assert scene.has_output_port(analysis_id)
    assert scene.has_input_port(result_id)
    assert not scene.has_output_port(result_id)


def test_create_and_delete_connection_emits_graph_updates(window, qtbot):
    scene = window.orchestrate.scene
    canvas = window.orchestrate.canvas
    snapshots = []
    scene.graph_changed.connect(snapshots.append)

    scene.begin_module_drag()
    _drop_module(window, "Geom", "Geometry", WorkflowCanvasScene.PLACEMENT_EMPTY, 0, 0)
    scene.begin_module_drag()
    _drop_module(window, "AnalysisA", "Analysis", WorkflowCanvasScene.PLACEMENT_COLUMN, 0, 1)

    geom_id = scene.node_id_by_name("Geom")
    analysis_id = scene.node_id_by_name("AnalysisA")
    assert geom_id is not None
    assert analysis_id is not None

    assert scene.create_connection(geom_id, analysis_id)
    qtbot.wait(20)
    assert snapshots
    assert len(snapshots[-1].connections) == 1

    connection_item = next(iter(scene._connection_items.values()))
    connection_item.setSelected(True)
    canvas.setFocus()
    qtbot.keyPress(canvas, Qt.Key.Key_Delete)
    qtbot.wait(20)
    assert scene.connection_count() == 0
    assert len(snapshots[-1].connections) == 0


def test_connection_rules_fanout_fanin_direction_and_compatibility(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_module(window, "Geom", "Geometry", WorkflowCanvasScene.PLACEMENT_EMPTY, 0, 0)
    scene.begin_module_drag()
    _drop_module(window, "AnalysisA", "Analysis", WorkflowCanvasScene.PLACEMENT_COLUMN, 0, 1)
    scene.begin_module_drag()
    _drop_module(window, "AnalysisB", "Analysis", WorkflowCanvasScene.PLACEMENT_COLUMN, 0, 2)
    scene.begin_module_drag()
    _drop_module(window, "SimAlt", "Simulation", WorkflowCanvasScene.PLACEMENT_ROW, 1, 0)
    scene.begin_module_drag()
    _drop_module(window, "ResultSink", "Results", WorkflowCanvasScene.PLACEMENT_COLUMN, 0, 3)

    geom_id = scene.node_id_by_name("Geom")
    analysis_a_id = scene.node_id_by_name("AnalysisA")
    analysis_b_id = scene.node_id_by_name("AnalysisB")
    sim_alt_id = scene.node_id_by_name("SimAlt")
    result_id = scene.node_id_by_name("ResultSink")
    assert all(node_id is not None for node_id in (geom_id, analysis_a_id, analysis_b_id, sim_alt_id, result_id))

    assert scene.create_connection(geom_id, analysis_a_id)
    assert scene.create_connection(geom_id, analysis_b_id)
    assert not scene.create_connection(sim_alt_id, analysis_a_id)  # single fan-in block
    assert not scene.create_connection(analysis_b_id, geom_id)  # right-to-left block
    assert not scene.create_connection(geom_id, result_id)  # incompatible category mapping


def test_connection_path_updates_when_nodes_shift(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_module(window, "Geom", "Geometry", WorkflowCanvasScene.PLACEMENT_EMPTY, 0, 0)
    scene.begin_module_drag()
    _drop_module(window, "AnalysisA", "Analysis", WorkflowCanvasScene.PLACEMENT_COLUMN, 0, 1)

    geom_id = scene.node_id_by_name("Geom")
    analysis_id = scene.node_id_by_name("AnalysisA")
    assert geom_id is not None
    assert analysis_id is not None
    assert scene.create_connection(geom_id, analysis_id)

    connection_item = next(iter(scene._connection_items.values()))
    before_right = connection_item.path().boundingRect().right()

    scene.begin_module_drag()
    _drop_module(window, "FilterMid", "Filter", WorkflowCanvasScene.PLACEMENT_COLUMN, 0, 1)
    after_item = next(iter(scene._connection_items.values()))
    after_right = after_item.path().boundingRect().right()

    assert scene.connection_count() == 1
    assert after_right > before_right

    snapshot = scene.snapshot()
    assert len(snapshot.connections) == 1
    assert snapshot.connections[0].source.node_id == geom_id
    assert snapshot.connections[0].target.node_id == analysis_id
    assert snapshot.connections[0].artifact_kind == "geometry"
