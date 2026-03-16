from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsSimpleTextItem

from rotorlab_app.ui.main_window import THEMES, RotorLabMainWindow
from rotorlab_app.ui.orchestrate import PlacementTarget, WorkflowCanvasScene
from rotorlab_app.ui.typography import default_typography_profile


@pytest.fixture
def window(qtbot):
    main_window = RotorLabMainWindow(typography_profile=default_typography_profile())
    qtbot.addWidget(main_window)
    main_window.show()
    qtbot.wait(50)
    return main_window


def _target(
    scene: WorkflowCanvasScene,
    kind: str,
    row: int,
    col: int | None = None,
) -> PlacementTarget:
    for candidate in scene.overlay_targets():
        if candidate.kind != kind:
            continue
        if candidate.row != row:
            continue
        if col is not None and candidate.col != col:
            continue
        return candidate
    raise AssertionError(f"Missing target kind={kind}, row={row}, col={col}")


def _drop_on_target(
    window: RotorLabMainWindow,
    module_name: str,
    target: PlacementTarget,
) -> None:
    scene = window.orchestrate.scene
    canvas = window.orchestrate.canvas

    point = scene.overlay_center_for_target(target)
    assert point is not None
    scene.update_drag_position(point)
    assert canvas.drop_module_at_scene_point(module_name, point)


def test_empty_canvas_drag_shows_single_origin_overlay(window):
    scene = window.orchestrate.scene
    scene.begin_module_drag()

    targets = scene.overlay_targets()
    assert len(targets) == 1
    assert targets[0] == PlacementTarget(
        kind=WorkflowCanvasScene.PLACEMENT_EMPTY,
        row=0,
        col=0,
    )


def test_first_drop_lands_at_origin_and_emits_snapshot(window, qtbot):
    scene = window.orchestrate.scene
    snapshots = []
    window.orchestrate.canvas.grid_changed.connect(snapshots.append)

    scene.begin_module_drag()
    origin_target = _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0)
    _drop_on_target(window, "A", origin_target)

    qtbot.wait(20)
    assert snapshots
    snapshot = snapshots[-1]
    assert [(module.name, module.row, module.col) for module in snapshot.modules] == [("A", 0, 0)]
    assert "row 0, col 0" in window.state_label.text()


def test_between_module_insertion_shifts_modules_right(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_on_target(window, "A", _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0))

    scene.begin_module_drag()
    _drop_on_target(window, "B", _target(scene, WorkflowCanvasScene.PLACEMENT_COLUMN, row=0, col=1))

    scene.begin_module_drag()
    _drop_on_target(window, "C", _target(scene, WorkflowCanvasScene.PLACEMENT_COLUMN, row=0, col=1))

    positions = {(module.name, module.row, module.col) for module in scene.snapshot().modules}
    assert positions == {("A", 0, 0), ("C", 0, 1), ("B", 0, 2)}


def test_row_insert_uses_column_segment_target_and_shifts_rows(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_on_target(window, "A", _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0))

    scene.begin_module_drag()
    _drop_on_target(window, "B", _target(scene, WorkflowCanvasScene.PLACEMENT_COLUMN, row=0, col=1))

    scene.begin_module_drag()
    _drop_on_target(window, "C", _target(scene, WorkflowCanvasScene.PLACEMENT_ROW, row=1, col=1))

    scene.begin_module_drag()
    _drop_on_target(window, "D", _target(scene, WorkflowCanvasScene.PLACEMENT_ROW, row=1, col=0))

    positions = {(module.name, module.row, module.col) for module in scene.snapshot().modules}
    assert positions == {("A", 0, 0), ("B", 0, 1), ("D", 1, 0), ("C", 2, 1)}


def test_row_insert_overlays_are_segmented_per_column(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_on_target(window, "A", _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0))

    scene.begin_module_drag()
    _drop_on_target(window, "B", _target(scene, WorkflowCanvasScene.PLACEMENT_COLUMN, row=0, col=1))

    scene.begin_module_drag()
    row_targets = [
        target
        for target in scene.overlay_targets()
        if target.kind == WorkflowCanvasScene.PLACEMENT_ROW and target.row == 1
    ]
    assert len(row_targets) == 3

    row_rects = [scene._overlay_items[target].sceneBoundingRect() for target in row_targets]
    assert all(rect.width() < (scene.NODE_WIDTH + scene.COLUMN_GAP) for rect in row_rects)
    assert len({round(rect.x()) for rect in row_rects}) == len(row_rects)


