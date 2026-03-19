from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPolygonF

import rotorlab_app.services.propeller_preview_bridge as bridge_module
import rotorlab_app.ui.advanced_propeller as advanced_propeller_module
from rotorlab_app.models.propeller import (
    ADVANCED_PROPELLER_MODULE_TYPE,
    ACTIVE_PROPELLER_STAGES,
    PropellerBuildRequestDTO,
    create_default_propeller_feature_state,
)
from rotorlab_app.services.propeller_preview_bridge import PropellerBuildBridge
from rotorlab_app.services.propeller_preview_service import PropellerBuildService
from rotorlab_app.ui.advanced_propeller import (
    AdvancedPropellerWorkspace,
    _OVERLAY_DEPTH_BIAS,
    _OVERLAY_PASS_CONFIG,
    _SURFACE_PASS_CONFIG,
    _VIEW_CUBE_DOMINANT_EDGE_AREA,
    _VIEW_CUBE_MIN_CORNER_AREA,
    _VIEW_CUBE_MIN_EDGE_AREA,
    _VIEWPORT_CUBE_BEVEL_HEX,
    _VIEWPORT_CUBE_FACE_HEX,
    _VIEWPORT_BACKGROUND_HEX,
    _VIEWPORT_SURFACE_HEX,
    _VIEW_CUBE_PADDING,
    _VIEW_CUBE_ICON_DIR,
    _VIEW_CUBE_LABEL_TEXTURE_SIZE,
    _VIEW_CUBE_WIDGET_HEIGHT,
    _VIEW_CUBE_WIDGET_WIDTH,
    _build_display_edges,
    _build_view_cube_overlay,
    _camera_state,
    _build_crease_aware_render_geometry,
    _hit_test_view_cube_overlay,
    _named_view_eye_direction,
    _view_cube_label_image,
    _view_cube_label_transform,
)
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


def test_named_view_mapping_uses_true_model_axes():
    assert _named_view_eye_direction("Top") == pytest.approx((0.0, 0.0, 1.0))
    assert _named_view_eye_direction("Front") == pytest.approx((0.0, -1.0, 0.0))
    assert _named_view_eye_direction("Right") == pytest.approx((1.0, 0.0, 0.0))
    iso = _named_view_eye_direction("Top-Front-Right")
    expected = 1.0 / math.sqrt(3.0)
    assert iso == pytest.approx((expected, -expected, expected))


def test_view_cube_overlay_exposes_visible_faces_and_hit_targets():
    overlay = _build_view_cube_overlay(
        _camera_state((0.0, 0.0, 0.0), 4.0, -45.0, 35.26438968),
        900.0,
        700.0,
    )
    visible_faces = {face.view_name for face in overlay.faces}
    assert {"Top", "Front", "Right"}.issubset(visible_faces)
    assert {panel.view_name for panel in overlay.edge_panels} >= {"Top-Front", "Top-Right", "Front-Right"}
    visible_corners = {panel.view_name for panel in overlay.corner_panels}
    assert "Top-Front-Right" in visible_corners
    assert len(visible_corners) > 1

    top_face = next(face for face in overlay.faces if face.view_name == "Top")
    centroid = (
        sum(point[0] for point in top_face.polygon) / len(top_face.polygon),
        sum(point[1] for point in top_face.polygon) / len(top_face.polygon),
    )
    target = _hit_test_view_cube_overlay(overlay, centroid)
    assert target is not None
    assert target.action == "snap"
    assert target.view_name == "Top"


def test_view_cube_hit_test_ignores_points_outside_overlay():
    overlay = _build_view_cube_overlay(
        _camera_state((0.0, 0.0, 0.0), 4.0, -45.0, 35.26438968),
        900.0,
        700.0,
    )
    assert _hit_test_view_cube_overlay(overlay, (24.0, 24.0)) is None


def test_view_cube_edge_and_corner_hotspots_resolve_expected_named_views():
    overlay = _build_view_cube_overlay(
        _camera_state((0.0, 0.0, 0.0), 4.0, -45.0, 35.26438968),
        900.0,
        700.0,
    )
    edge_panel = next(panel for panel in overlay.edge_panels if panel.view_name == "Top-Front")
    edge_center = (
        sum(point[0] for point in edge_panel.polygon) / len(edge_panel.polygon),
        sum(point[1] for point in edge_panel.polygon) / len(edge_panel.polygon),
    )
    edge_target = _hit_test_view_cube_overlay(overlay, edge_center)
    assert edge_target is not None
    assert edge_target.view_name == "Top-Front"

    corner_panel = next(panel for panel in overlay.corner_panels if panel.view_name == "Top-Front-Right")
    corner_center = (
        sum(point[0] for point in corner_panel.polygon) / len(corner_panel.polygon),
        sum(point[1] for point in corner_panel.polygon) / len(corner_panel.polygon),
    )
    corner_target = _hit_test_view_cube_overlay(overlay, corner_center)
    assert corner_target is not None
    assert corner_target.view_name == "Top-Front-Right"


