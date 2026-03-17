from __future__ import annotations

import pytest

from rotorlab_app.models.propeller import ADVANCED_PROPELLER_MODULE_TYPE
from rotorlab_app.ui.advanced_propeller import AdvancedPropellerWorkspace
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


def _drop_propeller_module(window: RotorLabMainWindow) -> str:
    scene = window.orchestrate.scene
    scene.begin_module_drag()
    target = next(
        candidate
        for candidate in scene.overlay_targets()
        if candidate.kind == WorkflowCanvasScene.PLACEMENT_EMPTY and candidate.row == 0 and candidate.col == 0
    )
    point = scene.overlay_center_for_target(target)
    assert point is not None
    scene.update_drag_position(point)
    assert window.orchestrate.canvas.drop_module_at_scene_point(
        "Propeller Parametric Builder",
        point,
        "Geometry",
        ADVANCED_PROPELLER_MODULE_TYPE,
    )
    node_id = scene.node_id_by_name("Propeller Parametric Builder")
    assert node_id is not None
    return node_id


def test_propeller_snapshot_uses_stable_module_type_and_payload(window):
    node_id = _drop_propeller_module(window)
    snapshot = window.orchestrate.scene.snapshot()
    module = next(module for module in snapshot.modules if module.id == node_id)
    assert module.module_type == ADVANCED_PROPELLER_MODULE_TYPE
    assert module.payload == {"environment": "advanced_propeller"}


def test_propeller_node_activation_opens_and_reuses_advanced_environment(window, qtbot):
    node_id = _drop_propeller_module(window)

    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(350)

    assert window.environment_tabs.count() == 2
    assert window.environment_tabs.tabText(1) == "Advanced Propeller: Propeller Parametric Builder"
    assert isinstance(window.workspace_stack.currentWidget(), AdvancedPropellerWorkspace)

    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(50)
    assert window.environment_tabs.count() == 2


def test_advanced_propeller_workspace_builds_preview_and_updates_after_edit(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(400)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    initial_faces = workspace.viewport.mesh_face_count()
    assert initial_faces > 0
    assert workspace.diagnostic_list.count() > 0

    workspace._update_global("num_blades", 5, "blade_preview")
    qtbot.wait(400)

    assert workspace.viewport.mesh_face_count() > initial_faces
    assert workspace.session.feature_state.dirty_stages == []
