from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QMimeData, QPointF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rotorlab_app.ui.typography import TypographyManager, TypographyProfile, TypographyRole


@dataclass(frozen=True)
class ModuleTemplate:
    category: str
    name: str


def _module_initials(module_name: str) -> str:
    initials = "".join(part[:1] for part in module_name.split() if part)[:2].upper()
    return initials or "M"


def _build_module_placeholder_icon(
    module_name: str,
    base_font: QFont,
    bg_color: QColor,
    text_color: QColor,
    size: int = 16,
) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(bg_color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, 3, 3)

    painter.setPen(text_color)
    font = QFont(base_font)
    font.setPointSize(7)
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, _module_initials(module_name))
    painter.end()
    return QIcon(pixmap)


class ModuleLibraryTree(QTreeWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setIndentation(16)
        self.setUniformRowHeights(True)
        self.setAnimated(True)
        self.setAlternatingRowColors(True)
        self.setDragEnabled(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        self._header_font = QFont(self.font())
        self._item_font = QFont(self.font())
        self._icon_bg = QColor("#4d80c4")
        self._icon_text = QColor("#f4f8ff")
        self._category_items: list[QTreeWidgetItem] = []
        self._module_items: list[QTreeWidgetItem] = []
        self._templates: list[ModuleTemplate] = [
            ModuleTemplate("Geometry", "Blade Profile Generator"),
            ModuleTemplate("Geometry", "Propeller Parametric Builder"),
            ModuleTemplate("Simulation", "BEMT Solver Setup"),
            ModuleTemplate("Simulation", "CFD Export Setup"),
            ModuleTemplate("Filter", "Mesh Quality Filter"),
            ModuleTemplate("Analysis", "Performance Curve Analysis"),
            ModuleTemplate("Results", "Acoustic Plot"),
        ]

        self.itemClicked.connect(self._on_item_clicked)
        self._populate()

    def _populate(self) -> None:
        category_lookup: dict[str, QTreeWidgetItem] = {}
        for template in self._templates:
            if template.category not in category_lookup:
                category_item = QTreeWidgetItem([template.category.upper()])
                category_item.setData(0, Qt.ItemDataRole.UserRole, "")
                category_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                category_item.setExpanded(True)
                category_item.setFont(0, self._header_font)
                self.addTopLevelItem(category_item)
                category_lookup[template.category] = category_item
                self._category_items.append(category_item)

            module_item = QTreeWidgetItem([template.name])
            module_item.setData(0, Qt.ItemDataRole.UserRole, template.name)
            module_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            module_item.setFont(0, self._item_font)
            module_item.setIcon(0, self._build_module_icon(template.name))
            category_lookup[template.category].addChild(module_item)
            self._module_items.append(module_item)

        self.expandAll()

    def _build_module_icon(self, module_name: str) -> QIcon:
        return _build_module_placeholder_icon(
            module_name=module_name,
            base_font=self._item_font,
            bg_color=self._icon_bg,
            text_color=self._icon_text,
            size=16,
        )

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.parent() is None:
            item.setExpanded(not item.isExpanded())
            self.clearSelection()

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None or item.parent() is None:
            return

        module_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not module_name:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(str(module_name))
        drag.setMimeData(mime_data)
        drag.setPixmap(item.icon(0).pixmap(16, 16))
        drag.exec(supported_actions)

    def apply_typography(self, profile: TypographyProfile) -> None:
        typography = TypographyManager(profile)
        self._header_font = typography.font(TypographyRole.GROUP_CAPTION)
        self._item_font = typography.font(TypographyRole.BODY)
        self.setFont(self._item_font)

        for category_item in self._category_items:
            category_item.setFont(0, self._header_font)
        for module_item in self._module_items:
            module_item.setFont(0, self._item_font)
            module_item.setIcon(0, self._build_module_icon(module_item.text(0)))

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.setStyleSheet(
            f"""
            QTreeWidget {{
                background-color: {colors["library_bg"]};
                color: {colors["library_text"]};
                border: 1px solid {colors["border"]};
            }}
            QTreeWidget::item {{
                min-height: 28px;
                padding: 2px 6px;
            }}
            QTreeWidget::item:alternate {{
                background-color: {colors["library_alt"]};
            }}
            QTreeWidget::item:selected {{
                background-color: {colors["tab_active"]};
                color: {colors["text_primary"]};
            }}
            """
        )

        self._icon_bg = QColor(colors["accent"])
        self._icon_text = QColor(colors["icon_text"])

        for category_item in self._category_items:
            category_item.setForeground(0, QColor(colors["text_muted"]))
            category_item.setBackground(0, QColor(colors["library_bg"]))

        for module_item in self._module_items:
            module_item.setIcon(0, self._build_module_icon(module_item.text(0)))

    @property
    def category_items(self) -> list[QTreeWidgetItem]:
        return self._category_items

    @property
    def module_items(self) -> list[QTreeWidgetItem]:
        return self._module_items

    @property
    def module_templates(self) -> list[ModuleTemplate]:
        return self._templates


class ModuleIconRailList(QListWidget):
    def __init__(self, module_templates: list[ModuleTemplate], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setMovement(QListWidget.Movement.Static)
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setIconSize(QSize(18, 18))
        self.setSpacing(2)
        self.setAlternatingRowColors(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._item_font = QFont(self.font())
        self._icon_bg = QColor("#4d80c4")
        self._icon_text = QColor("#f4f8ff")
        self._templates = module_templates
        self._populate()

    def _populate(self) -> None:
        self.clear()
        for template in self._templates:
            item = QListWidgetItem(" ")
            item.setData(Qt.ItemDataRole.UserRole, template.name)
            item.setToolTip(template.name)
            item.setIcon(self._build_module_icon(template.name))
            item.setSizeHint(QSize(28, 28))
            item.setFont(self._item_font)
            self.addItem(item)

    def _build_module_icon(self, module_name: str) -> QIcon:
        return _build_module_placeholder_icon(
            module_name=module_name,
            base_font=self._item_font,
            bg_color=self._icon_bg,
            text_color=self._icon_text,
            size=18,
        )

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None:
            return

        module_name = item.data(Qt.ItemDataRole.UserRole)
        if not module_name:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(str(module_name))
        drag.setMimeData(mime_data)
        drag.setPixmap(item.icon().pixmap(18, 18))
        drag.exec(supported_actions)

    def apply_typography(self, profile: TypographyProfile) -> None:
        typography = TypographyManager(profile)
        self._item_font = typography.font(TypographyRole.BODY)
        for index in range(self.count()):
            self.item(index).setFont(self._item_font)
            self.item(index).setIcon(
                self._build_module_icon(str(self.item(index).data(Qt.ItemDataRole.UserRole)))
            )

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.setStyleSheet(
            f"""
            QListWidget {{
                background-color: {colors["library_bg"]};
                border: 1px solid {colors["border"]};
                padding: 4px;
            }}
            QListWidget::item {{
                min-height: 26px;
                padding: 2px;
            }}
            QListWidget::item:selected {{
                background-color: {colors["tab_active"]};
            }}
            """
        )
        self._icon_bg = QColor(colors["accent"])
        self._icon_text = QColor(colors["icon_text"])
        for index in range(self.count()):
            item = self.item(index)
            item.setIcon(self._build_module_icon(str(item.data(Qt.ItemDataRole.UserRole))))


class ModuleSelectorPanel(QWidget):
    collapsed_width = 58
    icon_mode_threshold = 92

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ModuleSelectorPanel")
        self.setMinimumWidth(self.collapsed_width)

        self.title_label = QLabel("Module Selection", self)
        self.title_label.setObjectName("ModuleSelectorTitle")

        self.library = ModuleLibraryTree(self)
        self.icon_rail = ModuleIconRailList(self.library.module_templates, self)

        self.content_stack = QStackedWidget(self)
        self.content_stack.addWidget(self.library)
        self.content_stack.addWidget(self.icon_rail)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.title_label)
        layout.addWidget(self.content_stack, 1)

        self._icon_mode = False
        self._set_icon_mode(False)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._set_icon_mode(self.width() <= self.icon_mode_threshold)

    def _set_icon_mode(self, enabled: bool) -> None:
        if self._icon_mode == enabled:
            return
        self._icon_mode = enabled
        self.title_label.setVisible(not enabled)
        self.content_stack.setCurrentWidget(self.icon_rail if enabled else self.library)
        if enabled:
            self.library.clearSelection()
        else:
            self.icon_rail.clearSelection()

    def is_icon_mode(self) -> bool:
        return self._icon_mode

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.setStyleSheet(
            f"""
            QWidget#ModuleSelectorPanel {{
                background-color: {colors["library_bg"]};
                border-right: 1px solid {colors["border"]};
            }}
            QLabel#ModuleSelectorTitle {{
                color: {colors["text_primary"]};
                background-color: {colors["tab_row_bg"]};
                border-top: 1px solid {colors["border"]};
                border-bottom: 1px solid {colors["border"]};
                padding: 6px 10px;
            }}
            """
        )
        self.library.apply_theme(colors)
        self.icon_rail.apply_theme(colors)

    def apply_typography(self, profile: TypographyProfile) -> None:
        typography = TypographyManager(profile)
        typography.apply(self.title_label, TypographyRole.PANEL_HEADER)
        self.library.apply_typography(profile)
        self.icon_rail.apply_typography(profile)


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
        self.module_selector = ModuleSelectorPanel(self)
        self.library = self.module_selector.library

        self.scene = WorkflowCanvasScene(self)
        self.canvas = WorkflowCanvasView(self.scene, self)
        self.canvas.module_dropped.connect(self._on_module_dropped)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.module_selector)
        splitter.addWidget(self.canvas)
        splitter.setCollapsible(0, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 900])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self._splitter = splitter

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.module_selector.apply_theme(colors)
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
        self.module_selector.apply_typography(profile)
        self.scene.apply_typography(profile)

    def _on_module_dropped(self, module_name: str) -> None:
        self.status_message.emit(f"Added module to workflow: {module_name}")