def test_view_cube_label_transform_maps_text_center_inside_face_polygon():
    overlay = _build_view_cube_overlay(
        _camera_state((0.0, 0.0, 0.0), 4.0, -45.0, 35.26438968),
        900.0,
        700.0,
    )
    top_face = next(face for face in overlay.faces if face.view_name == "Top")
    mapped_center = _view_cube_label_transform(top_face).map(QPointF(0.5, 0.5))
    polygon = QPolygonF(QPointF(point[0], point[1]) for point in top_face.polygon)

    assert polygon.containsPoint(mapped_center, Qt.FillRule.WindingFill)


def test_view_cube_label_transform_stays_on_face_across_multiple_orientations():
    for view_name in (
        "Top-Front-Right",
        "Top-Back-Left",
        "Bottom-Front-Left",
        "Bottom-Back-Right",
    ):
        eye_direction = _named_view_eye_direction(view_name)
        overlay = _build_view_cube_overlay(
            _camera_state(
                (0.0, 0.0, 0.0),
                4.0,
                math.degrees(math.atan2(eye_direction[1], eye_direction[0])),
                math.degrees(math.asin(eye_direction[2])),
            ),
            900.0,
            700.0,
        )

        for face in overlay.faces:
            transform = _view_cube_label_transform(face)
            polygon = QPolygonF(QPointF(point[0], point[1]) for point in face.polygon)
            for sample in (QPointF(0.35, 0.5), QPointF(0.5, 0.5), QPointF(0.65, 0.5)):
                assert polygon.containsPoint(transform.map(sample), Qt.FillRule.WindingFill)


def test_view_cube_default_label_quads_have_readable_screen_extent():
    overlay = _build_view_cube_overlay(
        _camera_state((0.0, 0.0, 0.0), 4.0, -45.0, 35.26438968),
        900.0,
        700.0,
    )
    top_face = next(face for face in overlay.faces if face.view_name == "Top")
    front_face = next(face for face in overlay.faces if face.view_name == "Front")

    top_width = max(point[0] for point in top_face.label_quad) - min(point[0] for point in top_face.label_quad)
    top_height = max(point[1] for point in top_face.label_quad) - min(point[1] for point in top_face.label_quad)
    front_width = max(point[0] for point in front_face.label_quad) - min(point[0] for point in front_face.label_quad)
    front_height = max(point[1] for point in front_face.label_quad) - min(point[1] for point in front_face.label_quad)

    assert top_width > 23.0
    assert top_height > 10.0
    assert front_width > 15.0
    assert front_height > 18.0


def test_view_cube_label_images_render_at_supersampled_resolution():
    image = _view_cube_label_image("TOP", "Segoe UI")
    assert image.width() == _VIEW_CUBE_LABEL_TEXTURE_SIZE
    assert image.height() == _VIEW_CUBE_LABEL_TEXTURE_SIZE


def test_view_cube_projection_stays_within_overlay_bounds_across_orientations():
    for view_name in (
        "Top-Front-Right",
        "Top-Back-Left",
        "Bottom-Front-Left",
        "Bottom-Back-Right",
        "Top-Front-Left",
        "Top-Back-Right",
    ):
        eye_direction = _named_view_eye_direction(view_name)
        overlay = _build_view_cube_overlay(
            _camera_state(
                (0.0, 0.0, 0.0),
                4.0,
                math.degrees(math.atan2(eye_direction[1], eye_direction[0])),
                math.degrees(math.asin(eye_direction[2])),
            ),
            900.0,
            700.0,
        )
        polygons = (
            [face.polygon for face in overlay.faces]
            + [panel.polygon for panel in overlay.edge_panels]
            + [panel.polygon for panel in overlay.corner_panels]
            + [control.polygon for control in overlay.controls]
        )
        xs = [point[0] for polygon in polygons for point in polygon]
        ys = [point[1] for polygon in polygons for point in polygon]

        assert xs
        assert ys
        assert max(xs) - min(xs) <= _VIEW_CUBE_WIDGET_WIDTH + 1.0
        assert max(ys) - min(ys) <= _VIEW_CUBE_WIDGET_HEIGHT + 1.0
        assert min(xs) >= 900.0 - _VIEW_CUBE_PADDING - _VIEW_CUBE_WIDGET_WIDTH - 1.0
        assert max(xs) <= 900.0 - _VIEW_CUBE_PADDING + 1.0
        assert min(ys) >= _VIEW_CUBE_PADDING - 1.0
        assert max(ys) <= _VIEW_CUBE_PADDING + _VIEW_CUBE_WIDGET_HEIGHT + 1.0


