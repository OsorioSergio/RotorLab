from __future__ import annotations

from copy import deepcopy
import json
from dataclasses import dataclass

from PyQt6.QtCore import QMimeData, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
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

from rotorlab_app.models.propeller import ADVANCED_PROPELLER_MODULE_TYPE
from rotorlab_app.ui.typography import TypographyManager, TypographyProfile, TypographyRole


@dataclass(frozen=True)
class ModuleTemplate:
    template_id: str
    category: str
    name: str
    payload: dict[str, object] | None = None


@dataclass(frozen=True)
class ModuleDragPayload:
    name: str
    category: str
    template_id: str | None = None

    MIME_TYPE = "application/x-rotorlab-module"

    def encode(self, mime_data: QMimeData) -> None:
        mime_data.setText(self.name)
        raw = json.dumps(
            {
                "name": self.name,
                "category": self.category,
                "template_id": self.template_id,
            }
        ).encode("utf-8")
        mime_data.setData(self.MIME_TYPE, raw)

    @classmethod
    def decode(cls, mime_data: QMimeData) -> ModuleDragPayload | None:
        if mime_data.hasFormat(cls.MIME_TYPE):
            try:
                payload = json.loads(bytes(mime_data.data(cls.MIME_TYPE)).decode("utf-8"))
                name = str(payload.get("name", "")).strip()
                category = str(payload.get("category", "")).strip()
                template_id = payload.get("template_id")
                template_id_value = str(template_id).strip() if template_id is not None else None
                if name and category:
                    return cls(name=name, category=category, template_id=template_id_value)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        if mime_data.hasText():
            name = mime_data.text().strip()
            if name:
                return cls(name=name, category="Analysis", template_id=None)
        return None


DEFAULT_MODULE_TEMPLATES: tuple[ModuleTemplate, ...] = (
    ModuleTemplate("geometry.blade_profile_generator", "Geometry", "Blade Profile Generator"),
    ModuleTemplate(
        ADVANCED_PROPELLER_MODULE_TYPE,
        "Geometry",
        "Propeller Parametric Builder",
        payload={"environment": "advanced_propeller"},
    ),
    ModuleTemplate("simulation.bemt_solver_setup", "Simulation", "BEMT Solver Setup"),
    ModuleTemplate("simulation.cfd_export_setup", "Simulation", "CFD Export Setup"),
    ModuleTemplate("filter.mesh_quality_filter", "Filter", "Mesh Quality Filter"),
    ModuleTemplate("analysis.performance_curve_analysis", "Analysis", "Performance Curve Analysis"),
    ModuleTemplate("results.acoustic_plot", "Results", "Acoustic Plot"),
)


MODULE_CATEGORY_BY_NAME: dict[str, str] = {
    template.name: template.category for template in DEFAULT_MODULE_TEMPLATES
}
MODULE_TEMPLATE_BY_NAME: dict[str, ModuleTemplate] = {
    template.name: template for template in DEFAULT_MODULE_TEMPLATES
}
MODULE_TYPE_BY_NAME: dict[str, str] = {
    template.name: template.template_id for template in DEFAULT_MODULE_TEMPLATES
}


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
        self._templates: list[ModuleTemplate] = list(DEFAULT_MODULE_TEMPLATES)

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
            module_item.setData(0, Qt.ItemDataRole.UserRole + 1, template.category)
            module_item.setData(0, Qt.ItemDataRole.UserRole + 2, template.template_id)
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
        module_category = str(item.data(0, Qt.ItemDataRole.UserRole + 1) or "Analysis")
        template_id = item.data(0, Qt.ItemDataRole.UserRole + 2)
        ModuleDragPayload(
            name=str(module_name),
            category=module_category,
            template_id=str(template_id) if template_id else None,
        ).encode(mime_data)
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
            item.setData(Qt.ItemDataRole.UserRole + 1, template.category)
            item.setData(Qt.ItemDataRole.UserRole + 2, template.template_id)
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
        module_category = str(item.data(Qt.ItemDataRole.UserRole + 1) or "Analysis")
        template_id = item.data(Qt.ItemDataRole.UserRole + 2)
        ModuleDragPayload(
            name=str(module_name),
            category=module_category,
            template_id=str(template_id) if template_id else None,
        ).encode(mime_data)
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


@dataclass(frozen=True)
class GridCoord:
    row: int
    col: int


@dataclass(frozen=True)
class ModuleCapability:
    category: str
    has_input: bool
    has_output: bool
    allowed_downstream_categories: tuple[str, ...]
    artifact_kind: str | None


MODULE_CAPABILITIES: dict[str, ModuleCapability] = {
    "Geometry": ModuleCapability(
        category="Geometry",
        has_input=False,
        has_output=True,
        allowed_downstream_categories=("Simulation", "Analysis", "Filter"),
        artifact_kind="geometry",
    ),
    "Simulation": ModuleCapability(
        category="Simulation",
        has_input=True,
        has_output=True,
        allowed_downstream_categories=("Analysis", "Filter", "Results"),
        artifact_kind="simulation",
    ),
    "Analysis": ModuleCapability(
        category="Analysis",
        has_input=True,
        has_output=True,
        allowed_downstream_categories=("Filter", "Results"),
        artifact_kind="analysis",
    ),
    "Filter": ModuleCapability(
        category="Filter",
        has_input=True,
        has_output=True,
        allowed_downstream_categories=("Analysis", "Results", "Filter"),
        artifact_kind="filtered",
    ),
    "Results": ModuleCapability(
        category="Results",
        has_input=True,
        has_output=False,
        allowed_downstream_categories=(),
        artifact_kind=None,
    ),
}


