from __future__ import annotations

import pytest

import rotorlab_app.services.propeller_preview_bridge as bridge_module
from rotorlab_app.models.propeller import (
    ADVANCED_PROPELLER_MODULE_TYPE,
    ACTIVE_PROPELLER_STAGES,
    create_default_propeller_feature_state,
)
from rotorlab_app.services.propeller_preview_service import PropellerBuildService
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


def _wait_for_result(qtbot, workspace: AdvancedPropellerWorkspace) -> None:
    qtbot.waitUntil(lambda: workspace.session.last_result is not None, timeout=6000)


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


def test_advanced_propeller_workspace_exposes_authoritative_stages_and_builds(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(200)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    _wait_for_result(qtbot, workspace)

    labels = []
    for root_index in range(workspace.stage_tree.topLevelItemCount()):
        root = workspace.stage_tree.topLevelItem(root_index)
        for child_index in range(root.childCount()):
            labels.append(root.child(child_index).text(0))

    assert len(workspace.session.last_result.mesh.faces) > 0
    assert workspace.session.last_result.model_metadata.source == "truck_tessellation"
    assert workspace.session.last_result.model_metadata.component_count >= 5
    assert all(stage in ACTIVE_PROPELLER_STAGES for stage in workspace.session.last_result.built_stages)
    assert "Tip Surface" in labels
    assert "Hub Blend" in labels
    assert "Pattern" in labels


def test_advanced_propeller_workspace_rebuilds_after_pattern_edit(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(200)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    _wait_for_result(qtbot, workspace)

    initial_faces = workspace.viewport.mesh_face_count()
    initial_components = workspace.session.last_result.model_metadata.component_count

    workspace._update_pattern("num_blades", 5, "pattern")
    qtbot.waitUntil(
        lambda: workspace.session.last_result is not None
        and workspace.session.last_result.model_metadata.blade_count == 5,
        timeout=6000,
    )

    assert workspace.viewport.mesh_face_count() > initial_faces
    assert workspace.session.last_result.model_metadata.component_count == initial_components + 1
    assert workspace.session.feature_state.dirty_stages == []


def test_advanced_propeller_workspace_rebuilds_after_tip_and_hub_edits(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(200)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    _wait_for_result(qtbot, workspace)

    initial_apex = tuple(workspace.session.last_result.model_metadata.topology_status["tip_apex"])
    initial_bounds = (
        tuple(workspace.session.last_result.model_metadata.bounds_min),
        tuple(workspace.session.last_result.model_metadata.bounds_max),
    )

    workspace._update_tip("cap_length_ratio", 0.20, "tip")
    qtbot.waitUntil(lambda: workspace.session.feature_state.dirty_stages == [], timeout=6000)
    after_tip_apex = tuple(workspace.session.last_result.model_metadata.topology_status["tip_apex"])
    after_tip_bounds = (
        tuple(workspace.session.last_result.model_metadata.bounds_min),
        tuple(workspace.session.last_result.model_metadata.bounds_max),
    )

    workspace._update_hub("hub_length_ratio", 0.44, "hub")
    qtbot.waitUntil(lambda: workspace.session.feature_state.dirty_stages == [], timeout=6000)
    after_hub_bounds = (
        tuple(workspace.session.last_result.model_metadata.bounds_min),
        tuple(workspace.session.last_result.model_metadata.bounds_max),
    )

    assert after_tip_apex != initial_apex
    assert after_hub_bounds != after_tip_bounds
    assert workspace.session.last_result.model_metadata.source == "truck_tessellation"


def test_default_preview_settings_favor_surface_rendering():
    state = create_default_propeller_feature_state("preview-node", "Propeller")
    assert state.preview_settings.show_mesh
    assert not state.preview_settings.show_wireframe
    assert not state.preview_settings.show_sections


def test_build_service_reports_backend_missing(monkeypatch):
    monkeypatch.setattr(
        bridge_module,
        "_backend_error",
        lambda: "Rust backend is not installed. Run the repo maturin develop flow before using the advanced propeller workspace.",
    )
    service = PropellerBuildService()
    assert not service.using_rust_backend
    assert "not installed" in (service.backend_error or "")


def test_build_service_reports_backend_contract_mismatch(monkeypatch):
    monkeypatch.setattr(
        bridge_module,
        "_backend_error",
        lambda: "Rust backend contract mismatch. Expected rotorlab-propeller-build:2026-03-17.1, got stale.",
    )
    service = PropellerBuildService()
    assert not service.using_rust_backend
    assert "contract mismatch" in (service.backend_error or "")
