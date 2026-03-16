from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from rotorlab_app.ui.typography import TypographyManager, TypographyProfile, TypographyRole


@dataclass(frozen=True)
class ModuleTemplate:
    category: str
    name: str


class ModuleLibraryList(QListWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._header_font = QFont(self.font())
        self._item_font = QFont(self.font())
        self._populate()

    def _populate(self) -> None:
        templates = [
            ModuleTemplate("Geometry", "Blade Profile Generator"),
            ModuleTemplate("Geometry", "Propeller Parametric Builder"),
            ModuleTemplate("Simulation", "BEMT Solver Setup"),
            ModuleTemplate("Simulation", "CFD Export Setup"),
            ModuleTemplate("Filter", "Mesh Quality Filter"),
            ModuleTemplate("Analysis", "Performance Curve Analysis"),
            ModuleTemplate("Results", "Acoustic Plot"),
        ]
        current_category = None
        for template in templates:
            if template.category != current_category:
                header = QListWidgetItem(template.category.upper())
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setFont(self._header_font)
                self.addItem(header)
                current_category = template.category

            item = QListWidgetItem(f"  {template.name}")
            item.setData(Qt.ItemDataRole.UserRole, template.name)
            item.setFont(self._item_font)
            self.addItem(item)

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None:
            return
        module_name = item.data(Qt.ItemDataRole.UserRole)
        if not module_name:
            return
        drag = QDrag(self)
        mime_data = self.model().mimeData([self.currentIndex()])
        mime_data.setText(module_name)
        drag.setMimeData(mime_data)
        drag.exec(supported_actions)

    def apply_typography(self, profile: TypographyProfile) -> None:
        typography = TypographyManager(profile)
        self._header_font = typography.font(TypographyRole.GROUP_CAPTION)
        self._item_font = typography.font(TypographyRole.BODY)

        for index in range(self.count()):
            item = self.item(index)
            if item.flags() == Qt.ItemFlag.NoItemFlags:
                item.setFont(self._header_font)
            else:
                item.setFont(self._item_font)

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {colors["library_bg"]};
                color: {colors["library_text"]};
                border: 1px solid {colors["border"]};
            }}
            QListWidget::item {{
                min-height: 28px;
                padding: 2px 6px;
            }}
            QListWidget::item:alternate {{
                background-color: {colors["library_alt"]};
            }}
            QListWidget::item:selected {{
                background-color: {colors["tab_active"]};
                color: {colors["text_primary"]};
            }}
            """
        )

        for index in range(self.count()):
            item = self.item(index)
            if item.flags() == Qt.ItemFlag.NoItemFlags:
                item.setForeground(QColor(colors["text_muted"]))
                item.setBackground(QColor(colors["library_bg"]))


class WorkflowCanvasScene(QGraphicsScene):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSceneRect(0, 0, 1800, 1200)
        self._node_counter = 0
        self._node_fill = QColor("#f8fbff")
        self._node_border = QColor("#2e4f77")
        self._node_text = QColor("#5f6b7a")
        self._title_font = QFont()
        self._subtitle_font = QFont()

    def add_module_node(self, module_name: str, position: QPointF) -> None:
        self._node_counter += 1
        width = 220
        height = 72

        rect = QGraphicsRectItem(0, 0, width, height)
        rect.setPos(position)
        rect.setBrush(self._node_fill)
        rect.setPen(QPen(self._node_border, 1))
        self.addItem(rect)

        title = QGraphicsSimpleTextItem(module_name, rect)
        title.setPos(10, 10)
        title.setFont(self._title_font)
        subtitle = QGraphicsSimpleTextItem(f"Node {self._node_counter}", rect)
        subtitle.setPos(10, 38)
        subtitle.setFont(self._subtitle_font)
        subtitle.setBrush(self._node_text)

    def apply_theme(self, colors: dict[str, str]) -> None:
        self._node_fill = QColor(colors["node_bg"])
        self._node_border = QColor(colors["node_border"])
        self._node_text = QColor(colors["node_text_sub"])

    def apply_typography(self, profile: TypographyProfile) -> None:
        typography = TypographyManager(profile)
        self._title_font = typography.font(TypographyRole.BODY)
        self._subtitle_font = typography.font(TypographyRole.GROUP_CAPTION)
        for item in self.items():
            if isinstance(item, QGraphicsSimpleTextItem):
                if item.text().startswith("Node "):
                    item.setFont(self._subtitle_font)
                else:
                    item.setFont(self._title_font)


class WorkflowCanvasView(QGraphicsView):
    module_dropped = pyqtSignal(str)

    def __init__(self, scene: WorkflowCanvasScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setBackgroundBrush(QColor("#f3f6fb"))

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasText():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasText():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        module_name = event.mimeData().text()
        if not module_name:
            event.ignore()
            return

        scene_point = self.mapToScene(event.position().toPoint())
        scene: WorkflowCanvasScene = self.scene()  # type: ignore[assignment]
        scene.add_module_node(module_name, scene_point)
        self.module_dropped.emit(module_name)
        event.acceptProposedAction()

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.setBackgroundBrush(QColor(colors["canvas_bg"]))
        self.setStyleSheet(f"QGraphicsView {{ border: 1px solid {colors['border']}; }}")


class OrchestrateWorkspace(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = ModuleLibraryList(self)
        self.scene = WorkflowCanvasScene(self)
        self.canvas = WorkflowCanvasView(self.scene, self)
        self.canvas.module_dropped.connect(self._on_module_dropped)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.library)
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([290, 930])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self._splitter = splitter

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.library.apply_theme(colors)
        self.scene.apply_theme(colors)
        self.canvas.apply_theme(colors)
        self.setStyleSheet(
            f"""
            QSplitter::handle {{
                background-color: {colors["border"]};
                width: 1px;
            }}
            """
        )

    def apply_typography(self, profile: TypographyProfile) -> None:
        self.library.apply_typography(profile)
        self.scene.apply_typography(profile)

    def _on_module_dropped(self, module_name: str) -> None:
        self.status_message.emit(f"Added module to workflow: {module_name}")