DEFAULT_CAPABILITY = MODULE_CAPABILITIES["Analysis"]
INPUT_PORT_ID = "in"
OUTPUT_PORT_ID = "out"


@dataclass(frozen=True)
class GridModule:
    id: str
    name: str
    category: str
    module_type: str
    capability: ModuleCapability
    coord: GridCoord
    payload: dict[str, object] | None = None


@dataclass(frozen=True)
class GridModuleDTO:
    id: str
    name: str
    category: str
    module_type: str
    row: int
    col: int
    payload: dict[str, object] | None = None


@dataclass(frozen=True)
class NodePortRef:
    node_id: str
    port_id: str
    direction: str


@dataclass(frozen=True)
class ConnectionDTO:
    id: str
    source: NodePortRef
    target: NodePortRef
    artifact_kind: str


@dataclass(frozen=True)
class GridEdgeDTO:
    source_id: str
    target_id: str


@dataclass(frozen=True)
class WorkflowGraphSnapshotDTO:
    modules: list[GridModuleDTO]
    connections: list[ConnectionDTO]
    linear_edges: list[GridEdgeDTO]


GridSnapshotDTO = WorkflowGraphSnapshotDTO


@dataclass(frozen=True)
class ModuleActivationRequest:
    node_id: str
    module_name: str
    category: str
    module_type: str


@dataclass(frozen=True)
class ConnectionDraftState:
    source_node_id: str
    source_port_id: str
    cursor_scene_pos: QPointF
    hover_target_node_id: str | None
    is_valid_target: bool
    validity_reason: str | None


@dataclass(frozen=True)
class PlacementTarget:
    kind: str
    row: int
    col: int


@dataclass(frozen=True)
class DropPlacementResult:
    module: GridModule
    target: PlacementTarget
    snapshot: WorkflowGraphSnapshotDTO