def test_repeated_same_row_insertions_expand_width_without_wrapping(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_on_target(window, "A", _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0))

    for name in ("B", "C", "D", "E"):
        scene.begin_module_drag()
        row_targets = [
            target
            for target in scene.overlay_targets()
            if target.kind == WorkflowCanvasScene.PLACEMENT_COLUMN and target.row == 0
        ]
        assert row_targets
        append_target = max(row_targets, key=lambda target: target.col)
        _drop_on_target(window, name, append_target)

    modules = scene.snapshot().modules
    assert {module.row for module in modules} == {0}
    assert max(module.col for module in modules) == 4


def test_drag_cancel_and_invalid_payload_clear_overlays(window):
    scene = window.orchestrate.scene
    canvas = window.orchestrate.canvas

    scene.begin_module_drag()
    assert scene.overlay_count() > 0
    scene.cancel_module_drag()
    assert scene.overlay_count() == 0

    scene.begin_module_drag()
    target = _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0)
    point = scene.overlay_center_for_target(target)
    assert point is not None
    assert not canvas.drop_module_at_scene_point("", point)
    assert scene.overlay_count() == 0


def test_linear_edges_follow_row_major_order(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_on_target(window, "A", _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0))

    scene.begin_module_drag()
    _drop_on_target(window, "B", _target(scene, WorkflowCanvasScene.PLACEMENT_COLUMN, row=0, col=1))

    scene.begin_module_drag()
    _drop_on_target(window, "C", _target(scene, WorkflowCanvasScene.PLACEMENT_ROW, row=1, col=0))

    snapshot = scene.snapshot()
    id_to_name = {module.id: module.name for module in snapshot.modules}
    edge_names = [(id_to_name[edge.source_id], id_to_name[edge.target_id]) for edge in snapshot.linear_edges]
    assert edge_names == [("A", "B"), ("B", "C")]


def test_theme_switch_preserves_grid_state_and_overlay_colors(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_on_target(window, "A", _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0))
    before = {(module.name, module.row, module.col) for module in scene.snapshot().modules}

    window._on_global_action("Theme: Light")
    after = {(module.name, module.row, module.col) for module in scene.snapshot().modules}
    assert after == before

    scene.begin_module_drag()
    target = scene.overlay_targets()[0]
    overlay_item = scene._overlay_items[target]
    assert overlay_item.pen().color().name() == QColor(THEMES["Light"]["overlay_valid_border"]).name()


def test_existing_canvas_nodes_are_not_movable(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_on_target(window, "A", _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0))

    assert scene._node_items
    assert not (scene._node_items[0].flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_module_title_stays_inside_its_square_card(window):
    scene = window.orchestrate.scene

    scene.begin_module_drag()
    _drop_on_target(
        window,
        "Blade Profile Generator",
        _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0),
    )

    node = scene._node_items[0]
    node_bounds = node.sceneBoundingRect()
    title_items = [
        item
        for item in node.childItems()
        if isinstance(item, QGraphicsSimpleTextItem) and item.text().startswith("Blade")
    ]
    assert title_items

    title_bounds = title_items[0].sceneBoundingRect()
    assert title_bounds.left() >= node_bounds.left()
    assert title_bounds.right() <= node_bounds.right()
    assert title_bounds.top() >= node_bounds.top()
    assert title_bounds.bottom() <= node_bounds.bottom()


def test_canvas_scrollbars_appear_only_when_needed(window, qtbot):
    scene = window.orchestrate.scene
    canvas = window.orchestrate.canvas

    qtbot.wait(20)
    assert canvas.verticalScrollBar().maximum() == 0

    scene.begin_module_drag()
    _drop_on_target(window, "A", _target(scene, WorkflowCanvasScene.PLACEMENT_EMPTY, row=0, col=0))

    for row in range(1, 10):
        scene.begin_module_drag()
        _drop_on_target(
            window,
            f"R{row}",
            _target(scene, WorkflowCanvasScene.PLACEMENT_ROW, row=row, col=0),
        )

    qtbot.wait(20)
    assert canvas.verticalScrollBar().maximum() > 0
