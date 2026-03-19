from __future__ import annotations

import math
import os
from array import array
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QMatrix4x4, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform, QVector3D, QVector4D
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QSpinBox,
    QStackedWidget,
    QDoubleSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtOpenGL import (
        QOpenGLBuffer,
        QOpenGLShader,
        QOpenGLShaderProgram,
        QOpenGLVersionFunctionsFactory,
        QOpenGLVersionProfile,
    )
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget

    _HAS_QT_OPENGL = True
except ImportError:  # pragma: no cover - depends on Qt installation
    QOpenGLBuffer = None  # type: ignore[assignment]
    QOpenGLShader = None  # type: ignore[assignment]
    QOpenGLShaderProgram = None  # type: ignore[assignment]
    QOpenGLVersionFunctionsFactory = None  # type: ignore[assignment]
    QOpenGLVersionProfile = None  # type: ignore[assignment]
    QOpenGLWidget = None  # type: ignore[assignment]
    _HAS_QT_OPENGL = False

try:
    from PyQt6.QtSvg import QSvgRenderer

    _HAS_QT_SVG = True
except ImportError:  # pragma: no cover - depends on Qt installation
    QSvgRenderer = None  # type: ignore[assignment]
    _HAS_QT_SVG = False

from rotorlab_app.models.propeller import (
    ACTIVE_PROPELLER_STAGES,
    DEFERRED_PROPELLER_STAGES,
    STAGE_LABELS,
    PropellerEnvironmentSession,
    PropellerFeatureState,
    PropellerPreviewResult,
)
from rotorlab_app.services.propeller_preview_service import PropellerPreviewService
from rotorlab_app.ui.typography import TypographyManager, TypographyProfile, TypographyRole


GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_CULL_FACE = 0x0B44
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001
GL_LINE_STRIP = 0x0003
GL_UNSIGNED_INT = 0x1405
GL_FLOAT = 0x1406


@dataclass(frozen=True)
class _ProjectedPoint:
    x: float
    y: float
    depth: float


@dataclass(frozen=True)
class _RenderVertex:
    position: tuple[float, float, float]
    normal: tuple[float, float, float]


@dataclass(frozen=True)
class _RenderGeometry:
    vertices: list[_RenderVertex]
    faces: list[tuple[int, int, int]]


@dataclass(frozen=True)
class _RenderPassConfig:
    alpha: float
    blending_enabled: bool
    depth_write_enabled: bool


@dataclass(frozen=True)
class _ViewportCameraState:
    eye: tuple[float, float, float]
    eye_direction: tuple[float, float, float]
    forward: tuple[float, float, float]
    right: tuple[float, float, float]
    up: tuple[float, float, float]


@dataclass(frozen=True)
class _DisplayEdge:
    start: int
    end: int
    adjacent_faces: tuple[int, ...]


@dataclass(frozen=True)
class _ViewCubeFaceOverlay:
    label: str
    view_name: str
    polygon: tuple[tuple[float, float], ...]
    brightness: float
    depth: float
    label_quad: tuple[tuple[float, float], ...]
    screen_area: float = 0.0
    facing: float = 0.0


@dataclass(frozen=True)
class _ViewCubePanelOverlay:
    kind: str
    view_name: str
    polygon: tuple[tuple[float, float], ...]
    brightness: float
    depth: float
    screen_area: float = 0.0
    facing: float = 0.0


@dataclass(frozen=True)
class _ViewCubeControlOverlay:
    kind: str
    polygon: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class _ViewCubeHotspot:
    kind: str
    action: str
    polygon: tuple[tuple[float, float], ...]
    view_name: str | None = None
    axis: str | None = None
    degrees: float = 0.0


@dataclass(frozen=True)
class _ViewCubeOverlay:
    faces: tuple[_ViewCubeFaceOverlay, ...]
    edge_panels: tuple[_ViewCubePanelOverlay, ...]
    corner_panels: tuple[_ViewCubePanelOverlay, ...]
    controls: tuple[_ViewCubeControlOverlay, ...]
    hotspots: tuple[_ViewCubeHotspot, ...]


@dataclass(frozen=True)
class _ViewCubeFaceDefinition:
    view_name: str
    normal: tuple[float, float, float]
    u_axis: tuple[float, float, float]
    v_axis: tuple[float, float, float]


@dataclass(frozen=True)
class _ViewCubeBodyPanel3D:
    kind: str
    view_name: str
    points: tuple[tuple[float, float, float], ...]
    normal: tuple[float, float, float]
    label_quad: tuple[tuple[float, float, float], ...] | None = None


_CREASE_ANGLE_DEGREES = 45.0
_SURFACE_PASS_CONFIG = _RenderPassConfig(
    alpha=1.0,
    blending_enabled=False,
    depth_write_enabled=True,
)
_OVERLAY_PASS_CONFIG = _RenderPassConfig(
    alpha=0.92,
    blending_enabled=True,
    depth_write_enabled=False,
)
_SECTION_OVERLAY_ALPHA = 0.88
_OVERLAY_DEPTH_BIAS = 0.00035
_DISPLAY_EDGE_DEPTH_BIAS = 0.00018
_DISPLAY_EDGE_CREASE_ANGLE_DEGREES = 34.0
_VIEWPORT_BACKGROUND_HEX = "#5f6d86"
_VIEWPORT_BACKGROUND_BOTTOM_HEX = "#253041"
_VIEWPORT_SURFACE_HEX = "#d6d1cb"
_VIEWPORT_DISPLAY_EDGE_HEX = "#6f7478"
_VIEWPORT_WIREFRAME_HEX = "#86a8c7"
_VIEWPORT_CUBE_FACE_HEX = "#d5d5d3"
_VIEWPORT_CUBE_BEVEL_HEX = "#c3c3c1"
_VIEWPORT_CUBE_CORNER_HEX = "#b2b2b0"
_VIEWPORT_CUBE_EDGE_HEX = "#6f7277"
_VIEWPORT_CUBE_TEXT_HEX = "#34373c"
_VIEWPORT_CUBE_CONTROL_HEX = "#cfcfcd"
_VIEWPORT_CUBE_CONTROL_EDGE_HEX = "#666a70"
_VIEWPORT_CUBE_CONTROL_ICON_HEX = "#4d5158"
_VIEWPORT_TRIAD_X_HEX = "#d94343"
_VIEWPORT_TRIAD_Y_HEX = "#33b146"
_VIEWPORT_TRIAD_Z_HEX = "#3a64ff"
_VIEWPORT_LIGHT_DIRECTION = (0.35, -0.28, 0.89)
_VIEWPORT_LIGHT_AMBIENT = 0.86
_VIEWPORT_LIGHT_DIFFUSE = 0.12
_TRIAD_SIZE = 46.0
_TRIAD_PADDING = 18.0
_TRIAD_ARROW_SIZE = 6.0
_VIEW_CUBE_SIZE = 94.0
_VIEW_CUBE_PADDING = 18.0
_VIEW_CUBE_WIDGET_WIDTH = 150.0
_VIEW_CUBE_WIDGET_HEIGHT = 150.0
_VIEW_CUBE_WIDGET_INSET_X = 66.0
_VIEW_CUBE_WIDGET_INSET_Y = 75.0
_VIEW_CUBE_CHAMFER_RATIO = 0.23
_VIEW_CUBE_CORNER_RADIUS = 9.0
_VIEW_CUBE_EDGE_RADIUS = 7.0
_VIEW_CUBE_FOV_DEGREES = 28.0
_VIEW_CUBE_CAMERA_DISTANCE = 6.2
_VIEW_CUBE_FIT_FRACTION = 0.84
_VIEW_CUBE_CONTROL_SIZE = 15.0
_VIEW_CUBE_CONTROL_GAP = 7.0
_VIEW_CUBE_HOME_SIZE = 18.0
_VIEW_CUBE_ROLL_WIDTH = 22.0
_VIEW_CUBE_ROLL_HEIGHT = 14.0
_VIEW_CUBE_LABEL_MARGIN = 0.07
_VIEW_CUBE_LABEL_HEIGHT = 0.40
_VIEW_CUBE_LABEL_PIXEL_SIZE = 128
_VIEW_CUBE_LABEL_TEXTURE_SIZE = 512
_VIEW_CUBE_MIN_FACE_AREA = 2.0
_VIEW_CUBE_MIN_EDGE_AREA = 1.5
_VIEW_CUBE_MIN_CORNER_AREA = 0.75
_VIEW_CUBE_MIN_OUTLINE_AREA = 0.95
_VIEW_CUBE_EDGE_FACING_THRESHOLD = 0.035
_VIEW_CUBE_CORNER_FACING_THRESHOLD = 0.08
_VIEW_CUBE_DOMINANT_FACE_RATIO = 5.0
_VIEW_CUBE_DOMINANT_EDGE_AREA = 8.5
_VIEW_CUBE_FACE_ORDER = ("Top", "Bottom", "Front", "Back", "Right", "Left")
_VIEW_NAME_ORDER = ("Top", "Bottom", "Front", "Back", "Right", "Left")
_VIEW_CUBE_ICON_DIR = Path(__file__).with_name("assets") / "view_cube"
_DEFAULT_ISO_COMPONENT = 1.0 / math.sqrt(3.0)
_DEFAULT_ISO_DIRECTION = (_DEFAULT_ISO_COMPONENT, -_DEFAULT_ISO_COMPONENT, _DEFAULT_ISO_COMPONENT)
_DEFAULT_ISO_YAW = math.degrees(math.atan2(_DEFAULT_ISO_DIRECTION[1], _DEFAULT_ISO_DIRECTION[0]))
_DEFAULT_ISO_PITCH = math.degrees(math.asin(_DEFAULT_ISO_DIRECTION[2]))
_VIEW_AXIS_MAP: dict[str, tuple[float, float, float]] = {
    "Top": (0.0, 0.0, 1.0),
    "Bottom": (0.0, 0.0, -1.0),
    "Front": (0.0, -1.0, 0.0),
    "Back": (0.0, 1.0, 0.0),
    "Right": (1.0, 0.0, 0.0),
    "Left": (-1.0, 0.0, 0.0),
}
_VIEW_CUBE_VERTICES: tuple[tuple[float, float, float], ...] = (
    (-1.0, -1.0, -1.0),
    (1.0, -1.0, -1.0),
    (1.0, 1.0, -1.0),
    (-1.0, 1.0, -1.0),
    (-1.0, -1.0, 1.0),
    (1.0, -1.0, 1.0),
    (1.0, 1.0, 1.0),
    (-1.0, 1.0, 1.0),
)
_VIEW_CUBE_FACE_DEFINITIONS: tuple[_ViewCubeFaceDefinition, ...] = (
    _ViewCubeFaceDefinition(
        view_name="Top",
        normal=(0.0, 0.0, 1.0),
        u_axis=(1.0, 0.0, 0.0),
        v_axis=(0.0, -1.0, 0.0),
    ),
    _ViewCubeFaceDefinition(
        view_name="Bottom",
        normal=(0.0, 0.0, -1.0),
        u_axis=(1.0, 0.0, 0.0),
        v_axis=(0.0, 1.0, 0.0),
    ),
    _ViewCubeFaceDefinition(
        view_name="Front",
        normal=(0.0, -1.0, 0.0),
        u_axis=(1.0, 0.0, 0.0),
        v_axis=(0.0, 0.0, -1.0),
    ),
    _ViewCubeFaceDefinition(
        view_name="Back",
        normal=(0.0, 1.0, 0.0),
        u_axis=(-1.0, 0.0, 0.0),
        v_axis=(0.0, 0.0, -1.0),
    ),
    _ViewCubeFaceDefinition(
        view_name="Right",
        normal=(1.0, 0.0, 0.0),
        u_axis=(0.0, 1.0, 0.0),
        v_axis=(0.0, 0.0, -1.0),
    ),
    _ViewCubeFaceDefinition(
        view_name="Left",
        normal=(-1.0, 0.0, 0.0),
        u_axis=(0.0, -1.0, 0.0),
        v_axis=(0.0, 0.0, -1.0),
    ),
)
_VIEW_CUBE_ARROW_STEPS: dict[str, tuple[str, float]] = {
    "rotate_left": ("screen_up", 90.0),
    "rotate_right": ("screen_up", -90.0),
    "rotate_up": ("screen_right", -90.0),
    "rotate_down": ("screen_right", 90.0),
    "roll_left": ("forward", 90.0),
    "roll_right": ("forward", -90.0),
}