class WorkflowGridState:
    def __init__(self) -> None:
        self._next_id = 1
        self._next_connection_id = 1
        self._modules: dict[str, GridModule] = {}
        self._connections: dict[str, ConnectionDTO] = {}

    def has_modules(self) -> bool:
        return bool(self._modules)

    def get_module(self, module_id: str) -> GridModule | None:
        return self._modules.get(module_id)

    def sorted_modules(self) -> list[GridModule]:
        return sorted(
            self._modules.values(),
            key=lambda module: (module.coord.row, module.coord.col, module.id),
        )

    def sorted_connections(self) -> list[ConnectionDTO]:
        return sorted(self._connections.values(), key=lambda connection: connection.id)

    def row_indices(self) -> list[int]:
        return sorted({module.coord.row for module in self._modules.values()})

    def modules_in_row(self, row: int) -> list[GridModule]:
        return [module for module in self.sorted_modules() if module.coord.row == row]

    def insertion_columns(self, row: int) -> list[int]:
        row_modules = self.modules_in_row(row)
        if not row_modules:
            return [0]

        row_columns = sorted(module.coord.col for module in row_modules)
        candidates = [row_columns[0]]
        for column in row_columns:
            candidates.append(column + 1)
        return sorted(set(candidates))

    def row_bounds(self) -> tuple[int, int]:
        if not self._modules:
            return (0, 0)
        rows = [module.coord.row for module in self._modules.values()]
        return (min(rows), max(rows))

    def col_bounds(self) -> tuple[int, int]:
        if not self._modules:
            return (0, 0)
        cols = [module.coord.col for module in self._modules.values()]
        return (min(cols), max(cols))

    def insert_in_row(
        self,
        row: int,
        col: int,
        module_name: str,
        module_category: str,
        module_type: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> GridModule:
        updated: dict[str, GridModule] = {}
        for module in self._modules.values():
            if module.coord.row == row and module.coord.col >= col:
                updated[module.id] = GridModule(
                    id=module.id,
                    name=module.name,
                    category=module.category,
                    module_type=module.module_type,
                    capability=module.capability,
                    coord=GridCoord(row=row, col=module.coord.col + 1),
                    payload=deepcopy(module.payload),
                )
                continue
            updated[module.id] = module

        self._modules = updated
        return self._append_module(module_name, module_category, row, col, module_type, payload)

    def insert_row(
        self,
        row: int,
        col: int,
        module_name: str,
        module_category: str,
        module_type: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> GridModule:
        updated: dict[str, GridModule] = {}
        for module in self._modules.values():
            if module.coord.row >= row:
                updated[module.id] = GridModule(
                    id=module.id,
                    name=module.name,
                    category=module.category,
                    module_type=module.module_type,
                    capability=module.capability,
                    coord=GridCoord(row=module.coord.row + 1, col=module.coord.col),
                    payload=deepcopy(module.payload),
                )
                continue
            updated[module.id] = module

        self._modules = updated
        return self._append_module(module_name, module_category, row, col, module_type, payload)

    def validate_connection(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> tuple[bool, str | None, str | None]:
        source = self._modules.get(source_node_id)
        target = self._modules.get(target_node_id)
        if source is None or target is None:
            return (False, "Connection endpoints are missing.", None)
        if source.id == target.id:
            return (False, "A module cannot connect to itself.", None)
        if not source.capability.has_output:
            return (False, f"{source.category} modules do not expose output ports.", None)
        if not target.capability.has_input:
            return (False, f"{target.category} modules do not expose input ports.", None)
        if source.coord.col >= target.coord.col:
            return (False, "Connections must flow left-to-right.", None)
        if target.category not in source.capability.allowed_downstream_categories:
            return (
                False,
                f"Incompatible flow: {source.category} cannot connect to {target.category}.",
                None,
            )
        if any(
            connection.source.node_id == source_node_id
            and connection.target.node_id == target_node_id
            for connection in self._connections.values()
        ):
            return (False, "Connection already exists between these modules.", None)
        if any(connection.target.node_id == target_node_id for connection in self._connections.values()):
            return (False, "Target input already has an incoming connection.", None)
        if self._path_exists(target_node_id, source_node_id):
            return (False, "Connection would introduce a cycle.", None)

        artifact_kind = source.capability.artifact_kind or "artifact"
        return (True, None, artifact_kind)

    def add_connection(self, source_node_id: str, target_node_id: str) -> tuple[ConnectionDTO | None, str | None]:
        valid, reason, artifact_kind = self.validate_connection(source_node_id, target_node_id)
        if not valid or artifact_kind is None:
            return (None, reason or "Invalid connection.")

        connection_id = f"edge-{self._next_connection_id}"
        self._next_connection_id += 1
        connection = ConnectionDTO(
            id=connection_id,
            source=NodePortRef(node_id=source_node_id, port_id=OUTPUT_PORT_ID, direction="output"),
            target=NodePortRef(node_id=target_node_id, port_id=INPUT_PORT_ID, direction="input"),
            artifact_kind=artifact_kind,
        )
        self._connections[connection_id] = connection
        return (connection, None)

    def remove_connection(self, connection_id: str) -> bool:
        if connection_id not in self._connections:
            return False
        del self._connections[connection_id]
        return True

    def snapshot(self) -> WorkflowGraphSnapshotDTO:
        ordered = self.sorted_modules()
        modules = [
            GridModuleDTO(
                id=module.id,
                name=module.name,
                category=module.category,
                module_type=module.module_type,
                row=module.coord.row,
                col=module.coord.col,
                payload=deepcopy(module.payload),
            )
            for module in ordered
        ]
        edges = [
            GridEdgeDTO(source_id=ordered[index].id, target_id=ordered[index + 1].id)
            for index in range(len(ordered) - 1)
        ]
        return WorkflowGraphSnapshotDTO(
            modules=modules,
            connections=self.sorted_connections(),
            linear_edges=edges,
        )

    def _append_module(
        self,
        module_name: str,
        module_category: str,
        row: int,
        col: int,
        module_type: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> GridModule:
        module_id = f"node-{self._next_id}"
        self._next_id += 1
        capability = MODULE_CAPABILITIES.get(module_category, DEFAULT_CAPABILITY)
        module = GridModule(
            id=module_id,
            name=module_name,
            category=capability.category,
            module_type=module_type or MODULE_TYPE_BY_NAME.get(module_name, module_name.lower().replace(" ", "_")),
            capability=capability,
            coord=GridCoord(row=row, col=col),
            payload=deepcopy(payload),
        )
        self._modules[module_id] = module
        return module

    def _path_exists(self, start_node_id: str, end_node_id: str) -> bool:
        visited: set[str] = set()
        frontier: list[str] = [start_node_id]
        while frontier:
            current = frontier.pop()
            if current == end_node_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            frontier.extend(
                connection.target.node_id
                for connection in self._connections.values()
                if connection.source.node_id == current
            )
        return False


class ModulePortItem(QGraphicsEllipseItem):
    def __init__(
        self,
        node_id: str,
        port_id: str,
        direction: str,
        radius: float,
        parent: QGraphicsRectItem,
    ) -> None:
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0, parent)
        self.node_id = node_id
        self.port_id = port_id
        self.direction = direction
        self.setZValue(4)
        self.setAcceptHoverEvents(False)


class ConnectionPathItem(QGraphicsPathItem):
    def __init__(self, connection_id: str) -> None:
        super().__init__()
        self.connection_id = connection_id
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(0.6)


class WorkflowCanvasScene(QGraphicsScene):
    graph_changed = pyqtSignal(object)
    node_activated = pyqtSignal(object)
    status_message = pyqtSignal(str)

    NODE_WIDTH = 196
    NODE_HEIGHT = 196
    HEADER_HEIGHT = 30
    STEP_ROW_HEIGHT = 24
    PORT_RADIUS = 5.0
    COLUMN_GAP = 72
    ROW_GAP = 92
    GRID_MARGIN_X = 48
    GRID_MARGIN_Y = 48
    GRID_MARGIN_RIGHT = 180
    GRID_MARGIN_BOTTOM = 180
    COLUMN_OVERLAY_WIDTH = 26
    COLUMN_OVERLAY_EXTRA_HEIGHT = 24
    ROW_OVERLAY_HEIGHT = 24
    PLACEMENT_EMPTY = "empty_cell"
    PLACEMENT_COLUMN = "column_insert"
    PLACEMENT_ROW = "row_insert"
    MODULE_STEP_LABELS = ("Engineering Data", "Geometry", "Model", "Setup", "Results")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = WorkflowGridState()
        self._node_items: list[QGraphicsRectItem] = []
        self._overlay_items: dict[PlacementTarget, QGraphicsRectItem] = {}
        self._connection_items: dict[str, ConnectionPathItem] = {}
        self._input_ports: dict[str, ModulePortItem] = {}
        self._output_ports: dict[str, ModulePortItem] = {}
        self._active_target: PlacementTarget | None = None
        self._last_drop_result: DropPlacementResult | None = None
        self._draft_connection_item: QGraphicsPathItem | None = None
        self._draft_source_port: ModulePortItem | None = None
        self._draft_hover_target_port: ModulePortItem | None = None
        self._draft_state: ConnectionDraftState | None = None

        self._node_fill = QColor("#f8fbff")
        self._node_border = QColor("#2e4f77")
        self._node_text = QColor("#5f6b7a")
        self._node_header_fill = QColor("#376095")
        self._node_header_text = QColor("#f5f8ff")
        self._node_row_border = QColor("#d3dce8")
        self._overlay_valid_border = QColor("#1fc84b")
        self._overlay_valid_fill = QColor("#1fc84b30")
        self._overlay_active_border = QColor("#0fab37")

        self._port_input_color = QColor("#3ea0f0")
        self._port_output_color = QColor("#f08b3e")
        self._port_border_color = QColor("#1c2d43")
        self._port_compatible_color = QColor("#2abf52")
        self._port_active_color = QColor("#f4c542")
        self._port_disabled_color = QColor("#7f8b98")

        self._connection_color = QColor("#4a6f9e")
        self._connection_selected_color = QColor("#f4c542")
        self._connection_preview_valid = QColor("#2abf52")
        self._connection_preview_invalid = QColor("#cc3e3e")

        self._title_font = QFont()
        self._subtitle_font = QFont()
        self.selectionChanged.connect(self._refresh_connection_styles)
        self._update_scene_bounds()

    def begin_module_drag(self) -> None:
        self._render_overlays()

    def cancel_module_drag(self) -> None:
        self._clear_overlays()

    def update_drag_position(self, scene_point: QPointF) -> PlacementTarget | None:
        hovered_target = self._overlay_target_at(scene_point)
        self._set_active_target(hovered_target)
        return hovered_target

    def commit_module_drop(
        self,
        module_name: str,
        scene_point: QPointF,
        module_category: str | None = None,
        module_type: str | None = None,
    ) -> DropPlacementResult | None:
        if not module_name:
            self._clear_overlays()
            return None

        if not self._overlay_items:
            self._render_overlays()

        target = self._active_target or self.update_drag_position(scene_point)
        if target is None:
            self._clear_overlays()
            return None

        resolved_category = self._resolve_module_category(module_name, module_category)
        resolved_module_type = self._resolve_module_type(module_name, module_type)
        payload = self._default_payload(module_name)
        applied_target = target
        if target.kind in (self.PLACEMENT_EMPTY, self.PLACEMENT_COLUMN):
            module = self._grid.insert_in_row(
                target.row,
                target.col,
                module_name,
                resolved_category,
                resolved_module_type,
                payload,
            )
        elif target.kind == self.PLACEMENT_ROW:
            module = self._grid.insert_row(
                target.row,
                target.col,
                module_name,
                resolved_category,
                resolved_module_type,
                payload,
            )
        else:
            self._clear_overlays()
            return None

        self._render_grid_nodes()
        snapshot = self._grid.snapshot()
        self._last_drop_result = DropPlacementResult(
            module=module,
            target=applied_target,
            snapshot=snapshot,
        )
        self._clear_overlays()
        return self._last_drop_result

    def activate_node(self, node_id: str) -> bool:
        module = self._grid.get_module(node_id)
        if module is None:
            return False
        self.node_activated.emit(
            ModuleActivationRequest(
                node_id=module.id,
                module_name=module.name,
                category=module.category,
                module_type=module.module_type,
            )
        )
        return True

    def create_connection(
        self,
        source_node_id: str,
        target_node_id: str,
        emit_feedback: bool = True,
    ) -> bool:
        connection, reason = self._grid.add_connection(source_node_id, target_node_id)
        if connection is None:
            if emit_feedback and reason:
                self.status_message.emit(reason)
            return False

        self._render_connections()
        snapshot = self._grid.snapshot()
        self.graph_changed.emit(snapshot)
        if emit_feedback:
            source_module = self._grid.get_module(source_node_id)
            target_module = self._grid.get_module(target_node_id)
            source_name = source_module.name if source_module else source_node_id
            target_name = target_module.name if target_module else target_node_id
            self.status_message.emit(f"Connected {source_name} -> {target_name}.")
        return True

    def delete_selected_connections(self) -> int:
        selected_ids = [
            item.connection_id
            for item in self.selectedItems()
            if isinstance(item, ConnectionPathItem)
        ]
        if not selected_ids:
            return 0

        removed = 0
        for connection_id in selected_ids:
            if self._grid.remove_connection(connection_id):
                removed += 1

        if removed:
            self._render_connections()
            self.graph_changed.emit(self._grid.snapshot())
            suffix = "s" if removed != 1 else ""
            self.status_message.emit(f"Removed {removed} connection{suffix}.")
        return removed

    def snapshot(self) -> GridSnapshotDTO:
        return self._grid.snapshot()

    @property
    def last_drop_result(self) -> DropPlacementResult | None:
        return self._last_drop_result

    def node_id_by_name(self, module_name: str) -> str | None:
        for module in self._grid.sorted_modules():
            if module.name == module_name:
                return module.id
        return None

    def has_input_port(self, node_id: str) -> bool:
        return node_id in self._input_ports

    def has_output_port(self, node_id: str) -> bool:
        return node_id in self._output_ports

    def overlay_targets(self) -> list[PlacementTarget]:
        return list(self._overlay_items.keys())

    def overlay_count(self) -> int:
        return len(self._overlay_items)

    def overlay_center_for_target(self, target: PlacementTarget) -> QPointF | None:
        item = self._overlay_items.get(target)
        if item is None:
            return None
        return item.sceneBoundingRect().center()

    def grid_slot_center(self, row: int, col: int) -> QPointF:
        return self._module_rect(row, col).center()

    def connection_count(self) -> int:
        return len(self._grid.sorted_connections())

    def apply_theme(self, colors: dict[str, str]) -> None:
        self._node_fill = QColor(colors["node_bg"])
        self._node_border = QColor(colors["node_border"])
        self._node_text = QColor(colors["node_text_sub"])
        self._node_header_fill = QColor(colors.get("accent", colors["node_border"]))
        self._node_header_text = QColor(colors.get("icon_text", "#f5f8ff"))
        self._node_row_border = QColor(colors.get("border", "#d3dce8"))
        self._overlay_valid_border = QColor(colors.get("overlay_valid_border", "#1fc84b"))
        self._overlay_valid_fill = QColor(colors.get("overlay_valid_fill", "#1fc84b30"))
        self._overlay_active_border = QColor(colors.get("overlay_active_border", "#0fab37"))
        self._port_input_color = QColor(colors.get("port_input", "#3ea0f0"))
        self._port_output_color = QColor(colors.get("port_output", "#f08b3e"))
        self._port_border_color = QColor(colors.get("port_border", "#1c2d43"))
        self._port_compatible_color = QColor(colors.get("port_compatible", "#2abf52"))
        self._port_active_color = QColor(colors.get("port_active", "#f4c542"))
        self._port_disabled_color = QColor(colors.get("port_disabled", "#7f8b98"))
        self._connection_color = QColor(colors.get("connection_line", "#4a6f9e"))
        self._connection_selected_color = QColor(colors.get("connection_selected", "#f4c542"))
        self._connection_preview_valid = QColor(colors.get("connection_preview_valid", "#2abf52"))
        self._connection_preview_invalid = QColor(colors.get("connection_preview_invalid", "#cc3e3e"))
        self._render_grid_nodes()
        self._refresh_overlay_styles()
        self._refresh_port_highlights()

    def apply_typography(self, profile: TypographyProfile) -> None:
        typography = TypographyManager(profile)
        self._title_font = typography.font(TypographyRole.BODY)
        self._subtitle_font = typography.font(TypographyRole.GROUP_CAPTION)
        self._render_grid_nodes()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        output_port = self._port_item_at(event.scenePos(), "output")
        if output_port is not None:
            self.clearSelection()
            self._start_connection_draft(output_port, event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)
        self._refresh_connection_styles()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._draft_source_port is not None:
            self._update_connection_draft(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._draft_source_port is not None:
            self._finish_connection_draft(event.scenePos())
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._refresh_connection_styles()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        module = self._module_at(event.scenePos())
        if module is not None:
            self.activate_node(module.id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _render_grid_nodes(self) -> None:
        self._clear_connection_draft()
        self._clear_connection_items()
        self._input_ports.clear()
        self._output_ports.clear()

        for item in self._node_items:
            self.removeItem(item)
        self._node_items.clear()

        modules = self._grid.sorted_modules()
        for index, module in enumerate(modules, start=1):
            rect = self._module_rect(module.coord.row, module.coord.col)
            rect_item = QGraphicsRectItem(0, 0, self.NODE_WIDTH, self.NODE_HEIGHT)
            rect_item.setPos(rect.x(), rect.y())
            rect_item.setBrush(self._node_fill)
            rect_item.setPen(QPen(self._node_border, 1))
            rect_item.setZValue(1)
            rect_item.setData(0, module.id)
            rect_item.setData(1, module.module_type)
            rect_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.addItem(rect_item)
            self._node_items.append(rect_item)

            header = QGraphicsRectItem(0, 0, self.NODE_WIDTH, self.HEADER_HEIGHT, rect_item)
            header.setBrush(self._node_header_fill)
            header.setPen(QPen(self._node_border, 1))

            title = QGraphicsSimpleTextItem(self._truncate_label(module.name, 20), rect_item)
            title.setPos(9, 6)
            title.setFont(self._title_font)
            title.setBrush(self._node_header_text)

            for row_index, step_label in enumerate(self.MODULE_STEP_LABELS, start=1):
                row_y = self.HEADER_HEIGHT + (row_index - 1) * self.STEP_ROW_HEIGHT
                row_divider = QGraphicsRectItem(0, row_y, self.NODE_WIDTH, 1, rect_item)
                row_divider.setBrush(self._node_row_border)
                row_divider.setPen(QPen(Qt.PenStyle.NoPen))

                number = QGraphicsSimpleTextItem(f"{row_index}", rect_item)
                number.setPos(8, row_y + 4)
                number.setFont(self._subtitle_font)
                number.setBrush(self._node_text)

                step = QGraphicsSimpleTextItem(step_label, rect_item)
                step.setPos(30, row_y + 4)
                step.setFont(self._subtitle_font)
                step.setBrush(self._node_text)

            subtitle = QGraphicsSimpleTextItem(f"Node {index}", rect_item)
            subtitle.setPos(8, self.NODE_HEIGHT - 20)
            subtitle.setFont(self._subtitle_font)
            subtitle.setBrush(self._node_text)

            if module.capability.has_input:
                input_port = ModulePortItem(
                    node_id=module.id,
                    port_id=INPUT_PORT_ID,
                    direction="input",
                    radius=self.PORT_RADIUS,
                    parent=rect_item,
                )
                input_port.setPos(0, self.NODE_HEIGHT / 2.0)
                self._input_ports[module.id] = input_port
                self._apply_port_style(input_port, "default")

            if module.capability.has_output:
                output_port = ModulePortItem(
                    node_id=module.id,
                    port_id=OUTPUT_PORT_ID,
                    direction="output",
                    radius=self.PORT_RADIUS,
                    parent=rect_item,
                )
                output_port.setPos(self.NODE_WIDTH, self.NODE_HEIGHT / 2.0)
                self._output_ports[module.id] = output_port
                self._apply_port_style(output_port, "default")

        self._update_scene_bounds()
        self._render_connections()

    def _render_connections(self) -> None:
        self._clear_connection_items()
        for connection in self._grid.sorted_connections():
            source_port = self._output_ports.get(connection.source.node_id)
            target_port = self._input_ports.get(connection.target.node_id)
            if source_port is None or target_port is None:
                continue

            start = source_port.sceneBoundingRect().center()
            end = target_port.sceneBoundingRect().center()
            item = ConnectionPathItem(connection.id)
            item.setPath(self._orthogonal_path(start, end))
            item.setPen(QPen(self._connection_color, 2))
            self.addItem(item)
            self._connection_items[connection.id] = item
        self._refresh_connection_styles()

    def _clear_connection_items(self) -> None:
        for item in self._connection_items.values():
            self.removeItem(item)
        self._connection_items.clear()

    def _start_connection_draft(self, source_port: ModulePortItem, cursor: QPointF) -> None:
        self._clear_overlays()
        self._draft_source_port = source_port
        self._draft_hover_target_port = None

        if self._draft_connection_item is not None:
            self.removeItem(self._draft_connection_item)
        self._draft_connection_item = QGraphicsPathItem()
        self._draft_connection_item.setZValue(3.5)
        self.addItem(self._draft_connection_item)
        self._update_connection_draft(cursor)

    def _update_connection_draft(self, cursor: QPointF) -> None:
        source_port = self._draft_source_port
        draft_item = self._draft_connection_item
        if source_port is None or draft_item is None:
            return

        source_point = source_port.sceneBoundingRect().center()
        hovered_input = self._port_item_at(cursor, "input")
        is_valid_target = False
        reason: str | None = None
        if hovered_input is not None:
            is_valid_target, reason, _artifact = self._grid.validate_connection(
                source_port.node_id,
                hovered_input.node_id,
            )

        if hovered_input is not None and is_valid_target:
            self._draft_hover_target_port = hovered_input
            target_point = hovered_input.sceneBoundingRect().center()
        else:
            self._draft_hover_target_port = None
            target_point = cursor

        self._draft_state = ConnectionDraftState(
            source_node_id=source_port.node_id,
            source_port_id=source_port.port_id,
            cursor_scene_pos=cursor,
            hover_target_node_id=self._draft_hover_target_port.node_id if self._draft_hover_target_port else None,
            is_valid_target=is_valid_target,
            validity_reason=reason,
        )
        preview_pen_color = self._connection_preview_valid if (hovered_input is None or is_valid_target) else self._connection_preview_invalid
        draft_item.setPen(QPen(preview_pen_color, 2, Qt.PenStyle.DashLine))
        draft_item.setPath(self._orthogonal_path(source_point, target_point))
        self._refresh_port_highlights(
            source_node_id=source_port.node_id,
            active_target_node_id=self._draft_hover_target_port.node_id if self._draft_hover_target_port else None,
        )

    def _finish_connection_draft(self, release_point: QPointF) -> None:
        source_port = self._draft_source_port
        target_port = self._port_item_at(release_point, "input")
        if source_port is not None and target_port is not None:
            self.create_connection(source_port.node_id, target_port.node_id, emit_feedback=True)
        self._clear_connection_draft()

    def _clear_connection_draft(self) -> None:
        if self._draft_connection_item is not None and self._draft_connection_item.scene() is self:
            self.removeItem(self._draft_connection_item)
        self._draft_connection_item = None
        self._draft_source_port = None
        self._draft_hover_target_port = None
        self._draft_state = None
        self._refresh_port_highlights()

    def _port_item_at(self, point: QPointF, direction: str) -> ModulePortItem | None:
        for item in self.items(point):
            if isinstance(item, ModulePortItem) and item.direction == direction:
                return item
        return None

    def _apply_port_style(self, port: ModulePortItem, mode: str) -> None:
        if mode == "compatible":
            brush = self._port_compatible_color
            border = self._port_border_color
        elif mode == "active":
            brush = self._port_active_color
            border = self._port_border_color
        elif mode == "disabled":
            brush = self._port_disabled_color
            border = self._port_border_color
        else:
            brush = self._port_input_color if port.direction == "input" else self._port_output_color
            border = self._port_border_color

        port.setBrush(brush)
        port.setPen(QPen(border, 1))

    def _refresh_port_highlights(
        self,
        source_node_id: str | None = None,
        active_target_node_id: str | None = None,
    ) -> None:
        for port in self._input_ports.values():
            self._apply_port_style(port, "default")
        for port in self._output_ports.values():
            self._apply_port_style(port, "default")

        if source_node_id is None:
            return

        source_port = self._output_ports.get(source_node_id)
        if source_port is not None:
            self._apply_port_style(source_port, "active")

        for node_id, input_port in self._input_ports.items():
            valid, _reason, _artifact = self._grid.validate_connection(source_node_id, node_id)
            if valid:
                self._apply_port_style(input_port, "compatible")
            else:
                self._apply_port_style(input_port, "disabled")

        if active_target_node_id is not None and active_target_node_id in self._input_ports:
            self._apply_port_style(self._input_ports[active_target_node_id], "active")

    def _refresh_connection_styles(self) -> None:
        for connection_id, item in self._connection_items.items():
            if item.isSelected():
                item.setPen(QPen(self._connection_selected_color, 3))
            else:
                item.setPen(QPen(self._connection_color, 2))

    def _orthogonal_path(self, start: QPointF, end: QPointF) -> QPainterPath:
        path = QPainterPath(start)
        midpoint_x = start.x() + max(28.0, (end.x() - start.x()) * 0.5)
        path.lineTo(midpoint_x, start.y())
        path.lineTo(midpoint_x, end.y())
        path.lineTo(end)
        return path

    def _resolve_module_category(self, module_name: str, module_category: str | None) -> str:
        if module_category:
            return module_category
        return MODULE_CATEGORY_BY_NAME.get(module_name, "Analysis")

    def _resolve_module_type(self, module_name: str, module_type: str | None) -> str:
        if module_type:
            return module_type
        return MODULE_TYPE_BY_NAME.get(module_name, module_name.lower().replace(" ", "_"))

    def _default_payload(self, module_name: str) -> dict[str, object] | None:
        template = MODULE_TEMPLATE_BY_NAME.get(module_name)
        if template is None or template.payload is None:
            return None
        return deepcopy(template.payload)

    def _module_at(self, point: QPointF) -> GridModule | None:
        for item in self.items(point):
            current_item: QGraphicsItem | None = item
            while current_item is not None:
                node_id = current_item.data(0)
                if isinstance(node_id, str):
                    return self._grid.get_module(node_id)
                current_item = current_item.parentItem()
        return None

    def _truncate_label(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return f"{value[: max(0, limit - 3)]}..."

    def _render_overlays(self) -> None:
        self._clear_overlays()
        if not self._grid.has_modules():
            target = PlacementTarget(kind=self.PLACEMENT_EMPTY, row=0, col=0)
            self._add_overlay(target, self._module_rect(0, 0))
            return

        rows = self._grid.row_indices()
        for row in rows:
            for col in self._grid.insertion_columns(row):
                target = PlacementTarget(kind=self.PLACEMENT_COLUMN, row=row, col=col)
                self._add_overlay(target, self._column_overlay_rect(row, col))

        insertion_rows = sorted(set(rows + [row + 1 for row in rows]))
        row_columns = self._row_overlay_columns()
        for row in insertion_rows:
            for col in row_columns:
                target = PlacementTarget(kind=self.PLACEMENT_ROW, row=row, col=col)
                self._add_overlay(target, self._row_overlay_rect(row, col))

    def _add_overlay(self, target: PlacementTarget, rect: QRectF) -> None:
        existing = self._overlay_items.get(target)
        if existing is not None:
            self.removeItem(existing)

        item = QGraphicsRectItem(rect)
        item.setBrush(self._overlay_valid_fill)
        item.setPen(QPen(self._overlay_valid_border, 2, Qt.PenStyle.DashLine))
        item.setZValue(10)
        self.addItem(item)
        self._overlay_items[target] = item

    def _clear_overlays(self) -> None:
        for item in self._overlay_items.values():
            self.removeItem(item)
        self._overlay_items.clear()
        self._active_target = None

    def _overlay_target_at(self, point: QPointF) -> PlacementTarget | None:
        candidates = [
            target
            for target, item in self._overlay_items.items()
            if item.sceneBoundingRect().contains(point)
        ]
        if not candidates:
            return None

        for priority_kind in (self.PLACEMENT_EMPTY, self.PLACEMENT_COLUMN, self.PLACEMENT_ROW):
            for target in candidates:
                if target.kind == priority_kind:
                    return target
        return candidates[0]

    def _set_active_target(self, target: PlacementTarget | None) -> None:
        if self._active_target == target:
            return

        if self._active_target in self._overlay_items:
            old_item = self._overlay_items[self._active_target]
            old_item.setPen(QPen(self._overlay_valid_border, 2, Qt.PenStyle.DashLine))

        self._active_target = target
        if target in self._overlay_items:
            active_item = self._overlay_items[target]
            active_item.setPen(QPen(self._overlay_active_border, 2, Qt.PenStyle.DashLine))

    def _refresh_overlay_styles(self) -> None:
        for target, item in self._overlay_items.items():
            border_color = self._overlay_active_border if target == self._active_target else self._overlay_valid_border
            item.setBrush(self._overlay_valid_fill)
            item.setPen(QPen(border_color, 2, Qt.PenStyle.DashLine))

    def _module_rect(self, row: int, col: int) -> QRectF:
        x = self.GRID_MARGIN_X + col * (self.NODE_WIDTH + self.COLUMN_GAP)
        y = self.GRID_MARGIN_Y + row * (self.NODE_HEIGHT + self.ROW_GAP)
        return QRectF(x, y, self.NODE_WIDTH, self.NODE_HEIGHT)

    def _column_overlay_rect(self, row: int, col: int) -> QRectF:
        slot_x = self._module_rect(row, col).x()
        x = slot_x - (self.COLUMN_GAP / 2.0) - (self.COLUMN_OVERLAY_WIDTH / 2.0)
        y = self._module_rect(row, col).y() - (self.COLUMN_OVERLAY_EXTRA_HEIGHT / 2.0)
        height = self.NODE_HEIGHT + self.COLUMN_OVERLAY_EXTRA_HEIGHT
        return QRectF(x, y, self.COLUMN_OVERLAY_WIDTH, height)

    def _row_overlay_columns(self) -> list[int]:
        min_col, max_col = self._grid.col_bounds()
        return list(range(min_col, max_col + 2))

    def _row_overlay_rect(self, row: int, col: int) -> QRectF:
        width = max(42, self.NODE_WIDTH - 12)
        x = self.GRID_MARGIN_X + col * (self.NODE_WIDTH + self.COLUMN_GAP) + 6
        y = (
            self.GRID_MARGIN_Y
            + row * (self.NODE_HEIGHT + self.ROW_GAP)
            - (self.ROW_GAP / 2.0)
            - (self.ROW_OVERLAY_HEIGHT / 2.0)
        )
        return QRectF(x, y, width, self.ROW_OVERLAY_HEIGHT)

    def _update_scene_bounds(self) -> None:
        if self._grid.has_modules():
            _min_row, max_row = self._grid.row_bounds()
            _min_col, max_col = self._grid.col_bounds()
        else:
            max_row = 0
            max_col = 0

        width = (
            self.GRID_MARGIN_X
            + (max_col + 1) * (self.NODE_WIDTH + self.COLUMN_GAP)
            + self.GRID_MARGIN_RIGHT
        )
        height = (
            self.GRID_MARGIN_Y
            + (max_row + 1) * (self.NODE_HEIGHT + self.ROW_GAP)
            + self.GRID_MARGIN_BOTTOM
        )
        self.setSceneRect(0, 0, width, height)
class WorkflowCanvasView(QGraphicsView):
    module_dropped = pyqtSignal(str)
    grid_changed = pyqtSignal(object)

    def __init__(self, scene: WorkflowCanvasScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setBackgroundBrush(QColor("#f3f6fb"))
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _workflow_scene(self) -> WorkflowCanvasScene:
        return self.scene()  # type: ignore[return-value]

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if ModuleDragPayload.decode(event.mimeData()) is not None:
            scene = self._workflow_scene()
            scene.begin_module_drag()
            scene_point = self.mapToScene(event.position().toPoint())
            scene.update_drag_position(scene_point)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if ModuleDragPayload.decode(event.mimeData()) is not None:
            scene = self._workflow_scene()
            scene_point = self.mapToScene(event.position().toPoint())
            scene.update_drag_position(scene_point)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._workflow_scene().cancel_module_drag()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        payload = ModuleDragPayload.decode(event.mimeData())
        if payload is None:
            self._workflow_scene().cancel_module_drag()
            event.ignore()
            return

        scene_point = self.mapToScene(event.position().toPoint())
        if self.drop_module_at_scene_point(
            payload.name,
            scene_point,
            payload.category,
            payload.template_id,
        ):
            event.acceptProposedAction()
            return

        event.ignore()

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.setBackgroundBrush(QColor(colors["canvas_bg"]))
        self.setStyleSheet(f"QGraphicsView {{ border: 1px solid {colors['border']}; }}")

    def drop_module_at_scene_point(
        self,
        module_name: str,
        scene_point: QPointF,
        module_category: str | None = None,
        module_type: str | None = None,
    ) -> bool:
        scene = self._workflow_scene()
        result = scene.commit_module_drop(module_name, scene_point, module_category, module_type)
        if result is None:
            return False

        self.module_dropped.emit(module_name)
        self.grid_changed.emit(result.snapshot)
        return True

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            removed = self._workflow_scene().delete_selected_connections()
            if removed > 0:
                event.accept()
                return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.setFocus()
        super().mousePressEvent(event)


class OrchestrateWorkspace(QWidget):
    node_activated = pyqtSignal(object)
    status_message = pyqtSignal(str)
    grid_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.module_selector = ModuleSelectorPanel(self)
        self.library = self.module_selector.library

        self.scene = WorkflowCanvasScene(self)
        self.canvas = WorkflowCanvasView(self.scene, self)
        self.canvas.module_dropped.connect(self._on_module_dropped)
        self.canvas.grid_changed.connect(self._on_grid_changed)
        self.scene.graph_changed.connect(self._on_grid_changed)
        self.scene.node_activated.connect(self.node_activated.emit)
        self.scene.status_message.connect(self.status_message.emit)

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
        result = self.scene.last_drop_result
        if result is None:
            self.status_message.emit(f"Added module to workflow: {module_name}")
            return

        placement_label = {
            WorkflowCanvasScene.PLACEMENT_EMPTY: "origin cell",
            WorkflowCanvasScene.PLACEMENT_COLUMN: "column insertion",
            WorkflowCanvasScene.PLACEMENT_ROW: "row insertion",
        }.get(result.target.kind, result.target.kind)
        self.status_message.emit(
            "Added module to workflow: "
            f"{module_name} (row {result.module.coord.row}, col {result.module.coord.col}, {placement_label})"
        )

    def _on_grid_changed(self, snapshot: GridSnapshotDTO) -> None:
        self.grid_changed.emit(snapshot)