def test_view_cube_overlay_stays_visible_and_filters_slivers_across_angle_sweep():
    yaw_angles = (-180.0, -135.0, -90.0, -45.0, 0.0, 45.0, 90.0, 135.0, 180.0)
    pitch_angles = (-75.0, -45.0, -15.0, 15.0, 45.0, 75.0)
    roll_angles = (0.0, 45.0, 90.0, 135.0)

    for yaw in yaw_angles:
        for pitch in pitch_angles:
            for roll in roll_angles:
                overlay = _build_view_cube_overlay(
                    _camera_state((0.0, 0.0, 0.0), 4.0, yaw, pitch, roll),
                    900.0,
                    700.0,
                )

                assert overlay.faces
                assert all(face.screen_area > 0.0 for face in overlay.faces)
                assert all(panel.screen_area >= _VIEW_CUBE_MIN_EDGE_AREA for panel in overlay.edge_panels)
                assert all(
                    panel.screen_area >= _VIEW_CUBE_MIN_CORNER_AREA
                    for panel in overlay.corner_panels
                )
                assert len(overlay.hotspots) >= len(overlay.controls) + len(overlay.faces)


def test_view_cube_face_on_views_keep_primary_face_and_hide_corner_slivers():
    face_on_views = (
        (-90.0, 0.0, "Front"),
        (0.0, 0.0, "Right"),
        (90.0, 0.0, "Back"),
        (180.0, 0.0, "Left"),
        (0.0, 90.0, "Top"),
        (0.0, -90.0, "Bottom"),
    )

    for yaw, pitch, expected_face in face_on_views:
        overlay = _build_view_cube_overlay(
            _camera_state((0.0, 0.0, 0.0), 4.0, yaw, pitch),
            900.0,
            700.0,
        )

        assert [face.view_name for face in overlay.faces] == [expected_face]
        assert len(overlay.edge_panels) == 4
        assert not overlay.corner_panels
        assert all(panel.screen_area >= _VIEW_CUBE_DOMINANT_EDGE_AREA for panel in overlay.edge_panels)


def test_view_cube_labels_are_uppercase_and_bevels_are_darker_than_faces():
    overlay = _build_view_cube_overlay(
        _camera_state((0.0, 0.0, 0.0), 4.0, -45.0, 35.26438968),
        900.0,
        700.0,
    )
    assert overlay.faces
    assert all(face.label.isupper() for face in overlay.faces)
    assert QColor(_VIEWPORT_CUBE_BEVEL_HEX).lightnessF() < QColor(_VIEWPORT_CUBE_FACE_HEX).lightnessF()


def test_top_roll_icon_clears_the_top_rotate_arrow():
    overlay = _build_view_cube_overlay(
        _camera_state((0.0, 0.0, 0.0), 4.0, -45.0, 35.26438968),
        900.0,
        700.0,
    )
    rotate_up = next(control for control in overlay.controls if control.kind == "rotate_up")
    top_roll = next(control for control in overlay.controls if control.kind == "roll_left")

    rotate_bounds = QPolygonF(QPointF(point[0], point[1]) for point in rotate_up.polygon).boundingRect()
    roll_bounds = QPolygonF(QPointF(point[0], point[1]) for point in top_roll.polygon).boundingRect()

    assert not rotate_bounds.intersects(roll_bounds)