def _series_color(index: int) -> QColor:
    palette = (
        QColor("#0078d4"),
        QColor("#e8a628"),
        QColor("#6da57a"),
        QColor("#c86b4d"),
        QColor("#8fa3b8"),
        QColor("#5ea7aa"),
        QColor("#b9847a"),
    )
    return palette[index % len(palette)]


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-9:
        return (0.0, 0.0, 1.0)
    return tuple(component / length for component in vector)


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _dot(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _sub(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _add(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _scale(
    vector: tuple[float, float, float],
    factor: float,
) -> tuple[float, float, float]:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _camera_state(
    center: tuple[float, float, float],
    distance: float,
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float = 0.0,
) -> _ViewportCameraState:
    yaw_rad = math.radians(yaw_deg)
    pitch_rad = math.radians(pitch_deg)
    eye_direction = (
        math.cos(pitch_rad) * math.cos(yaw_rad),
        math.cos(pitch_rad) * math.sin(yaw_rad),
        math.sin(pitch_rad),
    )
    eye = _add(center, _scale(eye_direction, distance))
    forward = _normalize(_scale(eye_direction, -1.0))
    world_up = (0.0, 0.0, 1.0)
    if abs(_dot(forward, world_up)) > 0.98:
        world_up = (0.0, 1.0, 0.0)
    right = _normalize(_cross(forward, world_up))
    up = _normalize(_cross(right, forward))
    if abs(roll_deg) > 1e-6:
        right = _normalize(_rotate_vector(right, forward, roll_deg))
        up = _normalize(_rotate_vector(up, forward, roll_deg))
    return _ViewportCameraState(
        eye=eye,
        eye_direction=_normalize(eye_direction),
        forward=forward,
        right=right,
        up=up,
    )


def _rotate_vector(
    vector: tuple[float, float, float],
    axis: tuple[float, float, float],
    degrees: float,
) -> tuple[float, float, float]:
    axis = _normalize(axis)
    radians = math.radians(degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    cross = _cross(axis, vector)
    dot = _dot(axis, vector)
    return (
        vector[0] * cosine + cross[0] * sine + axis[0] * dot * (1.0 - cosine),
        vector[1] * cosine + cross[1] * sine + axis[1] * dot * (1.0 - cosine),
        vector[2] * cosine + cross[2] * sine + axis[2] * dot * (1.0 - cosine),
    )


def _orthonormalize_up(
    forward: tuple[float, float, float],
    up: tuple[float, float, float],
) -> tuple[float, float, float]:
    candidate = _sub(up, _scale(forward, _dot(up, forward)))
    if math.sqrt(_dot(candidate, candidate)) <= 1e-6:
        fallback = (0.0, 0.0, 1.0)
        if abs(_dot(forward, fallback)) > 0.98:
            fallback = (0.0, 1.0, 0.0)
        candidate = _sub(fallback, _scale(forward, _dot(fallback, forward)))
    return _normalize(candidate)


def _camera_angles_from_eye_direction(
    eye_direction: tuple[float, float, float],
    up: tuple[float, float, float],
) -> tuple[float, float, float]:
    eye_direction = _normalize(eye_direction)
    yaw = math.degrees(math.atan2(eye_direction[1], eye_direction[0]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, eye_direction[2]))))
    forward = _normalize(_scale(eye_direction, -1.0))
    normalized_up = _orthonormalize_up(forward, up)
    base_camera = _camera_state((0.0, 0.0, 0.0), 1.0, yaw, pitch, 0.0)
    sine = _dot(_cross(base_camera.up, normalized_up), forward)
    cosine = _dot(base_camera.up, normalized_up)
    roll = math.degrees(math.atan2(sine, cosine))
    return yaw, pitch, roll


def _rotate_camera_angles(
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
    axis_kind: str,
    degrees: float,
) -> tuple[float, float, float]:
    camera = _camera_state((0.0, 0.0, 0.0), 1.0, yaw_deg, pitch_deg, roll_deg)
    if axis_kind == "screen_up":
        axis = camera.up
    elif axis_kind == "screen_right":
        axis = camera.right
    else:
        axis = camera.forward
    rotated_eye_direction = _rotate_vector(camera.eye_direction, axis, degrees)
    rotated_up = _rotate_vector(camera.up, axis, degrees)
    return _camera_angles_from_eye_direction(rotated_eye_direction, rotated_up)


def _named_view_eye_direction(view_name: str) -> tuple[float, float, float]:
    parts = [part.strip().title() for part in view_name.split("-") if part.strip()]
    if not parts:
        raise ValueError("Named view must include at least one axis label.")

    seen_axes: set[str] = set()
    direction = (0.0, 0.0, 0.0)
    for part in parts:
        if part not in _VIEW_AXIS_MAP:
            raise ValueError(f"Unknown named view component: {part}")
        axis_key = "z" if part in {"Top", "Bottom"} else "y" if part in {"Front", "Back"} else "x"
        if axis_key in seen_axes:
            raise ValueError(f"Named view contains conflicting axes: {view_name}")
        seen_axes.add(axis_key)
        direction = _add(direction, _VIEW_AXIS_MAP[part])
    return _normalize(direction)


def _canonical_view_name(parts: list[str]) -> str:
    ordered = [part for part in _VIEW_NAME_ORDER if part in parts]
    return "-".join(ordered)


def _view_name_from_vector(vector: tuple[float, float, float]) -> str:
    parts: list[str] = []
    if vector[2] > 0.0:
        parts.append("Top")
    elif vector[2] < 0.0:
        parts.append("Bottom")
    if vector[1] < 0.0:
        parts.append("Front")
    elif vector[1] > 0.0:
        parts.append("Back")
    if vector[0] > 0.0:
        parts.append("Right")
    elif vector[0] < 0.0:
        parts.append("Left")
    return _canonical_view_name(parts)


def _view_name_from_points(points: tuple[tuple[float, float, float], ...]) -> str:
    constant = [0.0, 0.0, 0.0]
    for axis in range(3):
        values = {point[axis] for point in points}
        if len(values) == 1:
            constant[axis] = next(iter(values))
    return _view_name_from_vector((constant[0], constant[1], constant[2]))


def _color_with_brightness(color: QColor, brightness: float, alpha: float = 1.0) -> QColor:
    return QColor.fromRgbF(
        min(1.0, color.redF() * brightness),
        min(1.0, color.greenF() * brightness),
        min(1.0, color.blueF() * brightness),
        alpha,
    )


def _viewport_background_gradient(
    rect: QRectF,
    top_color: QColor,
    bottom_color: QColor,
) -> QLinearGradient:
    gradient = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
    gradient.setColorAt(0.0, _color_with_brightness(top_color, 1.08))
    gradient.setColorAt(0.34, top_color)
    gradient.setColorAt(0.68, _color_with_brightness(bottom_color, 1.38))
    gradient.setColorAt(1.0, bottom_color)
    return gradient


def _paint_viewport_background(
    painter: QPainter,
    rect: QRectF,
    top_color: QColor,
    bottom_color: QColor,
) -> None:
    painter.fillRect(rect, _viewport_background_gradient(rect, top_color, bottom_color))


def _surface_brightness(normal: tuple[float, float, float]) -> float:
    diffuse = max(0.0, _dot(_normalize(normal), _normalize(_VIEWPORT_LIGHT_DIRECTION)))
    return min(1.0, _VIEWPORT_LIGHT_AMBIENT + diffuse * _VIEWPORT_LIGHT_DIFFUSE)


def _polygon_from_points(points: tuple[tuple[float, float], ...]) -> QPolygonF:
    return QPolygonF([QPointF(point[0], point[1]) for point in points])


def _polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    if len(points) < 3:
        return 0.0
    doubled_area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        doubled_area += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(doubled_area) * 0.5


def _view_cube_panel_min_area(kind: str, dominant_face_mode: bool = False) -> float:
    if kind == "face":
        return _VIEW_CUBE_MIN_FACE_AREA
    if kind == "edge":
        return _VIEW_CUBE_DOMINANT_EDGE_AREA if dominant_face_mode else _VIEW_CUBE_MIN_EDGE_AREA
    return float("inf") if dominant_face_mode else _VIEW_CUBE_MIN_CORNER_AREA


def _view_cube_panel_facing_threshold(kind: str) -> float:
    if kind == "edge":
        return _VIEW_CUBE_EDGE_FACING_THRESHOLD
    if kind == "corner":
        return _VIEW_CUBE_CORNER_FACING_THRESHOLD
    return 1e-5


def _is_dominant_view_cube_face_mode(
    face_entries: list[tuple[float, float, _ViewCubeFaceOverlay]],
) -> bool:
    if not face_entries:
        return False
    sorted_entries = sorted(face_entries, key=lambda item: item[0], reverse=True)
    top_area = sorted_entries[0][0]
    next_area = sorted_entries[1][0] if len(sorted_entries) > 1 else 0.0
    return next_area <= 1e-6 or top_area >= next_area * _VIEW_CUBE_DOMINANT_FACE_RATIO


def _distance_between_points(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _distance_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    segment = (end[0] - start[0], end[1] - start[1])
    length_sq = segment[0] * segment[0] + segment[1] * segment[1]
    if length_sq <= 1e-9:
        return _distance_between_points(point, start)
    factor = ((point[0] - start[0]) * segment[0] + (point[1] - start[1]) * segment[1]) / length_sq
    factor = max(0.0, min(1.0, factor))
    projection = (start[0] + segment[0] * factor, start[1] + segment[1] * factor)
    return _distance_between_points(point, projection)


def _build_display_edges(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    crease_angle_deg: float = _DISPLAY_EDGE_CREASE_ANGLE_DEGREES,
) -> list[_DisplayEdge]:
    if not vertices or not faces:
        return []

    face_normals = [_face_normal(vertices, face) for face in faces]
    edge_faces: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(faces):
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            key = (start, end) if start < end else (end, start)
            edge_faces[key].append(face_index)

    crease_cosine = math.cos(math.radians(crease_angle_deg))
    display_edges: list[_DisplayEdge] = []
    for (start, end), adjacent_faces in edge_faces.items():
        show_edge = len(adjacent_faces) == 1
        if not show_edge and len(adjacent_faces) > 1:
            similarities = [
                _dot(face_normals[left], face_normals[right])
                for left_index, left in enumerate(adjacent_faces)
                for right in adjacent_faces[left_index + 1 :]
            ]
            show_edge = any(similarity < crease_cosine for similarity in similarities)
        if show_edge:
            display_edges.append(
                _DisplayEdge(start=start, end=end, adjacent_faces=tuple(adjacent_faces))
            )
    return display_edges


def _build_view_cube_overlay(
    camera: _ViewportCameraState,
    widget_width: float,
    widget_height: float,
    size: float = _VIEW_CUBE_SIZE,
    padding: float = _VIEW_CUBE_PADDING,
) -> _ViewCubeOverlay:
    widget_rect = _view_cube_widget_rect(widget_width, widget_height, padding)
    cube_center = (
        widget_rect.right() - _VIEW_CUBE_WIDGET_INSET_X,
        widget_rect.top() + _VIEW_CUBE_WIDGET_INSET_Y,
    )
    inset = max(0.05, 1.0 - _VIEW_CUBE_CHAMFER_RATIO)
    overlay_eye = _scale(camera.eye_direction, _VIEW_CUBE_CAMERA_DISTANCE)
    face_entries: list[tuple[float, float, _ViewCubeFaceOverlay]] = []
    edge_entries: list[tuple[float, float, _ViewCubePanelOverlay]] = []
    corner_entries: list[tuple[float, float, _ViewCubePanelOverlay]] = []
    for panel in _build_view_cube_body_panels(inset):
        panel_center = tuple(
            sum(point[index] for point in panel.points) / len(panel.points)
            for index in range(3)
        )
        view_direction = _normalize(_sub(overlay_eye, panel_center))
        facing = _dot(panel.normal, view_direction)
        if facing <= _view_cube_panel_facing_threshold(panel.kind):
            continue
        projected = _project_view_cube_points(panel.points, camera, cube_center, size)
        depth = sum(point[2] for point in projected) / len(projected)
        brightness = _surface_brightness(panel.normal)
        polygon = tuple((point[0], point[1]) for point in projected)
        screen_area = _polygon_area(polygon)
        if panel.kind == "face":
            label_quad_3d = panel.label_quad or panel.points
            projected_label = _project_view_cube_points(label_quad_3d, camera, cube_center, size)
            face = _ViewCubeFaceOverlay(
                label=panel.view_name.upper(),
                view_name=panel.view_name,
                polygon=polygon,
                brightness=brightness,
                depth=depth,
                label_quad=tuple((point[0], point[1]) for point in projected_label),
                screen_area=screen_area,
                facing=facing,
            )
            face_entries.append((screen_area, facing, face))
        elif panel.kind == "edge":
            edge_panel = _ViewCubePanelOverlay(
                kind="edge",
                view_name=panel.view_name,
                polygon=polygon,
                brightness=brightness,
                depth=depth,
                screen_area=screen_area,
                facing=facing,
            )
            edge_entries.append((screen_area, facing, edge_panel))
        else:
            corner_panel = _ViewCubePanelOverlay(
                kind="corner",
                view_name=panel.view_name,
                polygon=polygon,
                brightness=brightness,
                depth=depth,
                screen_area=screen_area,
                facing=facing,
            )
            corner_entries.append((screen_area, facing, corner_panel))

    face_entries.sort(key=lambda item: (item[2].depth, item[0], item[2].view_name), reverse=True)
    dominant_face_mode = _is_dominant_view_cube_face_mode(face_entries)

    visible_faces = [
        panel
        for index, (screen_area, _facing, panel) in enumerate(face_entries)
        if screen_area >= _view_cube_panel_min_area("face") or index == 0
    ]
    edge_panels = [
        panel
        for screen_area, _facing, panel in edge_entries
        if screen_area >= _view_cube_panel_min_area("edge", dominant_face_mode)
    ]
    corner_panels = [
        panel
        for screen_area, _facing, panel in corner_entries
        if screen_area >= _view_cube_panel_min_area("corner", dominant_face_mode)
    ]

    visible_faces.sort(key=lambda panel: (panel.depth, panel.screen_area, panel.view_name), reverse=True)
    edge_panels.sort(key=lambda panel: (panel.depth, panel.screen_area, panel.view_name))
    corner_panels.sort(key=lambda panel: (panel.depth, panel.screen_area, panel.view_name))

    hotspots: list[_ViewCubeHotspot] = []
    for face in visible_faces:
        hotspots.append(
            _ViewCubeHotspot(
                kind="face",
                action="snap",
                view_name=face.view_name,
                polygon=face.polygon,
            )
        )
    for panel in edge_panels:
        hotspots.append(
            _ViewCubeHotspot(
                kind="edge",
                action="snap",
                view_name=panel.view_name,
                polygon=panel.polygon,
            )
        )
    for panel in corner_panels:
        hotspots.append(
            _ViewCubeHotspot(
                kind="corner",
                action="snap",
                view_name=panel.view_name,
                polygon=panel.polygon,
            )
        )

    controls, control_hotspots = _build_view_cube_controls(widget_rect, cube_center, size)
    hotspots.extend(control_hotspots)
    return _ViewCubeOverlay(
        faces=tuple(visible_faces),
        edge_panels=tuple(edge_panels),
        corner_panels=tuple(corner_panels),
        controls=controls,
        hotspots=tuple(hotspots),
    )


def _view_cube_widget_rect(
    widget_width: float,
    widget_height: float,
    padding: float = _VIEW_CUBE_PADDING,
) -> QRectF:
    return QRectF(
        max(0.0, widget_width - _VIEW_CUBE_WIDGET_WIDTH - padding),
        padding,
        _VIEW_CUBE_WIDGET_WIDTH,
        min(_VIEW_CUBE_WIDGET_HEIGHT, max(_VIEW_CUBE_WIDGET_HEIGHT, widget_height - padding * 2.0)),
    )


def _project_view_cube_points(
    points: tuple[tuple[float, float, float], ...],
    camera: _ViewportCameraState,
    center: tuple[float, float],
    size: float,
) -> tuple[tuple[float, float, float], ...]:
    projection_scale = 1.0 / math.tan(math.radians(_VIEW_CUBE_FOV_DEGREES) * 0.5)
    max_extent = math.sqrt(3.0)
    max_projected_extent = (
        max_extent
        * projection_scale
        / max(0.2, _VIEW_CUBE_CAMERA_DISTANCE - max_extent)
    )
    fit_size = size * _VIEW_CUBE_FIT_FRACTION
    pixel_scale = (fit_size * 0.5) / max(max_projected_extent, 1e-6)
    overlay_eye = _scale(camera.eye_direction, _VIEW_CUBE_CAMERA_DISTANCE)
    projected_points: list[tuple[float, float, float]] = []
    for point in points:
        relative = _sub(point, overlay_eye)
        cam_x = _dot(relative, camera.right)
        cam_y = _dot(relative, camera.up)
        cam_z = max(0.05, _dot(relative, camera.forward))
        projected_points.append(
            (
                center[0] + (cam_x * projection_scale / cam_z) * pixel_scale,
                center[1] - (cam_y * projection_scale / cam_z) * pixel_scale,
                cam_z,
            )
        )
    return tuple(projected_points)


def _axis_index(vector: tuple[float, float, float]) -> int:
    return max(range(3), key=lambda index: abs(vector[index]))


def _view_cube_face_polygon_3d(
    definition: _ViewCubeFaceDefinition,
    inset: float,
) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        _add(
            definition.normal,
            _add(
                _scale(definition.u_axis, u * inset),
                _scale(definition.v_axis, v * inset),
            ),
        )
        for u, v in ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    )


def _view_cube_label_quad_3d(
    definition: _ViewCubeFaceDefinition,
    inset: float,
) -> tuple[tuple[float, float, float], ...]:
    width = inset * (1.0 - _VIEW_CUBE_LABEL_MARGIN * 2.0)
    height = inset * _VIEW_CUBE_LABEL_HEIGHT
    return tuple(
        _add(
            definition.normal,
            _add(
                _scale(definition.u_axis, u),
                _scale(definition.v_axis, v),
            ),
        )
        for u, v in (
            (-width, -height),
            (width, -height),
            (width, height),
            (-width, height),
        )
    )


def _build_view_cube_body_panels(inset: float) -> tuple[_ViewCubeBodyPanel3D, ...]:
    panels: list[_ViewCubeBodyPanel3D] = []
    for definition in _VIEW_CUBE_FACE_DEFINITIONS:
        panels.append(
            _ViewCubeBodyPanel3D(
                kind="face",
                view_name=definition.view_name,
                points=_view_cube_face_polygon_3d(definition, inset),
                normal=definition.normal,
                label_quad=_view_cube_label_quad_3d(definition, inset),
            )
        )

    for y_sign in (-1.0, 1.0):
        for z_sign in (-1.0, 1.0):
            panels.append(
                _ViewCubeBodyPanel3D(
                    kind="edge",
                    view_name=_view_name_from_vector((0.0, y_sign, z_sign)),
                    points=_view_cube_edge_strip_points(1, int(y_sign), 2, int(z_sign), 0, inset),
                    normal=_normalize((0.0, y_sign, z_sign)),
                )
            )
    for x_sign in (-1.0, 1.0):
        for z_sign in (-1.0, 1.0):
            panels.append(
                _ViewCubeBodyPanel3D(
                    kind="edge",
                    view_name=_view_name_from_vector((x_sign, 0.0, z_sign)),
                    points=_view_cube_edge_strip_points(0, int(x_sign), 2, int(z_sign), 1, inset),
                    normal=_normalize((x_sign, 0.0, z_sign)),
                )
            )
    for x_sign in (-1.0, 1.0):
        for y_sign in (-1.0, 1.0):
            panels.append(
                _ViewCubeBodyPanel3D(
                    kind="edge",
                    view_name=_view_name_from_vector((x_sign, y_sign, 0.0)),
                    points=_view_cube_edge_strip_points(0, int(x_sign), 1, int(y_sign), 2, inset),
                    normal=_normalize((x_sign, y_sign, 0.0)),
                )
            )

    for x_sign in (-1.0, 1.0):
        for y_sign in (-1.0, 1.0):
            for z_sign in (-1.0, 1.0):
                panels.append(
                    _ViewCubeBodyPanel3D(
                        kind="corner",
                        view_name=_view_name_from_vector((x_sign, y_sign, z_sign)),
                        points=_view_cube_corner_cap_points(int(x_sign), int(y_sign), int(z_sign), inset),
                        normal=_normalize((x_sign, y_sign, z_sign)),
                    )
                )
    return tuple(panels)


def _view_cube_edge_strip_points(
    fixed_axis_a: int,
    sign_a: int,
    fixed_axis_b: int,
    sign_b: int,
    variable_axis: int,
    inset: float,
) -> tuple[tuple[float, float, float], ...]:
    points: list[tuple[float, float, float]] = []
    for variable in (-inset, inset):
        coordinates = [0.0, 0.0, 0.0]
        coordinates[fixed_axis_a] = float(sign_a)
        coordinates[fixed_axis_b] = sign_b * inset
        coordinates[variable_axis] = variable
        points.append((coordinates[0], coordinates[1], coordinates[2]))
    for variable in (inset, -inset):
        coordinates = [0.0, 0.0, 0.0]
        coordinates[fixed_axis_a] = sign_a * inset
        coordinates[fixed_axis_b] = float(sign_b)
        coordinates[variable_axis] = variable
        points.append((coordinates[0], coordinates[1], coordinates[2]))
    return tuple(points)


def _view_cube_corner_cap_points(
    sign_x: int,
    sign_y: int,
    sign_z: int,
    inset: float,
) -> tuple[tuple[float, float, float], ...]:
    return (
        (float(sign_x), sign_y * inset, sign_z * inset),
        (sign_x * inset, float(sign_y), sign_z * inset),
        (sign_x * inset, sign_y * inset, float(sign_z)),
    )


def _triangle_control_polygon(
    center: tuple[float, float],
    direction: tuple[float, float],
    size: float = _VIEW_CUBE_CONTROL_SIZE,
) -> tuple[tuple[float, float], ...]:
    unit = _normalize((direction[0], direction[1], 0.0))
    normal = (-unit[1], unit[0])
    tip = (center[0] + unit[0] * size * 0.55, center[1] + unit[1] * size * 0.55)
    base_center = (center[0] - unit[0] * size * 0.35, center[1] - unit[1] * size * 0.35)
    return (
        tip,
        (base_center[0] + normal[0] * size * 0.48, base_center[1] + normal[1] * size * 0.48),
        (base_center[0] - normal[0] * size * 0.48, base_center[1] - normal[1] * size * 0.48),
    )


def _rounded_rect_polygon(rect: QRectF, radius: float = 5.0) -> tuple[tuple[float, float], ...]:
    return (
        (rect.left() + radius, rect.top()),
        (rect.right() - radius, rect.top()),
        (rect.right(), rect.top() + radius),
        (rect.right(), rect.bottom() - radius),
        (rect.right() - radius, rect.bottom()),
        (rect.left() + radius, rect.bottom()),
        (rect.left(), rect.bottom() - radius),
        (rect.left(), rect.top() + radius),
    )


def _build_view_cube_controls(
    widget_rect: QRectF,
    cube_center: tuple[float, float],
    size: float,
) -> tuple[tuple[_ViewCubeControlOverlay, ...], tuple[_ViewCubeHotspot, ...]]:
    half = size * 0.5
    controls: list[_ViewCubeControlOverlay] = []
    hotspots: list[_ViewCubeHotspot] = []
    cardinal_offset = half + max(2.0, _VIEW_CUBE_CONTROL_GAP * 0.45)

    control_specs = (
        ("rotate_up", _triangle_control_polygon((cube_center[0], cube_center[1] - cardinal_offset), (0.0, -1.0))),
        ("rotate_down", _triangle_control_polygon((cube_center[0], cube_center[1] + cardinal_offset), (0.0, 1.0))),
        ("rotate_left", _triangle_control_polygon((cube_center[0] - cardinal_offset, cube_center[1]), (-1.0, 0.0))),
        ("rotate_right", _triangle_control_polygon((cube_center[0] + cardinal_offset, cube_center[1]), (1.0, 0.0))),
    )
    for kind, polygon in control_specs:
        controls.append(_ViewCubeControlOverlay(kind=kind, polygon=polygon))
        axis, degrees = _VIEW_CUBE_ARROW_STEPS[kind]
        hotspots.append(
            _ViewCubeHotspot(
                kind="control",
                action="rotate",
                polygon=polygon,
                axis=axis,
                degrees=degrees,
            )
        )

    home_rect = QRectF(
        cube_center[0] + cardinal_offset - _VIEW_CUBE_HOME_SIZE * 0.5,
        cube_center[1] + cardinal_offset - _VIEW_CUBE_HOME_SIZE * 0.5,
        _VIEW_CUBE_HOME_SIZE,
        _VIEW_CUBE_HOME_SIZE,
    )
    home_polygon = _rounded_rect_polygon(home_rect, 4.0)
    controls.append(_ViewCubeControlOverlay(kind="home", polygon=home_polygon))
    hotspots.append(
        _ViewCubeHotspot(
            kind="control",
            action="home",
            polygon=home_polygon,
        )
    )

    roll_rects = (
        (
            "roll_left",
            QRectF(
                cube_center[0] - cardinal_offset - _VIEW_CUBE_ROLL_WIDTH * 0.5,
                cube_center[1] - cardinal_offset - _VIEW_CUBE_ROLL_HEIGHT * 0.5,
                _VIEW_CUBE_ROLL_WIDTH,
                _VIEW_CUBE_ROLL_HEIGHT,
            ),
        ),
        (
            "roll_right",
            QRectF(
                cube_center[0] + cardinal_offset - _VIEW_CUBE_ROLL_WIDTH * 0.5,
                cube_center[1] - cardinal_offset - _VIEW_CUBE_ROLL_HEIGHT * 0.5,
                _VIEW_CUBE_ROLL_WIDTH,
                _VIEW_CUBE_ROLL_HEIGHT,
            ),
        ),
    )
    for kind, rect in roll_rects:
        polygon = _rounded_rect_polygon(rect, 6.0)
        controls.append(_ViewCubeControlOverlay(kind=kind, polygon=polygon))
        axis, degrees = _VIEW_CUBE_ARROW_STEPS[kind]
        hotspots.append(
            _ViewCubeHotspot(
                kind="control",
                action="roll",
                polygon=polygon,
                axis=axis,
                degrees=degrees,
            )
        )
    return tuple(controls), tuple(hotspots)


def _hit_test_view_cube_overlay(
    overlay: _ViewCubeOverlay,
    point: tuple[float, float],
) -> _ViewCubeHotspot | None:
    priority = {"control": 0, "corner": 1, "edge": 2, "face": 3}
    for hotspot in sorted(overlay.hotspots, key=lambda item: priority.get(item.kind, 99)):
        if hotspot.polygon and _polygon_from_points(hotspot.polygon).containsPoint(
            QPointF(point[0], point[1]),
            Qt.FillRule.WindingFill,
        ):
            return hotspot
    return None


def _apply_view_cube_hotspot(
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
    hotspot: _ViewCubeHotspot,
) -> tuple[float, float, float]:
    if hotspot.action == "home":
        return _DEFAULT_ISO_YAW, _DEFAULT_ISO_PITCH, 0.0
    if hotspot.action == "snap" and hotspot.view_name:
        eye_direction = _named_view_eye_direction(hotspot.view_name)
        return (
            math.degrees(math.atan2(eye_direction[1], eye_direction[0])),
            math.degrees(math.asin(max(-1.0, min(1.0, eye_direction[2])))),
            0.0,
        )
    if hotspot.axis:
        return _rotate_camera_angles(yaw_deg, pitch_deg, roll_deg, hotspot.axis, hotspot.degrees)
    return yaw_deg, pitch_deg, roll_deg


def _draw_axis_triad_overlay(
    painter: QPainter,
    camera: _ViewportCameraState,
    widget_height: float,
) -> None:
    origin = (_TRIAD_PADDING + _TRIAD_SIZE * 0.35, widget_height - _TRIAD_PADDING - _TRIAD_SIZE * 0.35)
    axis_specs = (
        ("X", (1.0, 0.0, 0.0), QColor(_VIEWPORT_TRIAD_X_HEX)),
        ("Y", (0.0, 1.0, 0.0), QColor(_VIEWPORT_TRIAD_Y_HEX)),
        ("Z", (0.0, 0.0, 1.0), QColor(_VIEWPORT_TRIAD_Z_HEX)),
    )
    sorted_axes = sorted(axis_specs, key=lambda item: _dot(item[1], camera.eye_direction))

    for label, axis, color in sorted_axes:
        end = (
            origin[0] + _dot(axis, camera.right) * _TRIAD_SIZE,
            origin[1] - _dot(axis, camera.up) * _TRIAD_SIZE,
        )
        painter.setPen(QPen(color, 1.8))
        painter.drawLine(QPointF(origin[0], origin[1]), QPointF(end[0], end[1]))

        direction_2d = (end[0] - origin[0], end[1] - origin[1])
        direction_length = math.hypot(direction_2d[0], direction_2d[1])
        if direction_length > 1e-6:
            direction_2d = (direction_2d[0] / direction_length, direction_2d[1] / direction_length)
            normal = (-direction_2d[1], direction_2d[0])
            tip = end
            left = (
                tip[0] - direction_2d[0] * _TRIAD_ARROW_SIZE + normal[0] * (_TRIAD_ARROW_SIZE * 0.55),
                tip[1] - direction_2d[1] * _TRIAD_ARROW_SIZE + normal[1] * (_TRIAD_ARROW_SIZE * 0.55),
            )
            right = (
                tip[0] - direction_2d[0] * _TRIAD_ARROW_SIZE - normal[0] * (_TRIAD_ARROW_SIZE * 0.55),
                tip[1] - direction_2d[1] * _TRIAD_ARROW_SIZE - normal[1] * (_TRIAD_ARROW_SIZE * 0.55),
            )
            painter.setBrush(color)
            painter.drawPolygon(_polygon_from_points((tip, left, right)))
            painter.drawText(QPointF(tip[0] + normal[0] * 6.0, tip[1] + normal[1] * 6.0), label)

    painter.setBrush(QColor(_VIEWPORT_CUBE_EDGE_HEX))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(origin[0], origin[1]), 3.2, 3.2)


def _draw_view_cube_overlay(
    painter: QPainter,
    overlay: _ViewCubeOverlay,
) -> None:
    body_panels: list[tuple[float, str, str, object]] = []
    body_panels.extend((panel.depth, "edge", panel.view_name, panel) for panel in overlay.edge_panels)
    body_panels.extend((panel.depth, "corner", panel.view_name, panel) for panel in overlay.corner_panels)
    body_panels.extend((face.depth, "face", face.view_name, face) for face in overlay.faces)
    kind_priority = {"face": 0, "edge": 1, "corner": 2}
    body_panels.sort(
        key=lambda item: (-round(item[0], 6), kind_priority.get(item[1], 99), item[2])
    )

    painter.setPen(Qt.PenStyle.NoPen)
    for _depth, kind, _view_name, panel in body_panels:
        if kind == "face":
            assert isinstance(panel, _ViewCubeFaceOverlay)
            painter.setBrush(_color_with_brightness(QColor(_VIEWPORT_CUBE_FACE_HEX), panel.brightness))
            painter.drawPolygon(_polygon_from_points(panel.polygon))
            _draw_view_cube_face_label(painter, panel)
        elif kind == "edge":
            assert isinstance(panel, _ViewCubePanelOverlay)
            painter.setBrush(_color_with_brightness(QColor(_VIEWPORT_CUBE_BEVEL_HEX), panel.brightness))
            painter.drawPolygon(_polygon_from_points(panel.polygon))
        else:
            assert isinstance(panel, _ViewCubePanelOverlay)
            painter.setBrush(_color_with_brightness(QColor(_VIEWPORT_CUBE_CORNER_HEX), panel.brightness))
            painter.drawPolygon(_polygon_from_points(panel.polygon))

    outline_color = QColor(_VIEWPORT_CUBE_EDGE_HEX)
    outline_color.setAlpha(208)
    outline_pen = QPen(outline_color, 0.8)
    outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(outline_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for _depth, _kind, _view_name, panel in body_panels:
        polygon = panel.polygon if isinstance(panel, (_ViewCubeFaceOverlay, _ViewCubePanelOverlay)) else ()
        if polygon and panel.screen_area >= _VIEW_CUBE_MIN_OUTLINE_AREA:
            painter.drawPolygon(_polygon_from_points(polygon))

    for control in overlay.controls:
        _draw_view_cube_control(painter, control)


def _view_cube_label_transform(face: _ViewCubeFaceOverlay) -> QTransform:
    source = QPolygonF(
        [
            QPointF(0.0, 0.0),
            QPointF(1.0, 0.0),
            QPointF(1.0, 1.0),
            QPointF(0.0, 1.0),
        ]
    )
    destination = _polygon_from_points(face.label_quad)
    transform = QTransform()
    if QTransform.quadToQuad(source, destination, transform):
        return transform

    first = face.label_quad[0]
    second = face.label_quad[1]
    fourth = face.label_quad[3]
    return QTransform(
        second[0] - first[0],
        second[1] - first[1],
        fourth[0] - first[0],
        fourth[1] - first[1],
        first[0],
        first[1],
    )


def _view_cube_label_path(face: _ViewCubeFaceOverlay, painter: QPainter) -> QPainterPath:
    font = painter.font()
    font.setPixelSize(_VIEW_CUBE_LABEL_PIXEL_SIZE)
    font.setWeight(QFont.Weight.Bold)
    base_path = QPainterPath()
    base_path.addText(QPointF(0.0, 0.0), font, face.label)
    bounds = base_path.boundingRect()
    available_width = max(0.1, 1.0 - _VIEW_CUBE_LABEL_MARGIN * 2.0)
    available_height = _VIEW_CUBE_LABEL_HEIGHT
    scale = min(
        available_width / max(bounds.width(), 1e-6),
        available_height / max(bounds.height(), 1e-6),
    )
    centered = QTransform()
    centered.translate(0.5, 0.54)
    centered.scale(scale, scale)
    centered.translate(-bounds.center().x(), -bounds.center().y())
    return centered.map(base_path)


@lru_cache(maxsize=32)
def _view_cube_label_image(label: str, font_family: str) -> QImage:
    image = QImage(
        _VIEW_CUBE_LABEL_TEXTURE_SIZE,
        _VIEW_CUBE_LABEL_TEXTURE_SIZE,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)

    font = QFont(font_family)
    font.setPixelSize(int(_VIEW_CUBE_LABEL_TEXTURE_SIZE * 0.56))
    font.setWeight(QFont.Weight.Bold)
    base_path = QPainterPath()
    base_path.addText(QPointF(0.0, 0.0), font, label)
    bounds = base_path.boundingRect()
    margin = _VIEW_CUBE_LABEL_TEXTURE_SIZE * 0.08
    available_width = max(1.0, _VIEW_CUBE_LABEL_TEXTURE_SIZE - margin * 2.0)
    available_height = _VIEW_CUBE_LABEL_TEXTURE_SIZE * 0.60
    scale = min(
        available_width / max(bounds.width(), 1e-6),
        available_height / max(bounds.height(), 1e-6),
    )
    centered = QTransform()
    centered.translate(_VIEW_CUBE_LABEL_TEXTURE_SIZE * 0.5, _VIEW_CUBE_LABEL_TEXTURE_SIZE * 0.56)
    centered.scale(scale, scale)
    centered.translate(-bounds.center().x(), -bounds.center().y())
    label_path = centered.map(base_path)

    image_painter = QPainter(image)
    image_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    image_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    image_painter.setPen(Qt.PenStyle.NoPen)
    image_painter.setBrush(_color_with_brightness(QColor(_VIEWPORT_CUBE_TEXT_HEX), 0.98))
    image_painter.drawPath(label_path)
    image_painter.end()
    return image


def _draw_view_cube_face_label(
    painter: QPainter,
    face: _ViewCubeFaceOverlay,
) -> None:
    transform = _view_cube_label_transform(face)
    label_path = _view_cube_label_path(face, painter)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setTransform(transform, True)
    painter.setClipRect(QRectF(0.0, 0.0, 1.0, 1.0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_color_with_brightness(QColor(_VIEWPORT_CUBE_TEXT_HEX), 0.98))
    painter.drawPath(label_path)
    painter.restore()


def _polygon_bounds(polygons: list[tuple[tuple[float, float], ...]]) -> QRectF:
    xs = [point[0] for polygon in polygons for point in polygon]
    ys = [point[1] for polygon in polygons for point in polygon]
    return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


@lru_cache(maxsize=None)
def _view_cube_icon_path(control_kind: str) -> Path | None:
    for suffix in (".svg", ".png"):
        candidate = _VIEW_CUBE_ICON_DIR / f"{control_kind}{suffix}"
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=None)
def _view_cube_icon_pixmap(control_kind: str) -> QPixmap | None:
    icon_path = _view_cube_icon_path(control_kind)
    if icon_path is None:
        return None
    pixmap = QPixmap(str(icon_path))
    if pixmap.isNull():
        return None
    return pixmap


@lru_cache(maxsize=None)
def _view_cube_icon_renderer(control_kind: str):
    icon_path = _view_cube_icon_path(control_kind)
    if icon_path is None or icon_path.suffix.lower() != ".svg" or not _HAS_QT_SVG or QSvgRenderer is None:
        return None
    renderer = QSvgRenderer(str(icon_path))
    if not renderer.isValid():
        return None
    return renderer


def _draw_view_cube_icon_asset(
    painter: QPainter,
    control_kind: str,
    bounds: QRectF,
) -> bool:
    renderer = _view_cube_icon_renderer(control_kind)
    if renderer is not None:
        renderer.render(painter, bounds)
        return True
    pixmap = _view_cube_icon_pixmap(control_kind)
    if pixmap is None:
        return False
    painter.drawPixmap(bounds.toRect(), pixmap)
    return True


def _draw_view_cube_control(
    painter: QPainter,
    control: _ViewCubeControlOverlay,
) -> None:
    bounds = _polygon_bounds([control.polygon])
    asset_bounds = bounds.adjusted(1.0, 1.0, -1.0, -1.0)
    if _draw_view_cube_icon_asset(painter, control.kind, asset_bounds):
        return

    if control.kind.startswith("rotate_"):
        centroid_x = sum(point[0] for point in control.polygon) / len(control.polygon)
        centroid_y = sum(point[1] for point in control.polygon) / len(control.polygon)
        outline = tuple(
            (
                centroid_x + (point[0] - centroid_x) * 0.84,
                centroid_y + (point[1] - centroid_y) * 0.84,
            )
            for point in control.polygon
        )
        painter.setPen(QPen(QColor(_VIEWPORT_CUBE_FACE_HEX), 1.15))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(_polygon_from_points(outline))
        return

    if control.kind.startswith("roll_"):
        _draw_roll_control(painter, control.kind, control.polygon)
        return

    painter.setPen(QPen(QColor(_VIEWPORT_CUBE_CONTROL_EDGE_HEX), 0.85))
    painter.setBrush(QColor(_VIEWPORT_CUBE_CONTROL_HEX))
    painter.drawRoundedRect(bounds, 5.0, 5.0)

    if control.kind == "home":
        _draw_home_control(painter, control.polygon)


def _draw_home_control(
    painter: QPainter,
    polygon: tuple[tuple[float, float], ...],
) -> None:
    bounds = _polygon_bounds([polygon]).adjusted(3.0, 3.0, -3.0, -3.0)
    roof = (
        (bounds.center().x(), bounds.top()),
        (bounds.right(), bounds.top() + bounds.height() * 0.42),
        (bounds.left(), bounds.top() + bounds.height() * 0.42),
    )
    body = QRectF(
        bounds.left() + bounds.width() * 0.22,
        bounds.top() + bounds.height() * 0.42,
        bounds.width() * 0.56,
        bounds.height() * 0.42,
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(_VIEWPORT_CUBE_CONTROL_ICON_HEX))
    painter.drawPolygon(_polygon_from_points(roof))
    painter.drawRoundedRect(body, 1.5, 1.5)


def _draw_roll_control(
    painter: QPainter,
    kind: str,
    polygon: tuple[tuple[float, float], ...],
) -> None:
    bounds = _polygon_bounds([polygon]).adjusted(1.8, 1.2, -1.8, -1.2)
    icon_color = QColor(_VIEWPORT_CUBE_FACE_HEX)
    pen = QPen(icon_color, 1.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    painter.save()
    if kind == "roll_left":
        center_x = bounds.center().x()
        painter.translate(center_x, 0.0)
        painter.scale(-1.0, 1.0)
        painter.translate(-center_x, 0.0)

    start_angle = 210.0
    sweep_angle = -245.0
    path = QPainterPath()
    path.arcMoveTo(bounds, start_angle)
    path.arcTo(bounds, start_angle, sweep_angle)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    end_angle = start_angle + sweep_angle
    radians = math.radians(end_angle)
    center = bounds.center()
    radius_x = bounds.width() * 0.5
    radius_y = bounds.height() * 0.5
    tip = (
        center.x() + math.cos(radians) * radius_x,
        center.y() - math.sin(radians) * radius_y,
    )
    tangent = (math.sin(radians) * radius_x, math.cos(radians) * radius_y)
    tangent_length = math.hypot(tangent[0], tangent[1])
    if tangent_length <= 1e-6:
        tangent = (1.0, 0.0)
    else:
        tangent = (tangent[0] / tangent_length, tangent[1] / tangent_length)
    normal = (-tangent[1], tangent[0])
    arrow = (
        tip,
        (
            tip[0] - tangent[0] * 4.8 + normal[0] * 2.2,
            tip[1] - tangent[1] * 4.8 + normal[1] * 2.2,
        ),
        (
            tip[0] - tangent[0] * 4.8 - normal[0] * 2.2,
            tip[1] - tangent[1] * 4.8 - normal[1] * 2.2,
        ),
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(icon_color)
    painter.drawPolygon(_polygon_from_points(arrow))
    painter.restore()


def _face_normal(
    vertices: list[tuple[float, float, float]],
    face: tuple[int, int, int],
) -> tuple[float, float, float]:
    first, second, third = face
    return _normalize(
        _cross(
            _sub(vertices[second], vertices[first]),
            _sub(vertices[third], vertices[first]),
        )
    )


def _build_crease_aware_render_geometry(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    crease_angle_deg: float = _CREASE_ANGLE_DEGREES,
) -> _RenderGeometry:
    if not vertices or not faces:
        return _RenderGeometry(vertices=[], faces=[])

    incident_faces: defaultdict[int, list[int]] = defaultdict(list)
    face_normals = [_face_normal(vertices, face) for face in faces]
    for face_index, face in enumerate(faces):
        for vertex_index in face:
            incident_faces[vertex_index].append(face_index)

    render_vertices: list[_RenderVertex] = []
    corner_lookup: dict[tuple[int, int], int] = {}
    crease_cosine = math.cos(math.radians(crease_angle_deg))

    for vertex_index in sorted(incident_faces):
        clusters: list[dict[str, object]] = []
        for face_index in incident_faces[vertex_index]:
            normal = face_normals[face_index]
            best_cluster_index: int | None = None
            best_similarity = crease_cosine
            for cluster_index, cluster in enumerate(clusters):
                cluster_sum = cluster["sum"]
                if not isinstance(cluster_sum, tuple):
                    continue
                similarity = _dot(_normalize(cluster_sum), normal)
                if similarity >= best_similarity:
                    best_similarity = similarity
                    best_cluster_index = cluster_index

            if best_cluster_index is None:
                clusters.append(
                    {
                        "sum": normal,
                        "faces": [face_index],
                    }
                )
                continue

            cluster = clusters[best_cluster_index]
            cluster_sum = cluster["sum"]
            cluster_faces = cluster["faces"]
            if isinstance(cluster_sum, tuple) and isinstance(cluster_faces, list):
                cluster["sum"] = (
                    cluster_sum[0] + normal[0],
                    cluster_sum[1] + normal[1],
                    cluster_sum[2] + normal[2],
                )
                cluster_faces.append(face_index)

        for cluster in clusters:
            cluster_sum = cluster["sum"]
            cluster_faces = cluster["faces"]
            if not isinstance(cluster_sum, tuple) or not isinstance(cluster_faces, list):
                continue
            render_index = len(render_vertices)
            render_vertices.append(
                _RenderVertex(
                    position=vertices[vertex_index],
                    normal=_normalize(cluster_sum),
                )
            )
            for face_index in cluster_faces:
                corner_lookup[(face_index, vertex_index)] = render_index

    render_faces = [
        tuple(
            corner_lookup[(face_index, vertex_index)]
            for vertex_index in face
        )
        for face_index, face in enumerate(faces)
    ]
    return _RenderGeometry(vertices=render_vertices, faces=render_faces)


class DistributionEditorWidget(QWidget):
    distribution_selected = pyqtSignal(str)
    distribution_changed = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DistributionEditor")
        self._loading = False
        self._feature_state: PropellerFeatureState | None = None
        self._stage = ACTIVE_PROPELLER_STAGES[0]
        self._distribution_keys: list[str] = []

        self.selector = QComboBox(self)
        self.selector.currentIndexChanged.connect(self._on_distribution_selection_changed)
        self.table = QTableWidget(0, 2, self)
        self.table.setObjectName("DistributionTable")
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(["eta", "value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._on_table_item_changed)
        self.add_button = QPushButton("Add Point", self)
        self.remove_button = QPushButton("Remove Point", self)
        self.add_button.clicked.connect(self._add_point)
        self.remove_button.clicked.connect(self._remove_selected_point)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.selector)
        layout.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.remove_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def bind_stage(self, feature_state: PropellerFeatureState, stage: str) -> None:
        self._feature_state = feature_state
        self._stage = stage
        self._distribution_keys = [
            key
            for key, distribution in feature_state.distributions.items()
            if distribution.stage == stage
        ]
        self._loading = True
        self.selector.clear()
        for key in self._distribution_keys:
            distribution = feature_state.distributions[key]
            self.selector.addItem(distribution.label, key)
        self._loading = False
        if self._distribution_keys:
            self.selector.setCurrentIndex(0)
            self._populate_table(self._distribution_keys[0])
        else:
            self.table.setRowCount(0)

    def current_distribution_key(self) -> str | None:
        current_data = self.selector.currentData()
        if isinstance(current_data, str) and current_data:
            return current_data
        return None

    def refresh(self) -> None:
        current_key = self.current_distribution_key()
        if current_key is not None:
            self._populate_table(current_key)

    def _on_distribution_selection_changed(self) -> None:
        distribution_key = self.current_distribution_key()
        if distribution_key is None:
            return
        self._populate_table(distribution_key)
        self.distribution_selected.emit(distribution_key)

    def _populate_table(self, distribution_key: str) -> None:
        if self._feature_state is None:
            return
        distribution = self._feature_state.distributions[distribution_key]
        self._loading = True
        self.table.setRowCount(len(distribution.control_points))
        for row_index, point in enumerate(distribution.control_points):
            self.table.setItem(row_index, 0, QTableWidgetItem(f"{point.eta:.3f}"))
            self.table.setItem(row_index, 1, QTableWidgetItem(f"{point.value:.4f}"))
        self._loading = False

    def _on_table_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._loading or self._feature_state is None:
            return
        distribution_key = self.current_distribution_key()
        if distribution_key is None:
            return

        distribution = self._feature_state.distributions[distribution_key]
        point_type = type(distribution.control_points[0])
        updated_points = []
        for row_index in range(self.table.rowCount()):
            eta_item = self.table.item(row_index, 0)
            value_item = self.table.item(row_index, 1)
            try:
                eta = float(eta_item.text()) if eta_item is not None else 0.0
                value = float(value_item.text()) if value_item is not None else 0.0
            except ValueError:
                return
            updated_points.append((eta, value))

        updated_points.sort(key=lambda item: item[0])
        distribution.control_points = [
            point_type(eta=eta, value=value)
            for eta, value in updated_points
        ]
        self.distribution_changed.emit(distribution_key, distribution.stage)

    def _add_point(self) -> None:
        if self._feature_state is None:
            return
        distribution_key = self.current_distribution_key()
        if distribution_key is None:
            return
        distribution = self._feature_state.distributions[distribution_key]
        points = distribution.control_points
        point_type = type(points[0])
        if points:
            eta = min(1.0, points[-1].eta + 0.05)
            value = points[-1].value
        else:
            eta = 0.5
            value = 0.0
        points.append(point_type(eta=eta, value=value))
        self._populate_table(distribution_key)
        self.distribution_changed.emit(distribution_key, distribution.stage)

    def _remove_selected_point(self) -> None:
        if self._feature_state is None:
            return
        distribution_key = self.current_distribution_key()
        if distribution_key is None:
            return
        distribution = self._feature_state.distributions[distribution_key]
        selected_rows = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        if len(distribution.control_points) - len(selected_rows) < 2:
            return
        for row_index in selected_rows:
            del distribution.control_points[row_index]
        self._populate_table(distribution_key)
        self.distribution_changed.emit(distribution_key, distribution.stage)


class RadialDistributionPlot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._feature_state: PropellerFeatureState | None = None
        self._preview_result: PropellerPreviewResult | None = None
        self._distribution_keys: list[str] = []
        self._highlight_key: str | None = None
        self._colors: dict[str, QColor] = {
            "background": QColor("#2f2f2f"),
            "border": QColor("#444444"),
            "muted": QColor("#999999"),
            "highlight": QColor("#0078d4"),
        }

    def set_plot_data(
        self,
        feature_state: PropellerFeatureState,
        preview_result: PropellerPreviewResult | None,
        distribution_keys: list[str],
        highlight_key: str | None,
    ) -> None:
        self._feature_state = feature_state
        self._preview_result = preview_result
        self._distribution_keys = distribution_keys
        self._highlight_key = highlight_key
        self.update()

    def apply_theme(self, colors: dict[str, str]) -> None:
        self._colors = {
            "background": QColor(colors["workspace_bg"]),
            "border": QColor(colors["border"]),
            "muted": QColor(colors["text_muted"]),
            "highlight": QColor(colors["accent"]),
        }
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self._colors["background"])
        painter.setPen(QPen(self._colors["border"], 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if self._feature_state is None or not self._distribution_keys:
            painter.setPen(self._colors["muted"])
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No radial data yet.")
            return

        plot_rect = self.rect().adjusted(44, 18, -16, -28)
        painter.setPen(QPen(self._colors["muted"], 1))
        painter.drawLine(plot_rect.bottomLeft(), plot_rect.bottomRight())
        painter.drawLine(plot_rect.bottomLeft(), plot_rect.topLeft())

        values: list[float] = []
        series_map: dict[str, list[tuple[float, float]]] = {}
        for key in self._distribution_keys:
            if self._preview_result is not None and key in self._preview_result.radial_series:
                samples = self._preview_result.radial_series[key]
            else:
                distribution = self._feature_state.distributions[key]
                samples = [(point.eta, point.value) for point in distribution.control_points]
            series_map[key] = samples
            values.extend(value for _eta, value in samples)

        min_value = min(values) if values else 0.0
        max_value = max(values) if values else 1.0
        if math.isclose(min_value, max_value):
            max_value = min_value + 1.0

        for index, key in enumerate(self._distribution_keys):
            samples = series_map[key]
            color = self._colors["highlight"] if key == self._highlight_key else _series_color(index)
            path = QPainterPath()
            for sample_index, (eta, value) in enumerate(samples):
                x = plot_rect.left() + eta * plot_rect.width()
                y_ratio = (value - min_value) / (max_value - min_value)
                y = plot_rect.bottom() - y_ratio * plot_rect.height()
                if sample_index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(color, 2 if key == self._highlight_key else 1.5))
            painter.drawPath(path)

        painter.setPen(self._colors["muted"])
        painter.drawText(8, plot_rect.top() + 12, f"{max_value:.3f}")
        painter.drawText(8, plot_rect.bottom(), f"{min_value:.3f}")


class SectionPreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._preview_result: PropellerPreviewResult | None = None
        self._colors = {
            "background": QColor("#2f2f2f"),
            "border": QColor("#444444"),
            "curve": QColor("#0078d4"),
            "curve_alt": QColor("#e8a628"),
            "muted": QColor("#999999"),
        }

    def set_preview_result(self, result: PropellerPreviewResult | None) -> None:
        self._preview_result = result
        self.update()

    def apply_theme(self, colors: dict[str, str]) -> None:
        self._colors = {
            "background": QColor(colors["workspace_bg"]),
            "border": QColor(colors["border"]),
            "curve": QColor(colors["accent"]),
            "curve_alt": QColor(colors["port_output"]),
            "muted": QColor(colors["text_muted"]),
        }
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), self._colors["background"])
        painter.setPen(QPen(self._colors["border"], 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self._preview_result is None or not self._preview_result.section_samples:
            painter.setPen(self._colors["muted"])
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Section preview waiting for geometry.")
            return

        section_curves = next(iter(self._preview_result.section_samples.values()))
        if len(section_curves) < 2:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Section preview unavailable.")
            return

        upper, lower = section_curves[0], section_curves[1]
        bounds = upper + lower
        min_x = min(point[0] for point in bounds)
        max_x = max(point[0] for point in bounds)
        min_y = min(point[1] for point in bounds)
        max_y = max(point[1] for point in bounds)
        if math.isclose(min_x, max_x):
            max_x = min_x + 1.0
        if math.isclose(min_y, max_y):
            max_y = min_y + 1.0

        plot_rect = self.rect().adjusted(34, 18, -18, -18)
        scale = min(
            plot_rect.width() / (max_x - min_x),
            plot_rect.height() / (max_y - min_y),
        ) * 0.92
        center_x = (min_x + max_x) * 0.5
        center_y = (min_y + max_y) * 0.5

        def map_point(point: tuple[float, float]) -> QPointF:
            return QPointF(
                plot_rect.center().x() + (point[0] - center_x) * scale,
                plot_rect.center().y() - (point[1] - center_y) * scale,
            )

        upper_path = QPainterPath()
        lower_path = QPainterPath()
        for index, point in enumerate(upper):
            mapped = map_point(point)
            if index == 0:
                upper_path.moveTo(mapped)
            else:
                upper_path.lineTo(mapped)
        for index, point in enumerate(lower):
            mapped = map_point(point)
            if index == 0:
                lower_path.moveTo(mapped)
            else:
                lower_path.lineTo(mapped)

        painter.setPen(QPen(self._colors["curve"], 2))
        painter.drawPath(upper_path)
        painter.setPen(QPen(self._colors["curve_alt"], 2))
        painter.drawPath(lower_path)


class _SoftwarePropellerViewportWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PropellerViewport")
        self.setMinimumWidth(320)
        self.setMinimumHeight(320)
        self._preview_result: PropellerPreviewResult | None = None
        self._background = QColor(_VIEWPORT_BACKGROUND_HEX)
        self._background_bottom = QColor(_VIEWPORT_BACKGROUND_BOTTOM_HEX)
        self._border = QColor("#444444")
        self._mesh_fill = QColor(_VIEWPORT_SURFACE_HEX)
        self._display_edge = QColor(_VIEWPORT_DISPLAY_EDGE_HEX)
        self._mesh_wire = QColor(_VIEWPORT_WIREFRAME_HEX)
        self._section_color = QColor("#e8a628")
        self._text = QColor("#e0e0e0")
        self._muted = QColor("#999999")
        self._show_mesh = True
        self._show_wireframe = True
        self._yaw = _DEFAULT_ISO_YAW
        self._pitch = _DEFAULT_ISO_PITCH
        self._roll = 0.0
        self._distance = 4.0
        self._center = (0.0, 0.0, 0.0)
        self._last_pos = QPoint()
        self._drag_mode: str | None = None
        self._bounds_extent = 2.0
        self._vertex_normals: list[tuple[float, float, float]] = []
        self._display_edges: list[_DisplayEdge] = []
        self._interactive_preview = False
        self._static_face_budget = 24000
        self._interactive_face_budget = 6000
        self._interaction_timer = QTimer(self)
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.setInterval(140)
        self._interaction_timer.timeout.connect(self._settle_interaction)

    def set_preview_result(self, result: PropellerPreviewResult | None) -> None:
        self._preview_result = result
        self._rebuild_display_edge_cache()
        self._rebuild_surface_cache()
        self._fit_to_mesh()
        self._settle_interaction()
        self.update()

    def mesh_face_count(self) -> int:
        if self._preview_result is None:
            return 0
        return len(self._preview_result.mesh.faces)

    def set_preview_options(self, show_mesh: bool, show_wireframe: bool) -> None:
        self._show_mesh = show_mesh
        self._show_wireframe = show_wireframe
        self.update()

    def reset_view(self) -> None:
        self.snap_to_named_view("Top-Front-Right")
        self._fit_to_mesh()
        self._settle_interaction()
        self.update()

    def apply_theme(self, colors: dict[str, str]) -> None:
        self._border = QColor(colors["border"])
        self._section_color = QColor(colors["port_output"])
        self._text = QColor(colors["text_primary"])
        self._muted = QColor(colors["text_muted"])
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _paint_viewport_background(
            painter,
            QRectF(self.rect()),
            self._background,
            self._background_bottom,
        )
        painter.setPen(QPen(self._border, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        camera = self._camera_state()
        face_step = 1
        if self._preview_result is not None and self._preview_result.mesh.vertices and self._preview_result.mesh.faces:
            vertices = self._preview_result.mesh.vertices
            faces = self._preview_result.mesh.faces
            projected_vertices = [
                self._project_point(point, camera.eye, camera.forward, camera.right, camera.up)
                for point in vertices
            ]
            target_faces = self._interactive_face_budget if self._interactive_preview else self._static_face_budget
            face_step = max(1, math.ceil(len(faces) / max(1, target_faces)))
            show_wireframe = self._show_wireframe and not self._interactive_preview
            face_polygons: list[tuple[float, QPolygonF, QColor]] = []
            for face_index in range(0, len(faces), face_step):
                face = faces[face_index]
                projected = (
                    projected_vertices[face[0]],
                    projected_vertices[face[1]],
                    projected_vertices[face[2]],
                )
                if any(point is None for point in projected):
                    continue
                points = [point for point in projected if point is not None]
                polygon = QPolygonF([QPointF(point.x, point.y) for point in points])
                if self._vertex_normals:
                    n0 = self._vertex_normals[face[0]]
                    n1 = self._vertex_normals[face[1]]
                    n2 = self._vertex_normals[face[2]]
                    normal = _normalize(
                        (
                            n0[0] + n1[0] + n2[0],
                            n0[1] + n1[1] + n2[1],
                            n0[2] + n1[2] + n2[2],
                        )
                    )
                else:
                    world = [vertices[face[0]], vertices[face[1]], vertices[face[2]]]
                    normal = _normalize(_cross(_sub(world[1], world[0]), _sub(world[2], world[0])))
                fill = _color_with_brightness(
                    self._mesh_fill,
                    _surface_brightness(normal),
                    _SURFACE_PASS_CONFIG.alpha,
                )
                face_polygons.append((sum(point.depth for point in points) / len(points), polygon, fill))

            face_polygons.sort(key=lambda item: item[0], reverse=True)
            for _depth, polygon, fill in face_polygons:
                painter.setBrush(fill if self._show_mesh else Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(fill if self._show_mesh else self._mesh_wire, 0 if self._show_mesh else 1))
                painter.drawPolygon(polygon)

            if self._show_mesh:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(self._display_edge, 1.1))
                for start, end in self._visible_display_edges(camera):
                    start_point = projected_vertices[start]
                    end_point = projected_vertices[end]
                    if start_point is None or end_point is None:
                        continue
                    painter.drawLine(
                        QPointF(start_point.x, start_point.y),
                        QPointF(end_point.x, end_point.y),
                    )

            if show_wireframe:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(self._mesh_wire, 0.9))
                for a, b, c in faces:
                    for start, end in ((a, b), (b, c), (c, a)):
                        start_point = projected_vertices[start]
                        end_point = projected_vertices[end]
                        if start_point is None or end_point is None:
                            continue
                        painter.drawLine(
                            QPointF(start_point.x, start_point.y),
                            QPointF(end_point.x, end_point.y),
                        )

            if self._preview_result.mesh.section_polylines and not self._interactive_preview:
                painter.setPen(QPen(self._section_color, 1.2, Qt.PenStyle.DashLine))
                for polyline in self._preview_result.mesh.section_polylines:
                    path = QPainterPath()
                    started = False
                    for point in polyline:
                        projected = self._project_point(
                            point,
                            camera.eye,
                            camera.forward,
                            camera.right,
                            camera.up,
                        )
                        if projected is None:
                            continue
                        if not started:
                            path.moveTo(projected.x, projected.y)
                            started = True
                        else:
                            path.lineTo(projected.x, projected.y)
                    if started:
                        painter.drawPath(path)
        else:
            painter.setPen(self._muted)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "3D preview waiting for geometry.")

        self._draw_overlay_chrome(
            painter,
            camera,
            adaptive_text=(
                None
                if self._preview_result is None or face_step <= 1
                else f"Adaptive preview: {math.ceil(len(self._preview_result.mesh.faces) / face_step):,} of {len(self._preview_result.mesh.faces):,} faces"
            ),
        )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._last_pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            target = self._hit_test_view_cube(event.position().toPoint())
            if target is not None:
                self._apply_view_cube_hotspot(target)
                event.accept()
                return
            self._drag_mode = "orbit"
        elif event.button() == Qt.MouseButton.RightButton:
            self._drag_mode = "pan"
        else:
            self._drag_mode = None
        if self._drag_mode is not None:
            self._begin_interaction()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_mode is None:
            super().mouseMoveEvent(event)
            return

        position = event.position().toPoint()
        delta = position - self._last_pos
        self._last_pos = position
        if self._drag_mode == "orbit":
            self._yaw, self._pitch, self._roll = _rotate_camera_angles(
                self._yaw,
                self._pitch,
                self._roll,
                "screen_up",
                delta.x() * 0.6,
            )
            self._yaw, self._pitch, self._roll = _rotate_camera_angles(
                self._yaw,
                self._pitch,
                self._roll,
                "screen_right",
                -delta.y() * 0.4,
            )
        else:
            _, _forward, right, up = self._build_projection()
            scale = self._distance * 0.0018
            self._center = (
                self._center[0] - right[0] * delta.x() * scale + up[0] * delta.y() * scale,
                self._center[1] - right[1] * delta.x() * scale + up[1] * delta.y() * scale,
                self._center[2] - right[2] * delta.x() * scale + up[2] * delta.y() * scale,
            )
        self._begin_interaction()
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_mode = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        factor = 0.86 if event.angleDelta().y() > 0 else 1.16
        self._distance = max(self._bounds_extent * 0.6, min(self._bounds_extent * 30.0, self._distance * factor))
        self._begin_interaction()
        self.update()
        super().wheelEvent(event)

    def snap_to_named_view(self, view_name: str) -> None:
        eye_direction = _named_view_eye_direction(view_name)
        self._yaw = math.degrees(math.atan2(eye_direction[1], eye_direction[0]))
        self._pitch = math.degrees(math.asin(max(-1.0, min(1.0, eye_direction[2]))))
        self._roll = 0.0
        self._drag_mode = None
        self._settle_interaction()
        self.update()

    def _apply_view_cube_hotspot(self, hotspot: _ViewCubeHotspot) -> None:
        self._yaw, self._pitch, self._roll = _apply_view_cube_hotspot(
            self._yaw,
            self._pitch,
            self._roll,
            hotspot,
        )
        self._drag_mode = None
        self._settle_interaction()
        self.update()

    def _begin_interaction(self) -> None:
        self._interactive_preview = True
        self._interaction_timer.start()

    def _settle_interaction(self) -> None:
        if not self._interactive_preview:
            return
        self._interactive_preview = False
        self.update()

    def _rebuild_surface_cache(self) -> None:
        self._vertex_normals = []
        if self._preview_result is None:
            return
        vertices = self._preview_result.mesh.vertices
        faces = self._preview_result.mesh.faces
        if not vertices or not faces:
            return

        accumulated = [[0.0, 0.0, 0.0] for _ in vertices]
        for a, b, c in faces:
            normal = _cross(_sub(vertices[b], vertices[a]), _sub(vertices[c], vertices[a]))
            for index in (a, b, c):
                accumulated[index][0] += normal[0]
                accumulated[index][1] += normal[1]
                accumulated[index][2] += normal[2]
        self._vertex_normals = [
            _normalize((normal[0], normal[1], normal[2])) for normal in accumulated
        ]

    def _rebuild_display_edge_cache(self) -> None:
        self._display_edges = []
        if self._preview_result is None:
            return
        self._display_edges = _build_display_edges(
            self._preview_result.mesh.vertices,
            self._preview_result.mesh.faces,
        )

    def _visible_display_edges(
        self,
        camera: _ViewportCameraState,
    ) -> list[tuple[int, int]]:
        if self._preview_result is None:
            return []
        faces = self._preview_result.mesh.faces
        face_visibility = [
            _dot(_face_normal(self._preview_result.mesh.vertices, face), camera.eye_direction) > 0.0
            for face in faces
        ]
        visible_edges: list[tuple[int, int]] = []
        for edge in self._display_edges:
            if any(face_visibility[face_index] for face_index in edge.adjacent_faces if face_index < len(face_visibility)):
                visible_edges.append((edge.start, edge.end))
        return visible_edges

    def _fit_to_mesh(self) -> None:
        if self._preview_result is None or not self._preview_result.mesh.vertices:
            self._center = (0.0, 0.0, 0.0)
            self._distance = 4.0
            self._bounds_extent = 2.0
            return
        bounds_min = self._preview_result.model_metadata.bounds_min
        bounds_max = self._preview_result.model_metadata.bounds_max
        if len(bounds_min) == 3 and len(bounds_max) == 3:
            min_x, min_y, min_z = bounds_min
            max_x, max_y, max_z = bounds_max
        else:
            vertices = self._preview_result.mesh.vertices
            xs = [point[0] for point in vertices]
            ys = [point[1] for point in vertices]
            zs = [point[2] for point in vertices]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            min_z, max_z = min(zs), max(zs)
        self._center = (
            (min_x + max_x) * 0.5,
            (min_y + max_y) * 0.5,
            (min_z + max_z) * 0.5,
        )
        self._bounds_extent = max(
            max_x - min_x,
            max_y - min_y,
            max_z - min_z,
            1.0,
        )
        self._distance = self._bounds_extent * 2.2

    def _camera_state(self) -> _ViewportCameraState:
        return _camera_state(self._center, self._distance, self._yaw, self._pitch, self._roll)

    def _view_cube_overlay(self) -> _ViewCubeOverlay:
        return _build_view_cube_overlay(self._camera_state(), float(self.width()), float(self.height()))

    def _hit_test_view_cube(self, point: QPoint) -> _ViewCubeHotspot | None:
        return _hit_test_view_cube_overlay(self._view_cube_overlay(), (float(point.x()), float(point.y())))

    def _draw_overlay_chrome(
        self,
        painter: QPainter,
        camera: _ViewportCameraState,
        adaptive_text: str | None = None,
    ) -> None:
        painter.setPen(self._text)
        painter.drawText(16, 22, "Blade Preview")
        painter.setPen(self._muted)
        painter.drawText(16, 40, "Left drag: orbit | Right drag: pan | Wheel: zoom | Cube: snap views")
        if adaptive_text:
            painter.drawText(16, 58, adaptive_text)
        _draw_axis_triad_overlay(painter, camera, float(self.height()))
        _draw_view_cube_overlay(painter, self._view_cube_overlay())

    def _build_projection(self):
        camera = self._camera_state()
        return camera.eye, camera.forward, camera.right, camera.up

    def _project_point(
        self,
        point: tuple[float, float, float],
        eye: tuple[float, float, float],
        forward: tuple[float, float, float],
        right: tuple[float, float, float],
        up: tuple[float, float, float],
    ) -> _ProjectedPoint | None:
        relative = _sub(point, eye)
        cam_x = _dot(relative, right)
        cam_y = _dot(relative, up)
        cam_z = _dot(relative, forward)
        if cam_z <= 1e-3:
            return None
        fov = math.radians(46.0)
        aspect = max(1.0, self.width()) / max(1.0, self.height())
        scale = 1.0 / math.tan(fov / 2.0)
        ndc_x = (cam_x * scale / aspect) / cam_z
        ndc_y = (cam_y * scale) / cam_z
        screen_x = (ndc_x + 1.0) * 0.5 * self.width()
        screen_y = (1.0 - ndc_y) * 0.5 * self.height()
        return _ProjectedPoint(screen_x, screen_y, cam_z)


def _should_use_opengl_viewport() -> bool:
    if not _HAS_QT_OPENGL:
        return False
    if os.environ.get("ROTORLAB_FORCE_SOFTWARE_VIEWPORT") == "1":
        return False
    if "PYTEST_CURRENT_TEST" in os.environ or "PYTEST_VERSION" in os.environ:
        return False
    qpa_platform = (os.environ.get("QT_QPA_PLATFORM") or "").lower()
    if qpa_platform in {"offscreen", "minimal"}:
        return False
    app = QApplication.instance()
    platform_name = app.platformName().lower() if app is not None else ""
    return platform_name not in {"offscreen", "minimal"}


if _HAS_QT_OPENGL:
    class _OpenGLPropellerViewportWidget(QOpenGLWidget):
        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("PropellerViewport")
            self.setMinimumWidth(320)
            self.setMinimumHeight(320)
            self._preview_result: PropellerPreviewResult | None = None
            self._background = QColor(_VIEWPORT_BACKGROUND_HEX)
            self._background_bottom = QColor(_VIEWPORT_BACKGROUND_BOTTOM_HEX)
            self._border = QColor("#444444")
            self._mesh_fill = QColor(_VIEWPORT_SURFACE_HEX)
            self._display_edge = QColor(_VIEWPORT_DISPLAY_EDGE_HEX)
            self._mesh_wire = QColor(_VIEWPORT_WIREFRAME_HEX)
            self._section_color = QColor("#e8a628")
            self._text = QColor("#e0e0e0")
            self._muted = QColor("#999999")
            self._show_mesh = True
            self._show_wireframe = True
            self._yaw = _DEFAULT_ISO_YAW
            self._pitch = _DEFAULT_ISO_PITCH
            self._roll = 0.0
            self._distance = 4.0
            self._center = (0.0, 0.0, 0.0)
            self._last_pos = QPoint()
            self._drag_mode: str | None = None
            self._bounds_extent = 2.0
            self._interactive_preview = False
            self._interactive_face_budget = 7000
            self._interaction_timer = QTimer(self)
            self._interaction_timer.setSingleShot(True)
            self._interaction_timer.setInterval(140)
            self._interaction_timer.timeout.connect(self._settle_interaction)

            self._render_geometry = _RenderGeometry(vertices=[], faces=[])
            self._mesh_vertex_blob = b""
            self._line_vertex_blob = b""
            self._mesh_triangle_blob = b""
            self._mesh_interactive_triangle_blob = b""
            self._mesh_wire_blob = b""
            self._display_edge_blob = b""
            self._section_vertex_blob = b""
            self._mesh_triangle_count = 0
            self._mesh_interactive_triangle_count = 0
            self._mesh_wire_count = 0
            self._display_edge_count = 0
            self._section_ranges: list[tuple[int, int]] = []
            self._display_edges: list[_DisplayEdge] = []

            self._mesh_program: QOpenGLShaderProgram | None = None
            self._line_program: QOpenGLShaderProgram | None = None
            self._mesh_vertex_buffer: QOpenGLBuffer | None = None
            self._line_vertex_buffer: QOpenGLBuffer | None = None
            self._mesh_index_buffer: QOpenGLBuffer | None = None
            self._mesh_interactive_index_buffer: QOpenGLBuffer | None = None
            self._mesh_wire_index_buffer: QOpenGLBuffer | None = None
            self._display_edge_index_buffer: QOpenGLBuffer | None = None
            self._section_vertex_buffer: QOpenGLBuffer | None = None
            self._gl = None
            self._gl_ready = False
            self._gpu_dirty = False

        def set_preview_result(self, result: PropellerPreviewResult | None) -> None:
            self._preview_result = result
            self._prepare_geometry_payloads()
            self._fit_to_mesh()
            self._settle_interaction()
            self.update()

        def mesh_face_count(self) -> int:
            if self._preview_result is None:
                return 0
            return len(self._preview_result.mesh.faces)

        def set_preview_options(self, show_mesh: bool, show_wireframe: bool) -> None:
            self._show_mesh = show_mesh
            self._show_wireframe = show_wireframe
            self.update()

        def reset_view(self) -> None:
            self.snap_to_named_view("Top-Front-Right")
            self._fit_to_mesh()
            self._settle_interaction()
            self.update()

        def apply_theme(self, colors: dict[str, str]) -> None:
            self._border = QColor(colors["border"])
            self._section_color = QColor(colors["port_output"])
            self._text = QColor(colors["text_primary"])
            self._muted = QColor(colors["text_muted"])
            self.update()

        def initializeGL(self) -> None:  # type: ignore[override]
            profile = QOpenGLVersionProfile()
            profile.setVersion(2, 0)
            self._gl = QOpenGLVersionFunctionsFactory.get(profile, self.context())
            if self._gl is None:
                raise RuntimeError("Could not create OpenGL 2.0 function table.")
            self._gl.initializeOpenGLFunctions()
            self._gl.glEnable(GL_DEPTH_TEST)
            self._gl.glDisable(GL_BLEND)
            self._gl.glDisable(GL_CULL_FACE)
            self._create_programs()
            self._create_buffers()
            self._gl_ready = True
            self._upload_buffers()

        def paintGL(self) -> None:  # type: ignore[override]
            if self._gl is None:
                return
            gl = self._gl
            camera = self._camera_state()
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, not self._interactive_preview)
            _paint_viewport_background(
                painter,
                QRectF(self.rect()),
                self._background,
                self._background_bottom,
            )

            painter.beginNativePainting()
            gl.glClear(GL_DEPTH_BUFFER_BIT)
            if self._gpu_dirty:
                self._upload_buffers()
            if self._preview_result is not None and self._mesh_triangle_count:
                mvp_matrix = self._build_mvp_matrix()
                self._apply_pass_config(gl, _SURFACE_PASS_CONFIG)
                self._draw_mesh(gl, mvp_matrix)
                self._apply_pass_config(gl, _OVERLAY_PASS_CONFIG)
                self._draw_overlays(gl, mvp_matrix)
                gl.glDepthMask(True)
                gl.glDisable(GL_BLEND)
            painter.endNativePainting()

            painter.setPen(QPen(self._border, 1))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            if self._preview_result is None or not self._mesh_triangle_count:
                painter.setPen(self._muted)
                painter.drawText(
                    self.rect(),
                    Qt.AlignmentFlag.AlignCenter,
                    "3D preview waiting for geometry.",
                )
            self._draw_overlay_chrome(
                painter,
                camera,
                adaptive_text=(
                    None
                    if not self._interactive_preview or not self._mesh_interactive_triangle_count
                    else f"Adaptive preview: {self._mesh_interactive_triangle_count // 3:,} of {self._mesh_triangle_count // 3:,} faces"
                ),
            )

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            self._last_pos = event.position().toPoint()
            if event.button() == Qt.MouseButton.LeftButton:
                target = self._hit_test_view_cube(event.position().toPoint())
                if target is not None:
                    self._apply_view_cube_hotspot(target)
                    event.accept()
                    return
                self._drag_mode = "orbit"
            elif event.button() == Qt.MouseButton.RightButton:
                self._drag_mode = "pan"
            else:
                self._drag_mode = None
            if self._drag_mode is not None:
                self._begin_interaction()
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
            if self._drag_mode is None:
                super().mouseMoveEvent(event)
                return

            position = event.position().toPoint()
            delta = position - self._last_pos
            self._last_pos = position
            if self._drag_mode == "orbit":
                self._yaw, self._pitch, self._roll = _rotate_camera_angles(
                    self._yaw,
                    self._pitch,
                    self._roll,
                    "screen_up",
                    delta.x() * 0.6,
                )
                self._yaw, self._pitch, self._roll = _rotate_camera_angles(
                    self._yaw,
                    self._pitch,
                    self._roll,
                    "screen_right",
                    -delta.y() * 0.4,
                )
            else:
                _, _forward, right, up = self._build_projection()
                scale = self._distance * 0.0018
                self._center = (
                    self._center[0] - right[0] * delta.x() * scale + up[0] * delta.y() * scale,
                    self._center[1] - right[1] * delta.x() * scale + up[1] * delta.y() * scale,
                    self._center[2] - right[2] * delta.x() * scale + up[2] * delta.y() * scale,
                )
            self._begin_interaction()
            self.update()
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
            self._drag_mode = None
            super().mouseReleaseEvent(event)

        def wheelEvent(self, event) -> None:  # type: ignore[override]
            factor = 0.86 if event.angleDelta().y() > 0 else 1.16
            self._distance = max(
                self._bounds_extent * 0.6,
                min(self._bounds_extent * 30.0, self._distance * factor),
            )
            self._begin_interaction()
            self.update()
            super().wheelEvent(event)

        def snap_to_named_view(self, view_name: str) -> None:
            eye_direction = _named_view_eye_direction(view_name)
            self._yaw = math.degrees(math.atan2(eye_direction[1], eye_direction[0]))
            self._pitch = math.degrees(math.asin(max(-1.0, min(1.0, eye_direction[2]))))
            self._roll = 0.0
            self._drag_mode = None
            self._settle_interaction()
            self.update()

        def _apply_view_cube_hotspot(self, hotspot: _ViewCubeHotspot) -> None:
            self._yaw, self._pitch, self._roll = _apply_view_cube_hotspot(
                self._yaw,
                self._pitch,
                self._roll,
                hotspot,
            )
            self._drag_mode = None
            self._settle_interaction()
            self.update()

        def _create_programs(self) -> None:
            mesh_program = QOpenGLShaderProgram(self)
            mesh_program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Vertex,
                """
                #version 120
                attribute vec3 a_position;
                attribute vec3 a_normal;
                uniform mat4 u_mvp_matrix;
                varying vec3 v_normal;
                void main() {
                    v_normal = normalize(a_normal);
                    gl_Position = u_mvp_matrix * vec4(a_position, 1.0);
                }
                """,
            )
            mesh_program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Fragment,
                """
                #version 120
                uniform vec4 u_base_color;
                uniform vec3 u_light_direction;
                varying vec3 v_normal;
                void main() {
                    float diffuse = max(dot(normalize(v_normal), normalize(u_light_direction)), 0.0);
                    float brightness = 0.86 + diffuse * 0.12;
                    gl_FragColor = vec4(u_base_color.rgb * brightness, u_base_color.a);
                }
                """,
            )
            mesh_program.bindAttributeLocation("a_position", 0)
            mesh_program.bindAttributeLocation("a_normal", 1)
            mesh_program.link()

            line_program = QOpenGLShaderProgram(self)
            line_program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Vertex,
                """
                #version 120
                attribute vec3 a_position;
                uniform mat4 u_mvp_matrix;
                uniform float u_depth_bias;
                void main() {
                    vec4 clip_position = u_mvp_matrix * vec4(a_position, 1.0);
                    clip_position.z -= u_depth_bias * clip_position.w;
                    gl_Position = clip_position;
                }
                """,
            )
            line_program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Fragment,
                """
                #version 120
                uniform vec4 u_base_color;
                void main() {
                    gl_FragColor = u_base_color;
                }
                """,
            )
            line_program.bindAttributeLocation("a_position", 0)
            line_program.link()

            self._mesh_program = mesh_program
            self._line_program = line_program

        def _create_buffers(self) -> None:
            self._mesh_vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self._mesh_vertex_buffer.create()
            self._line_vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self._line_vertex_buffer.create()
            self._mesh_index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
            self._mesh_index_buffer.create()
            self._mesh_interactive_index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
            self._mesh_interactive_index_buffer.create()
            self._mesh_wire_index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
            self._mesh_wire_index_buffer.create()
            self._display_edge_index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
            self._display_edge_index_buffer.create()
            self._section_vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self._section_vertex_buffer.create()

        def _apply_pass_config(self, gl, config: _RenderPassConfig) -> None:
            gl.glEnable(GL_DEPTH_TEST)
            gl.glDepthMask(config.depth_write_enabled)
            if config.blending_enabled:
                gl.glEnable(GL_BLEND)
                gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            else:
                gl.glDisable(GL_BLEND)

        def _prepare_geometry_payloads(self) -> None:
            self._render_geometry = _RenderGeometry(vertices=[], faces=[])
            self._mesh_vertex_blob = b""
            self._line_vertex_blob = b""
            self._mesh_triangle_blob = b""
            self._mesh_interactive_triangle_blob = b""
            self._mesh_wire_blob = b""
            self._display_edge_blob = b""
            self._section_vertex_blob = b""
            self._mesh_triangle_count = 0
            self._mesh_interactive_triangle_count = 0
            self._mesh_wire_count = 0
            self._display_edge_count = 0
            self._section_ranges = []
            self._display_edges = []

            if self._preview_result is None:
                self._gpu_dirty = True
                return

            vertices = self._preview_result.mesh.vertices
            faces = self._preview_result.mesh.faces
            if not vertices or not faces:
                self._gpu_dirty = True
                return

            self._render_geometry = _build_crease_aware_render_geometry(vertices, faces)
            if not self._render_geometry.vertices or not self._render_geometry.faces:
                self._gpu_dirty = True
                return

            line_vertices = array("f")
            for vertex in vertices:
                line_vertices.extend([float(vertex[0]), float(vertex[1]), float(vertex[2])])
            self._line_vertex_blob = line_vertices.tobytes()

            mesh_vertices = array("f")
            for render_vertex in self._render_geometry.vertices:
                mesh_vertices.extend(
                    [
                        float(render_vertex.position[0]),
                        float(render_vertex.position[1]),
                        float(render_vertex.position[2]),
                        float(render_vertex.normal[0]),
                        float(render_vertex.normal[1]),
                        float(render_vertex.normal[2]),
                    ]
                )
            self._mesh_vertex_blob = mesh_vertices.tobytes()

            render_faces = self._render_geometry.faces
            face_step = max(1, math.ceil(len(render_faces) / self._interactive_face_budget))
            interactive_faces = render_faces[::face_step]

            triangle_indices = array("I")
            for a, b, c in render_faces:
                triangle_indices.extend([a, b, c])
            self._mesh_triangle_blob = triangle_indices.tobytes()
            self._mesh_triangle_count = len(triangle_indices)

            interactive_triangle_indices = array("I")
            for a, b, c in interactive_faces:
                interactive_triangle_indices.extend([a, b, c])
            self._mesh_interactive_triangle_blob = interactive_triangle_indices.tobytes()
            self._mesh_interactive_triangle_count = len(interactive_triangle_indices)

            wire_indices = array("I")
            for a, b, c in faces:
                wire_indices.extend([a, b, b, c, c, a])
            self._mesh_wire_blob = wire_indices.tobytes()
            self._mesh_wire_count = len(wire_indices)

            self._display_edges = _build_display_edges(vertices, faces)
            display_edge_indices = array("I")
            for edge in self._display_edges:
                display_edge_indices.extend([edge.start, edge.end])
            self._display_edge_blob = display_edge_indices.tobytes()
            self._display_edge_count = len(display_edge_indices)

            section_vertices = array("f")
            vertex_offset = 0
            for polyline in self._preview_result.mesh.section_polylines:
                if len(polyline) < 2:
                    continue
                self._section_ranges.append((vertex_offset, len(polyline)))
                for point in polyline:
                    section_vertices.extend(
                        [float(point[0]), float(point[1]), float(point[2])]
                    )
                vertex_offset += len(polyline)
            self._section_vertex_blob = section_vertices.tobytes()
            self._gpu_dirty = True

        def _upload_buffers(self) -> None:
            if not self._gl_ready:
                return
            if self._mesh_vertex_buffer is not None:
                blob_size = len(self._mesh_vertex_blob)
                if blob_size:
                    self._mesh_vertex_buffer.bind()
                    self._mesh_vertex_buffer.allocate(self._mesh_vertex_blob, blob_size)
                    self._mesh_vertex_buffer.release()
            if self._line_vertex_buffer is not None:
                blob_size = len(self._line_vertex_blob)
                if blob_size:
                    self._line_vertex_buffer.bind()
                    self._line_vertex_buffer.allocate(self._line_vertex_blob, blob_size)
                    self._line_vertex_buffer.release()
            if self._mesh_index_buffer is not None:
                blob_size = len(self._mesh_triangle_blob)
                if blob_size:
                    self._mesh_index_buffer.bind()
                    self._mesh_index_buffer.allocate(self._mesh_triangle_blob, blob_size)
                    self._mesh_index_buffer.release()
            if self._mesh_interactive_index_buffer is not None:
                blob_size = len(self._mesh_interactive_triangle_blob)
                if blob_size:
                    self._mesh_interactive_index_buffer.bind()
                    self._mesh_interactive_index_buffer.allocate(
                        self._mesh_interactive_triangle_blob,
                        blob_size,
                    )
                    self._mesh_interactive_index_buffer.release()
            if self._mesh_wire_index_buffer is not None:
                blob_size = len(self._mesh_wire_blob)
                if blob_size:
                    self._mesh_wire_index_buffer.bind()
                    self._mesh_wire_index_buffer.allocate(self._mesh_wire_blob, blob_size)
                    self._mesh_wire_index_buffer.release()
            if self._display_edge_index_buffer is not None:
                blob_size = len(self._display_edge_blob)
                if blob_size:
                    self._display_edge_index_buffer.bind()
                    self._display_edge_index_buffer.allocate(
                        self._display_edge_blob,
                        blob_size,
                    )
                    self._display_edge_index_buffer.release()
            if self._section_vertex_buffer is not None:
                blob_size = len(self._section_vertex_blob)
                if blob_size:
                    self._section_vertex_buffer.bind()
                    self._section_vertex_buffer.allocate(self._section_vertex_blob, blob_size)
                    self._section_vertex_buffer.release()
            self._gpu_dirty = False

        def _draw_mesh(self, gl, mvp_matrix: QMatrix4x4) -> None:
            if self._mesh_program is None or self._mesh_vertex_buffer is None:
                return
            if self._show_mesh:
                triangle_count = (
                    self._mesh_interactive_triangle_count
                    if self._interactive_preview
                    else self._mesh_triangle_count
                )
                index_buffer = (
                    self._mesh_interactive_index_buffer
                    if self._interactive_preview
                    else self._mesh_index_buffer
                )
                if triangle_count and index_buffer is not None:
                    self._mesh_program.bind()
                    self._mesh_program.setUniformValue("u_mvp_matrix", mvp_matrix)
                    self._mesh_program.setUniformValue(
                        "u_light_direction", QVector3D(*_normalize(_VIEWPORT_LIGHT_DIRECTION))
                    )
                    self._mesh_program.setUniformValue(
                        "u_base_color",
                        QVector4D(
                            self._mesh_fill.redF(),
                            self._mesh_fill.greenF(),
                            self._mesh_fill.blueF(),
                            _SURFACE_PASS_CONFIG.alpha,
                        ),
                    )
                    self._mesh_vertex_buffer.bind()
                    self._mesh_program.enableAttributeArray(0)
                    self._mesh_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 24)
                    self._mesh_program.enableAttributeArray(1)
                    self._mesh_program.setAttributeBuffer(1, GL_FLOAT, 12, 3, 24)
                    index_buffer.bind()
                    gl.glDrawElements(GL_TRIANGLES, triangle_count, GL_UNSIGNED_INT, None)
                    index_buffer.release()
                    self._mesh_vertex_buffer.release()
                    self._mesh_program.disableAttributeArray(0)
                    self._mesh_program.disableAttributeArray(1)
                    self._mesh_program.release()

        def _draw_overlays(self, gl, mvp_matrix: QMatrix4x4) -> None:
            if self._line_program is None:
                return

            if self._show_mesh and self._display_edge_count and self._line_vertex_buffer is not None and self._display_edge_index_buffer is not None:
                self._line_program.bind()
                self._line_program.setUniformValue("u_mvp_matrix", mvp_matrix)
                self._line_program.setUniformValue("u_depth_bias", _DISPLAY_EDGE_DEPTH_BIAS)
                self._line_program.setUniformValue(
                    "u_base_color",
                    QVector4D(
                        self._display_edge.redF(),
                        self._display_edge.greenF(),
                        self._display_edge.blueF(),
                        1.0,
                    ),
                )
                self._line_vertex_buffer.bind()
                self._line_program.enableAttributeArray(0)
                self._line_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 12)
                self._display_edge_index_buffer.bind()
                gl.glDrawElements(GL_LINES, self._display_edge_count, GL_UNSIGNED_INT, None)
                self._display_edge_index_buffer.release()
                self._line_vertex_buffer.release()
                self._line_program.disableAttributeArray(0)
                self._line_program.release()

            if self._interactive_preview:
                return

            if self._show_wireframe and self._line_vertex_buffer is not None:
                wire_count = self._mesh_wire_count
                wire_buffer = self._mesh_wire_index_buffer
                if wire_count and wire_buffer is not None:
                    self._line_program.bind()
                    self._line_program.setUniformValue("u_mvp_matrix", mvp_matrix)
                    self._line_program.setUniformValue("u_depth_bias", _OVERLAY_DEPTH_BIAS)
                    self._line_program.setUniformValue(
                        "u_base_color",
                        QVector4D(
                            self._mesh_wire.redF(),
                            self._mesh_wire.greenF(),
                            self._mesh_wire.blueF(),
                            _OVERLAY_PASS_CONFIG.alpha,
                        ),
                    )
                    self._line_vertex_buffer.bind()
                    self._line_program.enableAttributeArray(0)
                    self._line_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 12)
                    wire_buffer.bind()
                    gl.glDrawElements(GL_LINES, wire_count, GL_UNSIGNED_INT, None)
                    wire_buffer.release()
                    self._line_vertex_buffer.release()
                    self._line_program.disableAttributeArray(0)
                    self._line_program.release()

            if self._section_vertex_buffer is None or not self._section_ranges:
                return
            self._line_program.bind()
            self._line_program.setUniformValue("u_mvp_matrix", mvp_matrix)
            self._line_program.setUniformValue("u_depth_bias", _OVERLAY_DEPTH_BIAS)
            self._line_program.setUniformValue(
                "u_base_color",
                QVector4D(
                    self._section_color.redF(),
                    self._section_color.greenF(),
                    self._section_color.blueF(),
                    _SECTION_OVERLAY_ALPHA,
                ),
            )
            self._section_vertex_buffer.bind()
            self._line_program.enableAttributeArray(0)
            self._line_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 0)
            for offset, count in self._section_ranges:
                gl.glDrawArrays(GL_LINE_STRIP, offset, count)
            self._section_vertex_buffer.release()
            self._line_program.disableAttributeArray(0)
            self._line_program.release()

        def _begin_interaction(self) -> None:
            self._interactive_preview = True
            self._interaction_timer.start()

        def _settle_interaction(self) -> None:
            if not self._interactive_preview:
                return
            self._interactive_preview = False
            self.update()

        def _fit_to_mesh(self) -> None:
            if self._preview_result is None or not self._preview_result.mesh.vertices:
                self._center = (0.0, 0.0, 0.0)
                self._distance = 4.0
                self._bounds_extent = 2.0
                return
            bounds_min = self._preview_result.model_metadata.bounds_min
            bounds_max = self._preview_result.model_metadata.bounds_max
            if len(bounds_min) == 3 and len(bounds_max) == 3:
                min_x, min_y, min_z = bounds_min
                max_x, max_y, max_z = bounds_max
            else:
                vertices = self._preview_result.mesh.vertices
                xs = [point[0] for point in vertices]
                ys = [point[1] for point in vertices]
                zs = [point[2] for point in vertices]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                min_z, max_z = min(zs), max(zs)
            self._center = (
                (min_x + max_x) * 0.5,
                (min_y + max_y) * 0.5,
                (min_z + max_z) * 0.5,
            )
            self._bounds_extent = max(
                max_x - min_x,
                max_y - min_y,
                max_z - min_z,
                1.0,
            )
            self._distance = self._bounds_extent * 2.2

        def _camera_state(self) -> _ViewportCameraState:
            return _camera_state(self._center, self._distance, self._yaw, self._pitch, self._roll)

        def _view_cube_overlay(self) -> _ViewCubeOverlay:
            return _build_view_cube_overlay(self._camera_state(), float(self.width()), float(self.height()))

        def _hit_test_view_cube(self, point: QPoint) -> _ViewCubeHotspot | None:
            return _hit_test_view_cube_overlay(self._view_cube_overlay(), (float(point.x()), float(point.y())))

        def _draw_overlay_chrome(
            self,
            painter: QPainter,
            camera: _ViewportCameraState,
            adaptive_text: str | None = None,
        ) -> None:
            painter.setPen(self._text)
            painter.drawText(16, 22, "Blade Preview")
            painter.setPen(self._muted)
            painter.drawText(16, 40, "Left drag: orbit | Right drag: pan | Wheel: zoom | Cube: snap views")
            if adaptive_text:
                painter.drawText(16, 58, adaptive_text)
            _draw_axis_triad_overlay(painter, camera, float(self.height()))
            _draw_view_cube_overlay(painter, self._view_cube_overlay())

        def _build_projection(self):
            camera = self._camera_state()
            return camera.eye, camera.forward, camera.right, camera.up

        def _build_mvp_matrix(self) -> QMatrix4x4:
            eye, _forward, _right, up = self._build_projection()
            view = QMatrix4x4()
            view.lookAt(
                QVector3D(*eye),
                QVector3D(*self._center),
                QVector3D(*up),
            )
            projection = QMatrix4x4()
            aspect = max(1.0, self.width()) / max(1.0, self.height())
            near_plane = max(self._bounds_extent * 0.02, 0.1)
            far_plane = max(self._distance + self._bounds_extent * 6.0, near_plane + 10.0)
            projection.perspective(46.0, aspect, near_plane, far_plane)
            return projection * view
