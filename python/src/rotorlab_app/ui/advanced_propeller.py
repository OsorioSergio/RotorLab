from __future__ import annotations

import math
import os
from array import array
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QMatrix4x4, QPainter, QPainterPath, QPen, QPolygonF, QVector3D, QVector4D
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


def _series_color(index: int) -> QColor:
    palette = (
        QColor("#4d80c4"),
        QColor("#5cc88a"),
        QColor("#efad4d"),
        QColor("#e7726a"),
        QColor("#8a76d9"),
        QColor("#35b7c7"),
        QColor("#db72a5"),
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
            "background": QColor("#ffffff"),
            "border": QColor("#b4c6dd"),
            "muted": QColor("#5d7695"),
            "highlight": QColor("#3f73bb"),
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
            "background": QColor("#ffffff"),
            "border": QColor("#b4c6dd"),
            "curve": QColor("#3f73bb"),
            "curve_alt": QColor("#d97f2f"),
            "muted": QColor("#5d7695"),
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
        self._background = QColor("#161f2d")
        self._border = QColor("#2a3a50")
        self._mesh_fill = QColor("#4d80c4")
        self._mesh_wire = QColor("#dbe8fa")
        self._section_color = QColor("#efad4d")
        self._text = QColor("#e8eef7")
        self._muted = QColor("#9fb0c8")
        self._show_mesh = True
        self._show_wireframe = True
        self._yaw = -34.0
        self._pitch = 18.0
        self._distance = 4.0
        self._center = (0.0, 0.0, 0.0)
        self._last_pos = QPoint()
        self._drag_mode: str | None = None
        self._bounds_extent = 2.0
        self._vertex_normals: list[tuple[float, float, float]] = []
        self._interactive_preview = False
        self._static_face_budget = 24000
        self._interactive_face_budget = 6000
        self._interaction_timer = QTimer(self)
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.setInterval(140)
        self._interaction_timer.timeout.connect(self._settle_interaction)

    def set_preview_result(self, result: PropellerPreviewResult | None) -> None:
        self._preview_result = result
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
        self._yaw = -34.0
        self._pitch = 18.0
        self._fit_to_mesh()
        self._settle_interaction()
        self.update()

    def apply_theme(self, colors: dict[str, str]) -> None:
        self._background = QColor(colors["workspace_bg"])
        self._border = QColor(colors["border"])
        self._mesh_fill = QColor(colors["accent"])
        self._mesh_wire = QColor(colors["text_primary"])
        self._section_color = QColor(colors["port_output"])
        self._text = QColor(colors["text_primary"])
        self._muted = QColor(colors["text_muted"])
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, not self._interactive_preview)
        painter.fillRect(self.rect(), self._background)
        painter.setPen(QPen(self._border, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self._preview_result is None or not self._preview_result.mesh.vertices or not self._preview_result.mesh.faces:
            painter.setPen(self._muted)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "3D preview waiting for geometry.")
            return

        projection = self._build_projection()
        eye, forward, right, up = projection
        vertices = self._preview_result.mesh.vertices
        faces = self._preview_result.mesh.faces
        projected_vertices = [self._project_point(point, eye, forward, right, up) for point in vertices]
        target_faces = self._interactive_face_budget if self._interactive_preview else self._static_face_budget
        face_step = max(1, math.ceil(len(faces) / max(1, target_faces)))
        show_wireframe = self._show_wireframe and not self._interactive_preview
        face_polygons: list[tuple[float, QPolygonF, QColor]] = []
        light_direction = _normalize((0.35, -0.28, 0.89))
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
            brightness = 0.34 + max(0.0, _dot(normal, light_direction)) * 0.66
            fill = QColor(self._mesh_fill)
            fill.setAlpha(216 if show_wireframe else 232)
            fill = fill.lighter(int(100 * brightness + 18))
            face_polygons.append((sum(point.depth for point in points) / len(points), polygon, fill))

        face_polygons.sort(key=lambda item: item[0], reverse=True)
        for _depth, polygon, fill in face_polygons:
            painter.setBrush(fill if self._show_mesh else Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self._mesh_wire if show_wireframe else fill, 1 if show_wireframe else 0))
            painter.drawPolygon(polygon)

        if self._preview_result.mesh.section_polylines and not self._interactive_preview:
            painter.setPen(QPen(self._section_color, 1.2, Qt.PenStyle.DashLine))
            for polyline in self._preview_result.mesh.section_polylines:
                path = QPainterPath()
                started = False
                for point in polyline:
                    projected = self._project_point(point, eye, forward, right, up)
                    if projected is None:
                        continue
                    if not started:
                        path.moveTo(projected.x, projected.y)
                        started = True
                    else:
                        path.lineTo(projected.x, projected.y)
                if started:
                    painter.drawPath(path)

        painter.setPen(self._text)
        painter.drawText(16, 22, "Blade Preview")
        painter.setPen(self._muted)
        painter.drawText(16, 40, "Left drag: orbit | Right drag: pan | Wheel: zoom")
        if face_step > 1:
            painter.drawText(
                16,
                58,
                f"Adaptive preview: {len(face_polygons):,} of {len(faces):,} faces",
            )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._last_pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
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
            self._yaw += delta.x() * 0.6
            self._pitch = max(-80.0, min(80.0, self._pitch + delta.y() * 0.4))
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

    def _build_projection(self):
        yaw_rad = math.radians(self._yaw)
        pitch_rad = math.radians(self._pitch)
        eye = (
            self._center[0] + self._distance * math.cos(pitch_rad) * math.cos(yaw_rad),
            self._center[1] + self._distance * math.cos(pitch_rad) * math.sin(yaw_rad),
            self._center[2] + self._distance * math.sin(pitch_rad),
        )
        forward = _normalize(
            (
                self._center[0] - eye[0],
                self._center[1] - eye[1],
                self._center[2] - eye[2],
            )
        )
        world_up = (0.0, 0.0, 1.0)
        if abs(_dot(forward, world_up)) > 0.98:
            world_up = (0.0, 1.0, 0.0)
        right = _normalize(_cross(forward, world_up))
        up = _normalize(_cross(right, forward))
        return eye, forward, right, up

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
            self._background = QColor("#161f2d")
            self._border = QColor("#2a3a50")
            self._mesh_fill = QColor("#4d80c4")
            self._mesh_wire = QColor("#dbe8fa")
            self._section_color = QColor("#efad4d")
            self._text = QColor("#e8eef7")
            self._muted = QColor("#9fb0c8")
            self._show_mesh = True
            self._show_wireframe = True
            self._yaw = -34.0
            self._pitch = 18.0
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

            self._vertex_normals: list[tuple[float, float, float]] = []
            self._mesh_vertex_blob = b""
            self._mesh_triangle_blob = b""
            self._mesh_interactive_triangle_blob = b""
            self._mesh_wire_blob = b""
            self._mesh_interactive_wire_blob = b""
            self._section_vertex_blob = b""
            self._mesh_triangle_count = 0
            self._mesh_interactive_triangle_count = 0
            self._mesh_wire_count = 0
            self._mesh_interactive_wire_count = 0
            self._section_ranges: list[tuple[int, int]] = []

            self._mesh_program: QOpenGLShaderProgram | None = None
            self._line_program: QOpenGLShaderProgram | None = None
            self._mesh_vertex_buffer: QOpenGLBuffer | None = None
            self._mesh_index_buffer: QOpenGLBuffer | None = None
            self._mesh_interactive_index_buffer: QOpenGLBuffer | None = None
            self._mesh_wire_index_buffer: QOpenGLBuffer | None = None
            self._mesh_interactive_wire_index_buffer: QOpenGLBuffer | None = None
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
            self._yaw = -34.0
            self._pitch = 18.0
            self._fit_to_mesh()
            self._settle_interaction()
            self.update()

        def apply_theme(self, colors: dict[str, str]) -> None:
            self._background = QColor(colors["workspace_bg"])
            self._border = QColor(colors["border"])
            self._mesh_fill = QColor(colors["accent"])
            self._mesh_wire = QColor(colors["text_primary"])
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
            self._gl.glEnable(GL_BLEND)
            self._gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            self._create_programs()
            self._create_buffers()
            self._gl_ready = True
            self._upload_buffers()

        def paintGL(self) -> None:  # type: ignore[override]
            if self._gl is None:
                return
            gl = self._gl
            gl.glClearColor(
                self._background.redF(),
                self._background.greenF(),
                self._background.blueF(),
                1.0,
            )
            gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            if self._gpu_dirty:
                self._upload_buffers()

            if self._preview_result is not None and self._mesh_triangle_count:
                mvp_matrix = self._build_mvp_matrix()
                self._draw_mesh(gl, mvp_matrix)
                self._draw_overlays(gl, mvp_matrix)

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, not self._interactive_preview)
            painter.setPen(QPen(self._border, 1))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            if self._preview_result is None or not self._mesh_triangle_count:
                painter.setPen(self._muted)
                painter.drawText(
                    self.rect(),
                    Qt.AlignmentFlag.AlignCenter,
                    "3D preview waiting for geometry.",
                )
                return
            painter.setPen(self._text)
            painter.drawText(16, 22, "Blade Preview")
            painter.setPen(self._muted)
            painter.drawText(16, 40, "OpenGL: orbit, pan, zoom")
            if self._interactive_preview and self._mesh_interactive_triangle_count:
                painter.drawText(
                    16,
                    58,
                    f"Adaptive preview: {self._mesh_interactive_triangle_count // 3:,} of {self._mesh_triangle_count // 3:,} faces",
                )

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            self._last_pos = event.position().toPoint()
            if event.button() == Qt.MouseButton.LeftButton:
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
                self._yaw += delta.x() * 0.6
                self._pitch = max(-80.0, min(80.0, self._pitch + delta.y() * 0.4))
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
                    float brightness = 0.34 + diffuse * 0.66;
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
                void main() {
                    gl_Position = u_mvp_matrix * vec4(a_position, 1.0);
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
            self._mesh_index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
            self._mesh_index_buffer.create()
            self._mesh_interactive_index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
            self._mesh_interactive_index_buffer.create()
            self._mesh_wire_index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
            self._mesh_wire_index_buffer.create()
            self._mesh_interactive_wire_index_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
            self._mesh_interactive_wire_index_buffer.create()
            self._section_vertex_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self._section_vertex_buffer.create()

        def _prepare_geometry_payloads(self) -> None:
            self._vertex_normals = []
            self._mesh_vertex_blob = b""
            self._mesh_triangle_blob = b""
            self._mesh_interactive_triangle_blob = b""
            self._mesh_wire_blob = b""
            self._mesh_interactive_wire_blob = b""
            self._section_vertex_blob = b""
            self._mesh_triangle_count = 0
            self._mesh_interactive_triangle_count = 0
            self._mesh_wire_count = 0
            self._mesh_interactive_wire_count = 0
            self._section_ranges = []

            if self._preview_result is None:
                self._gpu_dirty = True
                return

            vertices = self._preview_result.mesh.vertices
            faces = self._preview_result.mesh.faces
            if not vertices or not faces:
                self._gpu_dirty = True
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

            mesh_vertices = array("f")
            for vertex, normal in zip(vertices, self._vertex_normals):
                mesh_vertices.extend(
                    [
                        float(vertex[0]),
                        float(vertex[1]),
                        float(vertex[2]),
                        float(normal[0]),
                        float(normal[1]),
                        float(normal[2]),
                    ]
                )
            self._mesh_vertex_blob = mesh_vertices.tobytes()

            face_step = max(1, math.ceil(len(faces) / self._interactive_face_budget))
            interactive_faces = faces[::face_step]

            triangle_indices = array("I")
            for a, b, c in faces:
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

            interactive_wire_indices = array("I")
            for a, b, c in interactive_faces:
                interactive_wire_indices.extend([a, b, b, c, c, a])
            self._mesh_interactive_wire_blob = interactive_wire_indices.tobytes()
            self._mesh_interactive_wire_count = len(interactive_wire_indices)

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
                self._mesh_vertex_buffer.bind()
                self._mesh_vertex_buffer.allocate(
                    self._mesh_vertex_blob, len(self._mesh_vertex_blob)
                )
                self._mesh_vertex_buffer.release()
            if self._mesh_index_buffer is not None:
                self._mesh_index_buffer.bind()
                self._mesh_index_buffer.allocate(
                    self._mesh_triangle_blob, len(self._mesh_triangle_blob)
                )
                self._mesh_index_buffer.release()
            if self._mesh_interactive_index_buffer is not None:
                self._mesh_interactive_index_buffer.bind()
                self._mesh_interactive_index_buffer.allocate(
                    self._mesh_interactive_triangle_blob,
                    len(self._mesh_interactive_triangle_blob),
                )
                self._mesh_interactive_index_buffer.release()
            if self._mesh_wire_index_buffer is not None:
                self._mesh_wire_index_buffer.bind()
                self._mesh_wire_index_buffer.allocate(
                    self._mesh_wire_blob, len(self._mesh_wire_blob)
                )
                self._mesh_wire_index_buffer.release()
            if self._mesh_interactive_wire_index_buffer is not None:
                self._mesh_interactive_wire_index_buffer.bind()
                self._mesh_interactive_wire_index_buffer.allocate(
                    self._mesh_interactive_wire_blob,
                    len(self._mesh_interactive_wire_blob),
                )
                self._mesh_interactive_wire_index_buffer.release()
            if self._section_vertex_buffer is not None:
                self._section_vertex_buffer.bind()
                self._section_vertex_buffer.allocate(
                    self._section_vertex_blob, len(self._section_vertex_blob)
                )
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
                        "u_light_direction", QVector3D(0.35, -0.28, 0.89)
                    )
                    fill = QColor(self._mesh_fill)
                    fill.setAlpha(232 if not self._show_wireframe else 216)
                    self._mesh_program.setUniformValue(
                        "u_base_color",
                        QVector4D(
                            fill.redF(),
                            fill.greenF(),
                            fill.blueF(),
                            fill.alphaF(),
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

            if (
                self._show_wireframe
                and not self._interactive_preview
                and self._line_program is not None
                and self._mesh_vertex_buffer is not None
            ):
                wire_count = (
                    self._mesh_interactive_wire_count
                    if self._interactive_preview
                    else self._mesh_wire_count
                )
                wire_buffer = (
                    self._mesh_interactive_wire_index_buffer
                    if self._interactive_preview
                    else self._mesh_wire_index_buffer
                )
                if wire_count and wire_buffer is not None:
                    self._line_program.bind()
                    self._line_program.setUniformValue("u_mvp_matrix", mvp_matrix)
                    self._line_program.setUniformValue(
                        "u_base_color",
                        QVector4D(
                            self._mesh_wire.redF(),
                            self._mesh_wire.greenF(),
                            self._mesh_wire.blueF(),
                            0.92,
                        ),
                    )
                    self._mesh_vertex_buffer.bind()
                    self._line_program.enableAttributeArray(0)
                    self._line_program.setAttributeBuffer(0, GL_FLOAT, 0, 3, 24)
                    wire_buffer.bind()
                    gl.glDrawElements(GL_LINES, wire_count, GL_UNSIGNED_INT, None)
                    wire_buffer.release()
                    self._mesh_vertex_buffer.release()
                    self._line_program.disableAttributeArray(0)
                    self._line_program.release()

        def _draw_overlays(self, gl, mvp_matrix: QMatrix4x4) -> None:
            if (
                self._interactive_preview
                or self._line_program is None
                or self._section_vertex_buffer is None
                or not self._section_ranges
            ):
                return
            self._line_program.bind()
            self._line_program.setUniformValue("u_mvp_matrix", mvp_matrix)
            self._line_program.setUniformValue(
                "u_base_color",
                QVector4D(
                    self._section_color.redF(),
                    self._section_color.greenF(),
                    self._section_color.blueF(),
                    0.88,
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

        def _build_projection(self):
            yaw_rad = math.radians(self._yaw)
            pitch_rad = math.radians(self._pitch)
            eye = (
                self._center[0] + self._distance * math.cos(pitch_rad) * math.cos(yaw_rad),
                self._center[1] + self._distance * math.cos(pitch_rad) * math.sin(yaw_rad),
                self._center[2] + self._distance * math.sin(pitch_rad),
            )
            forward = _normalize(
                (
                    self._center[0] - eye[0],
                    self._center[1] - eye[1],
                    self._center[2] - eye[2],
                )
            )
            world_up = (0.0, 0.0, 1.0)
            if abs(_dot(forward, world_up)) > 0.98:
                world_up = (0.0, 1.0, 0.0)
            right = _normalize(_cross(forward, world_up))
            up = _normalize(_cross(right, forward))
            return eye, forward, right, up

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
        self.stage_tree.itemSelectionChanged.connect(self._on_stage_selection_changed)

        self.inspector_stack = QStackedWidget(self)
        self.plot_tabs = QTabWidget(self)
        self.radial_plot = RadialDistributionPlot(self.plot_tabs)
        self.section_preview = SectionPreviewWidget(self.plot_tabs)
        self.plot_tabs.addTab(self.radial_plot, "Radial Plots")
        self.plot_tabs.addTab(self.section_preview, "Section")
        self.viewport = PropellerViewportWidget(self)
        self.diagnostic_list = QListWidget(self)

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
                background-color: {colors["library_bg"]};
                color: {colors["text_primary"]};
                border: 1px solid {colors["border"]};
            }}
            QTreeWidget#PropellerStageTree::item:selected,
            QListWidget::item:selected,
            QTableWidget::item:selected {{
                background-color: {colors["tab_active"]};
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
            QPushButton,
            QComboBox,
            QDoubleSpinBox,
            QSpinBox,
            QCheckBox {{
                color: {colors["text_primary"]};
            }}
            QPushButton {{
                background-color: {colors["tab_bg"]};
                border: 1px solid {colors["border"]};
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {colors["menu_hover"]};
            }}
            QFrame#InspectorSection {{
                border: 1px solid {colors["border"]};
                background-color: {colors["library_alt"]};
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