def test_view_cube_home_and_roll_controls_anchor_to_requested_widget_corners():
    overlay = _build_view_cube_overlay(
        _camera_state((0.0, 0.0, 0.0), 4.0, -45.0, 35.26438968),
        900.0,
        700.0,
    )
    cube_points = [
        point
        for polygon in [face.polygon for face in overlay.faces]
        + [panel.polygon for panel in overlay.edge_panels]
        + [panel.polygon for panel in overlay.corner_panels]
        for point in polygon
    ]
    cube_min_x = min(point[0] for point in cube_points)
    cube_max_x = max(point[0] for point in cube_points)
    cube_mid_y = (min(point[1] for point in cube_points) + max(point[1] for point in cube_points)) * 0.5

    home = next(control for control in overlay.controls if control.kind == "home")
    roll_left = next(control for control in overlay.controls if control.kind == "roll_left")
    roll_right = next(control for control in overlay.controls if control.kind == "roll_right")

    home_center = (
        sum(point[0] for point in home.polygon) / len(home.polygon),
        sum(point[1] for point in home.polygon) / len(home.polygon),
    )
    left_roll_center = (
        sum(point[0] for point in roll_left.polygon) / len(roll_left.polygon),
        sum(point[1] for point in roll_left.polygon) / len(roll_left.polygon),
    )
    right_roll_center = (
        sum(point[0] for point in roll_right.polygon) / len(roll_right.polygon),
        sum(point[1] for point in roll_right.polygon) / len(roll_right.polygon),
    )

    assert home_center[0] > cube_max_x
    assert home_center[1] > cube_mid_y
    assert left_roll_center[0] < cube_min_x
    assert left_roll_center[1] < cube_mid_y
    assert right_roll_center[0] > cube_max_x
    assert right_roll_center[1] < cube_mid_y


def test_view_cube_icon_slot_directory_exists():
    assert (_VIEW_CUBE_ICON_DIR / "README.md").exists()


def test_crease_aware_render_geometry_keeps_coplanar_faces_smooth():
    geometry = _build_crease_aware_render_geometry(
        vertices=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        faces=[
            (0, 1, 2),
            (0, 2, 3),
        ],
    )

    assert len(geometry.vertices) == 4
    assert len(geometry.faces) == 2
    assert {
        tuple(round(component, 6) for component in vertex.normal)
        for vertex in geometry.vertices
    } == {(0.0, 0.0, 1.0)}


def test_crease_aware_render_geometry_splits_normals_across_sharp_transition():
    geometry = _build_crease_aware_render_geometry(
        vertices=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ],
        faces=[
            (0, 1, 2),
            (0, 3, 1),
        ],
    )

    assert len(geometry.vertices) == 6
    first_normal = geometry.vertices[geometry.faces[0][0]].normal
    second_normal = geometry.vertices[geometry.faces[1][0]].normal
    assert geometry.faces[0][0] != geometry.faces[1][0]
    assert abs(sum(left * right for left, right in zip(first_normal, second_normal))) < 0.1


def test_crease_aware_render_geometry_handles_empty_and_degenerate_inputs():
    empty = _build_crease_aware_render_geometry(vertices=[], faces=[])
    assert empty.vertices == []
    assert empty.faces == []

    degenerate = _build_crease_aware_render_geometry(
        vertices=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
        ],
        faces=[(0, 1, 2)],
    )
    assert len(degenerate.faces) == 1
    assert len(degenerate.vertices) == 3
    assert all(
        math.isfinite(component)
        for vertex in degenerate.vertices
        for component in vertex.normal
    )


def test_render_pass_configs_keep_surface_opaque_and_overlays_non_destructive():
    assert _SURFACE_PASS_CONFIG.alpha == pytest.approx(1.0)
    assert not _SURFACE_PASS_CONFIG.blending_enabled
    assert _SURFACE_PASS_CONFIG.depth_write_enabled
    assert _OVERLAY_PASS_CONFIG.blending_enabled
    assert not _OVERLAY_PASS_CONFIG.depth_write_enabled
    assert _OVERLAY_DEPTH_BIAS > 0.0


def test_opengl_viewport_initializes_empty_geometry_buffers(qtbot):
    if not advanced_propeller_module._HAS_QT_OPENGL:
        pytest.skip("Qt OpenGL modules are unavailable")

    viewport = advanced_propeller_module._OpenGLPropellerViewportWidget()
    qtbot.addWidget(viewport)

    assert viewport._mesh_triangle_blob == b""
    assert viewport._mesh_interactive_triangle_blob == b""
    assert viewport._mesh_wire_blob == b""


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