else:  # pragma: no cover - depends on Qt installation
    class _OpenGLPropellerViewportWidget(QWidget):
        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            raise RuntimeError("Qt OpenGL modules are unavailable.")


class PropellerViewportWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PropellerViewportHost")
        self.setMinimumWidth(320)
        self.setMinimumHeight(320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if _should_use_opengl_viewport():
            try:
                self._canvas: QWidget = _OpenGLPropellerViewportWidget(self)
            except Exception:
                self._canvas = _SoftwarePropellerViewportWidget(self)
        else:
            self._canvas = _SoftwarePropellerViewportWidget(self)
        layout.addWidget(self._canvas)

    def set_preview_result(self, result: PropellerPreviewResult | None) -> None:
        self._canvas.set_preview_result(result)  # type: ignore[attr-defined]

    def mesh_face_count(self) -> int:
        return self._canvas.mesh_face_count()  # type: ignore[attr-defined]

    def set_preview_options(self, show_mesh: bool, show_wireframe: bool) -> None:
        self._canvas.set_preview_options(show_mesh, show_wireframe)  # type: ignore[attr-defined]

    def reset_view(self) -> None:
        self._canvas.reset_view()  # type: ignore[attr-defined]

    def snap_to_named_view(self, view_name: str) -> None:
        self._canvas.snap_to_named_view(view_name)  # type: ignore[attr-defined]

    def apply_theme(self, colors: dict[str, str]) -> None:
        self._canvas.apply_theme(colors)  # type: ignore[attr-defined]


class AdvancedPropellerWorkspace(QWidget):
    status_message = pyqtSignal(str)

    def __init__(
        self,
        session: PropellerEnvironmentSession,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AdvancedPropellerWorkspace")
        self._session = session
        self._preview_service = PropellerPreviewService(self)
        self._preview_service.build_started.connect(self._on_build_started)
        self._preview_service.build_ready.connect(self._on_build_ready)
        self._preview_service.build_failed.connect(self._on_build_failed)
        self._stage_pages: dict[str, QWidget] = {}
        self._distribution_editors: dict[str, DistributionEditorWidget] = {}
        self._backend_status_label: QLabel | None = None
        self._model_summary_label: QLabel | None = None
        self._section_eta_spin: QDoubleSpinBox | None = None

        self.stage_tree = QTreeWidget(self)
        self.stage_tree.setObjectName("PropellerStageTree")
        self.stage_tree.setHeaderHidden(True)
        self.stage_tree.setAlternatingRowColors(True)
        self.stage_tree.itemSelectionChanged.connect(self._on_stage_selection_changed)

        self.inspector_stack = QStackedWidget(self)
        self.plot_tabs = QTabWidget(self)
        self.radial_plot = RadialDistributionPlot(self.plot_tabs)
        self.section_preview = SectionPreviewWidget(self.plot_tabs)
        self.plot_tabs.addTab(self.radial_plot, "Radial Plots")
        self.plot_tabs.addTab(self.section_preview, "Section")
        self.viewport = PropellerViewportWidget(self)
        self.diagnostic_list = QListWidget(self)
        self.diagnostic_list.setAlternatingRowColors(True)

        center_panel = QWidget(self)
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)
        center_layout.addWidget(self.inspector_stack, 1)
        center_layout.addWidget(self.plot_tabs, 1)

        middle_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        middle_splitter.addWidget(center_panel)
        middle_splitter.addWidget(self.viewport)
        middle_splitter.setStretchFactor(0, 1)
        middle_splitter.setStretchFactor(1, 1)
        middle_splitter.setSizes([540, 560])

        outer_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        outer_splitter.addWidget(self.stage_tree)
        outer_splitter.addWidget(middle_splitter)
        outer_splitter.setStretchFactor(0, 0)
        outer_splitter.setStretchFactor(1, 1)
        outer_splitter.setSizes([220, 1080])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(outer_splitter)

        self._build_stage_tree()
        self._build_pages()
        self._select_stage(self._session.active_stage)
        self.viewport.set_preview_options(
            self._session.feature_state.preview_settings.show_mesh,
            self._session.feature_state.preview_settings.show_wireframe,
        )
        self._sync_section_eta_constraints()
        if self._preview_service.using_rust_backend:
            self._request_build(force_all=True)
        else:
            self._show_backend_error(self._preview_service.backend_error)

    @property
    def session(self) -> PropellerEnvironmentSession:
        return self._session

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.radial_plot.apply_theme(colors)
        self.section_preview.apply_theme(colors)
        self.viewport.apply_theme(colors)
        self.setStyleSheet(
            f"""
            QWidget#AdvancedPropellerWorkspace {{
                background-color: {colors["workspace_bg"]};
                color: {colors["text_primary"]};
            }}
            QTreeWidget#PropellerStageTree,
            QStackedWidget,
            QTabWidget::pane,
            QListWidget,
            QTableWidget {{
                background-color: {colors["table_row_odd"]};
                alternate-background-color: {colors["table_row_even"]};
                color: {colors["text_primary"]};
                border: 1px solid {colors["border"]};
            }}
            QTreeWidget#PropellerStageTree::item,
            QListWidget::item,
            QTableWidget::item {{
                padding: 4px 6px;
            }}
            QTreeWidget#PropellerStageTree::item:selected,
            QListWidget::item:selected,
            QTableWidget::item:selected {{
                background-color: {colors["tab_active"]};
                color: {colors["text_primary"]};
            }}
            QTreeWidget#PropellerStageTree::item:hover,
            QListWidget::item:hover,
            QTableWidget::item:hover {{
                background-color: {colors["menu_hover"]};
            }}
            QTreeWidget#PropellerStageTree::item:disabled {{
                color: {colors["text_disabled"]};
            }}
            QHeaderView::section {{
                background-color: {colors["table_header_bg"]};
                color: {colors["text_muted"]};
                border: 1px solid {colors["border"]};
                padding: 4px 6px;
            }}
            QTabBar::tab {{
                background-color: {colors["tab_bg"]};
                color: {colors["text_primary"]};
                border: 1px solid {colors["border"]};
                padding: 6px 10px;
            }}
            QTabBar::tab:selected {{
                background-color: {colors["tab_active"]};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {colors["menu_hover"]};
            }}
            QPushButton,
            QComboBox,
            QDoubleSpinBox,
            QSpinBox,
            QCheckBox {{
                color: {colors["text_primary"]};
            }}
            QPushButton {{
                background-color: {colors["button_bg"]};
                border: 1px solid {colors["border"]};
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {colors["button_hover"]};
            }}
            QPushButton:pressed {{
                background-color: {colors["button_pressed"]};
            }}
            QPushButton:disabled,
            QComboBox:disabled,
            QDoubleSpinBox:disabled,
            QSpinBox:disabled,
            QCheckBox:disabled {{
                color: {colors["text_disabled"]};
            }}
            QComboBox,
            QDoubleSpinBox,
            QSpinBox {{
                background-color: {colors["input_bg"]};
                border: 1px solid {colors["border"]};
                padding: 4px 8px;
                selection-background-color: {colors["accent"]};
            }}
            QComboBox:hover,
            QDoubleSpinBox:hover,
            QSpinBox:hover {{
                background-color: {colors["input_focus"]};
            }}
            QComboBox:focus,
            QDoubleSpinBox:focus,
            QSpinBox:focus {{
                background-color: {colors["input_focus"]};
                border: 1px solid {colors["accent"]};
            }}
            QComboBox::drop-down {{
                border-left: 1px solid {colors["border"]};
                background-color: {colors["button_bg"]};
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors["library_bg"]};
                color: {colors["text_primary"]};
                border: 1px solid {colors["border"]};
                selection-background-color: {colors["tab_active"]};
            }}
            QFrame#InspectorSection {{
                border: 1px solid {colors["border"]};
                background-color: {colors["library_alt"]};
                border-radius: 4px;
            }}
            QSplitter::handle {{
                background-color: {colors["border"]};
                width: 1px;
            }}
            """
        )

    def apply_typography(self, profile: TypographyProfile) -> None:
        typography = TypographyManager(profile)
        typography.apply(self.stage_tree, TypographyRole.BODY)
        typography.apply(self.plot_tabs, TypographyRole.TAB_LABEL)
        typography.apply(self.diagnostic_list, TypographyRole.BODY)
        for editor in self._distribution_editors.values():
            typography.apply(editor.selector, TypographyRole.BODY)
            typography.apply(editor.table, TypographyRole.MONO_LOG)
            typography.apply(editor.add_button, TypographyRole.BODY)
            typography.apply(editor.remove_button, TypographyRole.BODY)
        for widget in self.findChildren(QLabel):
            role = TypographyRole.PANEL_HEADER if widget.objectName().endswith("Title") else TypographyRole.BODY
            typography.apply(widget, role)

    def handle_action(self, action_name: str) -> bool:
        if action_name in {"Rebuild Preview", "Rebuild Model", "Validate Propeller"}:
            self._request_build(force_all=True)
            return True
        if action_name == "Reset View":
            self.viewport.reset_view()
            self.status_message.emit("Reset propeller viewport.")
            return True
        if action_name == "Toggle Mesh":
            self._session.feature_state.preview_settings.show_mesh = not self._session.feature_state.preview_settings.show_mesh
            self.viewport.set_preview_options(
                self._session.feature_state.preview_settings.show_mesh,
                self._session.feature_state.preview_settings.show_wireframe,
            )
            return True
        if action_name == "Toggle Sections":
            self._session.feature_state.preview_settings.show_sections = not self._session.feature_state.preview_settings.show_sections
            self._session.feature_state.mark_dirty_from_stage("blade_preview")
            self._request_build(force_all=False)
            return True
        return False

    def _build_stage_tree(self) -> None:
        active_root = QTreeWidgetItem(["Active Stages"])
        for stage in ACTIVE_PROPELLER_STAGES:
            item = QTreeWidgetItem([STAGE_LABELS[stage]])
            item.setData(0, Qt.ItemDataRole.UserRole, stage)
            active_root.addChild(item)
        active_root.setExpanded(True)
        self.stage_tree.addTopLevelItem(active_root)

        deferred_root = QTreeWidgetItem(["Deferred"])
        for stage in DEFERRED_PROPELLER_STAGES:
            item = QTreeWidgetItem([STAGE_LABELS[stage]])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setDisabled(True)
            deferred_root.addChild(item)
        deferred_root.setExpanded(True)
        self.stage_tree.addTopLevelItem(deferred_root)

    def _build_pages(self) -> None:
        for stage in ACTIVE_PROPELLER_STAGES:
            page = getattr(self, f"_build_{stage}_page")()
            self._stage_pages[stage] = page
            self.inspector_stack.addWidget(page)

    def _select_stage(self, stage: str) -> None:
        matches = self.stage_tree.findItems(
            STAGE_LABELS[stage],
            Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
        )
        if matches:
            self.stage_tree.setCurrentItem(matches[0])
        self._session.active_stage = stage

    def _on_stage_selection_changed(self) -> None:
        item = self.stage_tree.currentItem()
        if item is None:
            return
        stage = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(stage, str):
            return
        self._session.active_stage = stage
        self.inspector_stack.setCurrentWidget(self._stage_pages[stage])
        self._refresh_plot_panels()

    def _build_center_surface_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Center Surface Parameters", page)
        title.setObjectName("CenterSurfaceTitle")
        layout.addWidget(title)

        form_container = QFrame(page)
        form_container.setObjectName("InspectorSection")
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(12, 12, 12, 12)
        state = self._session.feature_state.global_parameters

        radius_spin = self._make_double_spin(500.0, 12000.0, state.radius, 1.0)
        pitch_spin = self._make_double_spin(-12.0, 12.0, state.pitch_reference_deg, 0.1)
        radius_spin.valueChanged.connect(lambda value: self._update_global("radius", value, "center_surface"))
        pitch_spin.valueChanged.connect(lambda value: self._update_global("pitch_reference_deg", value, "section_placement"))
        form_layout.addRow("Radius", radius_spin)
        form_layout.addRow("Pitch Ref. (deg)", pitch_spin)
        layout.addWidget(form_container)

        editor = DistributionEditorWidget(page)
        editor.bind_stage(self._session.feature_state, "center_surface")
        editor.distribution_selected.connect(lambda _key: self._refresh_plot_panels())
        editor.distribution_changed.connect(self._on_distribution_changed)
        self._distribution_editors["center_surface"] = editor
        layout.addWidget(editor, 1)
        return page

    def _build_profile_configurator_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Profile Configurator", page)
        title.setObjectName("ProfileConfiguratorTitle")
        layout.addWidget(title)

        form_container = QFrame(page)
        form_container.setObjectName("InspectorSection")
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(12, 12, 12, 12)
        profile = self._session.feature_state.profile_definition
        camber_combo = self._make_combo(("modified_naca", "parabolic", "elliptic"), profile.camber_family)
        thickness_combo = self._make_combo(("naca66_like", "ogive", "elliptic"), profile.thickness_family)
        te_spin = self._make_double_spin(0.001, 0.03, profile.trailing_edge_thickness, 0.001)
        le_spin = self._make_double_spin(-0.3, 0.3, profile.leading_edge_bias, 0.01)
        camber_combo.currentTextChanged.connect(
            lambda value: self._update_profile("camber_family", value, "profile_configurator")
        )
        thickness_combo.currentTextChanged.connect(
            lambda value: self._update_profile("thickness_family", value, "profile_configurator")
        )
        te_spin.valueChanged.connect(lambda value: self._update_profile("trailing_edge_thickness", value, "profile_configurator"))
        le_spin.valueChanged.connect(lambda value: self._update_profile("leading_edge_bias", value, "profile_configurator"))
        form_layout.addRow("Camber Family", camber_combo)
        form_layout.addRow("Thickness Family", thickness_combo)
        form_layout.addRow("TE Thickness", te_spin)
        form_layout.addRow("LE Bias", le_spin)
        layout.addWidget(form_container)

        editor = DistributionEditorWidget(page)
        editor.bind_stage(self._session.feature_state, "profile_configurator")
        editor.distribution_selected.connect(lambda _key: self._refresh_plot_panels())
        editor.distribution_changed.connect(self._on_distribution_changed)
        self._distribution_editors["profile_configurator"] = editor
        layout.addWidget(editor, 1)
        return page

    def _build_section_placement_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Section Placement", page)
        title.setObjectName("SectionPlacementTitle")
        layout.addWidget(title)

        form_container = QFrame(page)
        form_container.setObjectName("InspectorSection")
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(12, 12, 12, 12)
        preview = self._session.feature_state.preview_settings
        minimum_eta = self._session.feature_state.hub_parameters.hub_radius_ratio
        span_spin = self._make_int_spin(8, 40, preview.span_samples)
        chord_spin = self._make_int_spin(12, 64, preview.chord_samples)
        eta_spin = self._make_double_spin(minimum_eta, 1.0, preview.section_eta, 0.01)
        tessellation_rows = self._make_int_spin(12, 120, preview.tessellation_rows)
        tessellation_cols = self._make_int_spin(24, 180, preview.tessellation_cols)
        self._section_eta_spin = eta_spin
        span_spin.valueChanged.connect(lambda value: self._update_preview_setting("span_samples", value, "section_placement"))
        chord_spin.valueChanged.connect(lambda value: self._update_preview_setting("chord_samples", value, "section_placement"))
        eta_spin.valueChanged.connect(lambda value: self._update_preview_setting("section_eta", value, "section_placement"))
        tessellation_rows.valueChanged.connect(lambda value: self._update_preview_setting("tessellation_rows", value, "blade_preview"))
        tessellation_cols.valueChanged.connect(lambda value: self._update_preview_setting("tessellation_cols", value, "blade_preview"))
        form_layout.addRow("Span Samples", span_spin)
        form_layout.addRow("Chord Samples", chord_spin)
        form_layout.addRow("Section eta", eta_spin)
        form_layout.addRow("Tessellation Rows", tessellation_rows)
        form_layout.addRow("Tessellation Cols", tessellation_cols)
        layout.addWidget(form_container)
        layout.addStretch(1)
        return page

    def _build_tip_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Tip Surface", page)
        title.setObjectName("TipSurfaceTitle")
        layout.addWidget(title)

        form_container = QFrame(page)
        form_container.setObjectName("InspectorSection")
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(12, 12, 12, 12)
        tip = self._session.feature_state.tip_parameters

        controls = (
            ("Closure Bias", "closure_bias", self._make_double_spin(0.05, 0.95, tip.closure_bias, 0.01)),
            ("Roundness", "roundness", self._make_double_spin(0.05, 1.00, tip.roundness, 0.01)),
            ("Cap Depth Ratio", "cap_depth_ratio", self._make_double_spin(0.01, 0.25, tip.cap_depth_ratio, 0.005)),
            ("Cap Length Ratio", "cap_length_ratio", self._make_double_spin(0.01, 0.35, tip.cap_length_ratio, 0.005)),
            ("Thickness Fade", "tip_thickness_fade", self._make_double_spin(0.10, 1.00, tip.tip_thickness_fade, 0.01)),
            ("Camber Fade", "tip_camber_fade", self._make_double_spin(0.10, 1.00, tip.tip_camber_fade, 0.01)),
            ("Rake Fade", "tip_rake_fade", self._make_double_spin(0.00, 1.00, tip.tip_rake_fade, 0.01)),
        )
        for label, field_name, spin in controls:
            spin.valueChanged.connect(
                lambda value, field_name=field_name: self._update_tip(field_name, value, "tip")
            )
            form_layout.addRow(label, spin)

        layout.addWidget(form_container)
        layout.addStretch(1)
        return page

    def _build_hub_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Hub Blend", page)
        title.setObjectName("HubBlendTitle")
        layout.addWidget(title)

        form_container = QFrame(page)
        form_container.setObjectName("InspectorSection")
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(12, 12, 12, 12)
        hub = self._session.feature_state.hub_parameters

        controls = (
            ("Hub Radius Ratio", "hub_radius_ratio", self._make_double_spin(0.10, 0.45, hub.hub_radius_ratio, 0.01)),
            ("Hub Length Ratio", "hub_length_ratio", self._make_double_spin(0.08, 0.70, hub.hub_length_ratio, 0.01)),
            ("Fore Profile Split", "fore_profile_split", self._make_double_spin(0.05, 0.90, hub.fore_profile_split, 0.01)),
            ("Aft Profile Split", "aft_profile_split", self._make_double_spin(0.05, 0.95, hub.aft_profile_split, 0.01)),
            ("Root Cutback Start", "root_cutback_start", self._make_double_spin(0.01, 0.60, hub.root_cutback_start, 0.01)),
            ("Root LE Blend", "root_le_blend_ratio", self._make_double_spin(0.0, 0.20, hub.root_le_blend_ratio, 0.005)),
            ("Root TE Blend", "root_te_blend_ratio", self._make_double_spin(0.0, 0.20, hub.root_te_blend_ratio, 0.005)),
        )
        for label, field_name, spin in controls:
            spin.valueChanged.connect(
                lambda value, field_name=field_name: self._update_hub(field_name, value, "hub")
            )
            form_layout.addRow(label, spin)

        layout.addWidget(form_container)
        layout.addStretch(1)
        return page

    def _build_pattern_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Pattern", page)
        title.setObjectName("PatternTitle")
        layout.addWidget(title)

        form_container = QFrame(page)
        form_container.setObjectName("InspectorSection")
        form_layout = QFormLayout(form_container)
        form_layout.setContentsMargins(12, 12, 12, 12)
        pattern = self._session.feature_state.pattern_parameters

        blade_spin = self._make_int_spin(2, 8, pattern.num_blades)
        start_angle_spin = self._make_double_spin(-180.0, 180.0, pattern.start_angle_deg, 1.0)
        handedness_combo = self._make_combo(("right", "left"), pattern.handedness)
        axis_combo = self._make_combo(("z",), pattern.axis_convention)

        blade_spin.valueChanged.connect(lambda value: self._update_pattern("num_blades", value, "pattern"))
        start_angle_spin.valueChanged.connect(
            lambda value: self._update_pattern("start_angle_deg", value, "pattern")
        )
        handedness_combo.currentTextChanged.connect(
            lambda value: self._update_pattern("handedness", value, "pattern")
        )
        axis_combo.currentTextChanged.connect(
            lambda value: self._update_pattern("axis_convention", value, "pattern")
        )

        form_layout.addRow("Blade Count", blade_spin)
        form_layout.addRow("Start Angle", start_angle_spin)
        form_layout.addRow("Handedness", handedness_combo)
        form_layout.addRow("Axis", axis_combo)
        layout.addWidget(form_container)
        layout.addStretch(1)
        return page

    def _build_blade_preview_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Blade Preview", page)
        title.setObjectName("BladePreviewTitle")
        layout.addWidget(title)

        form_container = QFrame(page)
        form_container.setObjectName("InspectorSection")
        form_layout = QGridLayout(form_container)
        form_layout.setContentsMargins(12, 12, 12, 12)
        preview = self._session.feature_state.preview_settings
        mesh_check = QCheckBox("Show mesh", form_container)
        wire_check = QCheckBox("Show wireframe", form_container)
        section_check = QCheckBox("Show sections", form_container)
        backend_label = QLabel(self._backend_status_text(), form_container)
        backend_label.setObjectName("PropellerBackendLabel")
        model_summary = QLabel("Awaiting first Rust build.", form_container)
        model_summary.setWordWrap(True)
        self._backend_status_label = backend_label
        self._model_summary_label = model_summary
        mesh_check.setChecked(preview.show_mesh)
        wire_check.setChecked(preview.show_wireframe)
        section_check.setChecked(preview.show_sections)
        mesh_check.toggled.connect(lambda value: self._toggle_preview_option("show_mesh", value))
        wire_check.toggled.connect(lambda value: self._toggle_preview_option("show_wireframe", value))
        section_check.toggled.connect(lambda value: self._toggle_preview_option("show_sections", value, rebuild=True))
        form_layout.addWidget(mesh_check, 0, 0)
        form_layout.addWidget(wire_check, 0, 1)
        form_layout.addWidget(section_check, 1, 0)
        form_layout.addWidget(backend_label, 2, 0, 1, 2)
        form_layout.addWidget(model_summary, 3, 0, 1, 2)
        layout.addWidget(form_container)
        layout.addStretch(1)
        return page

    def _build_diagnostics_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Diagnostics", page)
        title.setObjectName("DiagnosticsTitle")
        layout.addWidget(title)
        layout.addWidget(self.diagnostic_list, 1)
        return page

    def _make_double_spin(self, minimum: float, maximum: float, value: float, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(minimum, maximum)
        spin.setDecimals(4)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    def _make_int_spin(self, minimum: int, maximum: int, value: int) -> QSpinBox:
        spin = QSpinBox(self)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def _make_combo(self, options: tuple[str, ...], value: str) -> QComboBox:
        combo = QComboBox(self)
        combo.addItems(list(options))
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _update_global(self, field_name: str, value, stage: str) -> None:
        setattr(self._session.feature_state.global_parameters, field_name, value)
        self._session.feature_state.mark_dirty_from_stage(stage)
        self._request_build(force_all=False)

    def _update_profile(self, field_name: str, value, stage: str) -> None:
        setattr(self._session.feature_state.profile_definition, field_name, value)
        self._session.feature_state.mark_dirty_from_stage(stage)
        self._request_build(force_all=False)

    def _update_preview_setting(self, field_name: str, value, stage: str) -> None:
        setattr(self._session.feature_state.preview_settings, field_name, value)
        self.viewport.set_preview_options(
            self._session.feature_state.preview_settings.show_mesh,
            self._session.feature_state.preview_settings.show_wireframe,
        )
        self._session.feature_state.mark_dirty_from_stage(stage)
        self._request_build(force_all=False)

    def _update_tip(self, field_name: str, value, stage: str) -> None:
        setattr(self._session.feature_state.tip_parameters, field_name, value)
        self._session.feature_state.mark_dirty_from_stage(stage)
        self._request_build(force_all=False)

    def _update_hub(self, field_name: str, value, stage: str) -> None:
        setattr(self._session.feature_state.hub_parameters, field_name, value)
        self._sync_section_eta_constraints()
        self._session.feature_state.mark_dirty_from_stage(stage)
        self._request_build(force_all=False)

    def _update_pattern(self, field_name: str, value, stage: str) -> None:
        setattr(self._session.feature_state.pattern_parameters, field_name, value)
        self._session.feature_state.mark_dirty_from_stage(stage)
        self._request_build(force_all=False)

    def _toggle_preview_option(self, field_name: str, value: bool, rebuild: bool = False) -> None:
        setattr(self._session.feature_state.preview_settings, field_name, value)
        self.viewport.set_preview_options(
            self._session.feature_state.preview_settings.show_mesh,
            self._session.feature_state.preview_settings.show_wireframe,
        )
        if rebuild:
            self._session.feature_state.mark_dirty_from_stage("blade_preview")
            self._request_build(force_all=False)

    def _on_distribution_changed(self, _distribution_key: str, stage: str) -> None:
        self._session.feature_state.mark_dirty_from_stage(stage)
        self._refresh_plot_panels()
        self._request_build(force_all=False)

    def _request_build(self, force_all: bool) -> None:
        if not self._preview_service.using_rust_backend:
            self._show_backend_error(self._preview_service.backend_error)
            return
        if force_all:
            self._session.feature_state.dirty_stages = list(ACTIVE_PROPELLER_STAGES)
        self._preview_service.request_build(
            self._session.feature_state,
            list(self._session.feature_state.dirty_stages),
        )

    def _on_build_started(self, dirty_stages: list[str]) -> None:
        self.status_message.emit(
            "Rebuilding propeller model: " + ", ".join(STAGE_LABELS[stage] for stage in dirty_stages)
        )

    def _on_build_ready(self, result: PropellerPreviewResult) -> None:
        self._session.last_result = result
        self._session.feature_state.mark_clean(result.built_stages)
        self.section_preview.set_preview_result(result)
        self.viewport.set_preview_result(result)
        self.viewport.set_preview_options(
            self._session.feature_state.preview_settings.show_mesh,
            self._session.feature_state.preview_settings.show_wireframe,
        )
        self._refresh_plot_panels()
        self._refresh_diagnostics()
        self._update_model_summary(result)
        self.status_message.emit(
            f"Propeller model ready ({len(result.mesh.vertices)} verts, {len(result.mesh.faces)} faces)."
        )

    def _on_build_failed(self, message: str) -> None:
        self._show_backend_error(message)
        self.status_message.emit(f"Propeller build failed: {message}")

    def _refresh_plot_panels(self) -> None:
        stage = self._session.active_stage
        if stage in self._distribution_editors:
            editor = self._distribution_editors[stage]
            distribution_keys = editor._distribution_keys
            highlight_key = editor.current_distribution_key()
            editor.refresh()
        else:
            distribution_keys = list(self._session.feature_state.distributions.keys())
            highlight_key = None
        self.radial_plot.set_plot_data(
            self._session.feature_state,
            self._session.last_result,
            distribution_keys,
            highlight_key,
        )

    def _refresh_diagnostics(self) -> None:
        self.diagnostic_list.clear()
        if self._preview_service.backend_error is not None:
            self.diagnostic_list.addItem(QListWidgetItem(f"[ERROR] {self._preview_service.backend_error}"))
        if self._session.last_result is None:
            return
        metadata = self._session.last_result.model_metadata
        self.diagnostic_list.addItem(
            QListWidgetItem(
                f"[INFO] Source={metadata.source}, valid={metadata.valid}, watertight={metadata.watertight}, components={metadata.component_count}"
            )
        )
        for diagnostic in self._session.last_result.diagnostics:
            self.diagnostic_list.addItem(QListWidgetItem(f"[{diagnostic.severity.upper()}] {diagnostic.message}"))

    def _sync_section_eta_constraints(self) -> None:
        minimum_eta = self._session.feature_state.hub_parameters.hub_radius_ratio
        if self._session.feature_state.preview_settings.section_eta < minimum_eta:
            self._session.feature_state.preview_settings.section_eta = minimum_eta
        if self._section_eta_spin is not None:
            self._section_eta_spin.blockSignals(True)
            self._section_eta_spin.setMinimum(minimum_eta)
            self._section_eta_spin.setValue(self._session.feature_state.preview_settings.section_eta)
            self._section_eta_spin.blockSignals(False)

    def _backend_status_text(self) -> str:
        if self._preview_service.backend_error is not None:
            return f"Rust backend unavailable: {self._preview_service.backend_error}"
        return "Rust backend: authoritative Truck build active"

    def _show_backend_error(self, message: str | None) -> None:
        if self._backend_status_label is not None:
            self._backend_status_label.setText(self._backend_status_text())
        if self._model_summary_label is not None:
            self._model_summary_label.setText(message or "Rust backend unavailable.")
        self._refresh_diagnostics()

    def _update_model_summary(self, result: PropellerPreviewResult) -> None:
        if self._backend_status_label is not None:
            self._backend_status_label.setText(self._backend_status_text())
        if self._model_summary_label is None:
            return
        metadata = result.model_metadata
        self._model_summary_label.setText(
            f"Source: {metadata.source}. Blades: {metadata.blade_count}. "
            f"Components: {metadata.component_count}. Watertight: {metadata.watertight}."
        )
