from __future__ import annotations

import pytest

from rotorlab_app.models.propeller import (
    ADVANCED_PROPELLER_MODULE_TYPE,
    STAGE_ORDER,
    PropellerPreviewRequestDTO,
    create_default_propeller_feature_state,
)
from rotorlab_app.services.propeller_preview_engine import PythonPropellerPreviewBackend
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


def test_advanced_propeller_workspace_build_exact_builds_exact_artifacts(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(400)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)

    assert workspace.handle_action("Build Exact")
    qtbot.wait(400)

    assert workspace.session.last_result is not None
    artifacts = workspace.session.last_result.exact_artifacts
    assert artifacts["mode"] == "exact"
    assert artifacts["exact_stages_built"] == ["blade_surface", "tip"]
    assert artifacts["pending_exact_stages"] == ["hub", "pattern"]
    assert "blade_surface" in artifacts
    assert "tip_surface" in artifacts
    assert artifacts["blade_surface"]["estimated_area"] >= 0.0
    assert artifacts["tip_surface"]["estimated_area"] >= 0.0
    assert workspace.session.feature_state.dirty_stages == []


def test_python_fallback_exact_mode_includes_exact_artifacts() -> None:
    state = create_default_propeller_feature_state("node-exact", "Propeller Exact")
    request = PropellerPreviewRequestDTO(
        feature_state=state,
        dirty_stages=list(STAGE_ORDER),
        build_mode="exact",
    )

    result = PythonPropellerPreviewBackend().rebuild_preview(request)

    assert result.exact_artifacts["mode"] == "exact"
    assert result.exact_artifacts["exact_stages_built"] == ["blade_surface", "tip"]
    assert result.exact_artifacts["pending_exact_stages"] == ["hub", "pattern"]
    assert result.exact_artifacts["blade_count"] == state.global_parameters.num_blades
    assert result.exact_artifacts["vertex_count"] == len(result.mesh.vertices)
    assert result.exact_artifacts["face_count"] == len(result.mesh.faces)
    assert result.exact_artifacts["blade_surface"]["engine"] == "python-fallback"
    assert result.exact_artifacts["tip_surface"]["engine"] == "python-fallback"