def test_software_viewport_cube_click_snaps_without_entering_drag(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(200)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    _wait_for_result(qtbot, workspace)

    canvas = workspace.viewport._canvas
    overlay = canvas._view_cube_overlay()
    top_face = next(face for face in overlay.faces if face.view_name == "Top")
    centroid = (
        sum(point[0] for point in top_face.polygon) / len(top_face.polygon),
        sum(point[1] for point in top_face.polygon) / len(top_face.polygon),
    )
    qtbot.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(centroid[0]), round(centroid[1])),
    )

    assert canvas._drag_mode is None
    assert canvas._pitch == pytest.approx(90.0)


def test_view_cube_home_control_restores_default_iso(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(200)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    _wait_for_result(qtbot, workspace)

    canvas = workspace.viewport._canvas
    workspace.viewport.snap_to_named_view("Front")
    overlay = canvas._view_cube_overlay()
    home_hotspot = next(hotspot for hotspot in overlay.hotspots if hotspot.action == "home")
    centroid = (
        sum(point[0] for point in home_hotspot.polygon) / len(home_hotspot.polygon),
        sum(point[1] for point in home_hotspot.polygon) / len(home_hotspot.polygon),
    )
    qtbot.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(centroid[0]), round(centroid[1])),
    )

    assert canvas._drag_mode is None
    assert canvas._yaw == pytest.approx(-45.0)
    assert canvas._pitch == pytest.approx(35.26438968)
    assert canvas._roll == pytest.approx(0.0)


def test_view_cube_rotate_and_roll_controls_update_camera_without_drag(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(200)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    _wait_for_result(qtbot, workspace)

    canvas = workspace.viewport._canvas
    initial_angles = (canvas._yaw, canvas._pitch, canvas._roll)

    overlay = canvas._view_cube_overlay()
    rotate_hotspot = next(hotspot for hotspot in overlay.hotspots if hotspot.action == "rotate")
    rotate_center = (
        sum(point[0] for point in rotate_hotspot.polygon) / len(rotate_hotspot.polygon),
        sum(point[1] for point in rotate_hotspot.polygon) / len(rotate_hotspot.polygon),
    )
    qtbot.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(rotate_center[0]), round(rotate_center[1])),
    )

    after_rotate = (canvas._yaw, canvas._pitch, canvas._roll)
    assert canvas._drag_mode is None
    assert any(abs(after - before) > 1e-3 for after, before in zip(after_rotate, initial_angles))

    overlay = canvas._view_cube_overlay()
    roll_hotspot = next(hotspot for hotspot in overlay.hotspots if hotspot.action == "roll")
    roll_center = (
        sum(point[0] for point in roll_hotspot.polygon) / len(roll_hotspot.polygon),
        sum(point[1] for point in roll_hotspot.polygon) / len(roll_hotspot.polygon),
    )
    qtbot.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(roll_center[0]), round(roll_center[1])),
    )

    assert canvas._drag_mode is None
    assert abs(canvas._roll) > 1.0


def test_reset_view_restores_default_iso_after_named_view_snap(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(200)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    _wait_for_result(qtbot, workspace)

    workspace.viewport.snap_to_named_view("Front")
    workspace.viewport.reset_view()
    canvas = workspace.viewport._canvas

    assert canvas._yaw == pytest.approx(-45.0)
    assert canvas._pitch == pytest.approx(35.26438968)
    assert canvas._roll == pytest.approx(0.0)


def test_viewport_uses_cad_palette_instead_of_app_accent(window, qtbot):
    node_id = _drop_propeller_module(window)
    assert window.orchestrate.scene.activate_node(node_id)
    qtbot.wait(200)

    workspace = window.workspace_stack.currentWidget()
    assert isinstance(workspace, AdvancedPropellerWorkspace)
    canvas = workspace.viewport._canvas

    assert canvas._background.name().lower() == _VIEWPORT_BACKGROUND_HEX
    assert canvas._mesh_fill.name().lower() == _VIEWPORT_SURFACE_HEX


def test_display_edge_geometry_is_separate_from_full_wireframe():
    state = create_default_propeller_feature_state("edge-node", "Propeller")
    bridge = PropellerBuildBridge()
    result = bridge.build_model(
        PropellerBuildRequestDTO(
            feature_state=state,
            dirty_stages=list(ACTIVE_PROPELLER_STAGES),
        )
    )
    display_edges = _build_display_edges(result.mesh.vertices, result.mesh.faces)
    total_wire_edges = len(result.mesh.faces) * 3
    assert display_edges
    assert len(display_edges) * 2 < total_wire_edges
