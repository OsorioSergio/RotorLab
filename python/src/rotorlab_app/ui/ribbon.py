from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rotorlab_app.ui.typography import TypographyManager, TypographyProfile, TypographyRole


@dataclass(frozen=True)
class RibbonActionDef:
    key: str
    label: str
    size: str
    icon_text: str


@dataclass(frozen=True)
class RibbonGroupDef:
    title: str
    actions: tuple[RibbonActionDef, ...]


RIBBON_LAYOUTS: dict[str, tuple[RibbonGroupDef, ...]] = {
    "Orchestrate": (
        RibbonGroupDef(
            "Graph",
            (
                RibbonActionDef("Validate Graph", "Validate\nGraph", "large", "V"),
                RibbonActionDef("Run Workflow", "Run\nWorkflow", "large", "R"),
                RibbonActionDef("Stop Execution", "Stop", "small", "S"),
            ),
        ),
        RibbonGroupDef(
            "Modules",
            (
                RibbonActionDef("Open CAD Tab", "Open CAD", "large", "C"),
                RibbonActionDef("Open Simulation Tab", "Open Simulation", "small", "Si"),
                RibbonActionDef("Open Results Tab", "Open Results", "small", "Re"),
            ),
        ),
        RibbonGroupDef(
            "Canvas",
            (
                RibbonActionDef("Fit Canvas", "Fit Canvas", "small", "F"),
                RibbonActionDef("Auto Layout", "Auto Layout", "small", "A"),
                RibbonActionDef("Clear Selection", "Clear Selection", "small", "Cl"),
            ),
        ),
    ),
    "CAD": (
        RibbonGroupDef(
            "Geometry",
            (
                RibbonActionDef("Regenerate Geometry", "Regenerate", "large", "G"),
                RibbonActionDef("Import Profile", "Import Profile", "small", "I"),
                RibbonActionDef("Export Surface", "Export Surface", "small", "E"),
            ),
        ),
        RibbonGroupDef(
            "Inspect",
            (
                RibbonActionDef("Open Measure Panel", "Measure", "large", "M"),
                RibbonActionDef("Section View", "Section View", "small", "Se"),
                RibbonActionDef("Curvature Plot", "Curvature", "small", "Cu"),
            ),
        ),
        RibbonGroupDef(
            "Build",
            (
                RibbonActionDef("Generate Mesh", "Generate Mesh", "small", "Me"),
                RibbonActionDef("Validate Model", "Validate Model", "small", "Va"),
            ),
        ),
    ),
    "Simulation": (
        RibbonGroupDef(
            "Setup",
            (
                RibbonActionDef("Build Mesh", "Build Mesh", "large", "M"),
                RibbonActionDef("Boundary Conditions", "Boundary Conditions", "small", "B"),
                RibbonActionDef("Solver Settings", "Solver Settings", "small", "Ss"),
            ),
        ),
        RibbonGroupDef(
            "Execution",
            (
                RibbonActionDef("Run Solver", "Run Solver", "large", "R"),
                RibbonActionDef("Stop", "Stop", "small", "S"),
                RibbonActionDef("Monitor Run", "Monitor", "small", "Mo"),
            ),
        ),
        RibbonGroupDef(
            "Post",
            (
                RibbonActionDef("Export Case", "Export Case", "small", "E"),
                RibbonActionDef("Open Results Tab", "Open Results", "small", "Re"),
            ),
        ),
    ),
    "Results": (
        RibbonGroupDef(
            "Analysis",
            (
                RibbonActionDef("Refresh Results", "Refresh", "large", "Rf"),
                RibbonActionDef("Compare Runs", "Compare", "large", "Co"),
                RibbonActionDef("Export Report", "Export Report", "small", "Ex"),
            ),
        ),
        RibbonGroupDef(
            "Visualize",
            (
                RibbonActionDef("Open Plot", "Open Plot", "small", "P"),
                RibbonActionDef("Table View", "Table View", "small", "T"),
                RibbonActionDef("Take Snapshot", "Snapshot", "small", "Sn"),
            ),
        ),
    ),
}


class ContextRibbon(QWidget):
    action_triggered = pyqtSignal(str)

    def __init__(self, row_height: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ContextRibbon")
        self.setFixedHeight(row_height)
        self._row_height = row_height

        self._current_environment = "Orchestrate"
        self._theme_colors: dict[str, str] = {}
        self._typography_profile: TypographyProfile | None = None
        self._typography: TypographyManager | None = None

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._layout.setSpacing(0)

        self.set_environment(self._current_environment)

    def apply_theme(self, colors: dict[str, str]) -> None:
        self._theme_colors = colors
        self.set_environment(self._current_environment)

    def apply_typography(self, profile: TypographyProfile) -> None:
        self._typography_profile = profile
        self._typography = TypographyManager(profile)
        self.set_environment(self._current_environment)

    def set_environment(self, environment: str) -> None:
        target_environment = environment if environment in RIBBON_LAYOUTS else "Results"
        self._current_environment = target_environment
        self._clear_layout()

        groups = RIBBON_LAYOUTS[target_environment]
        for index, group in enumerate(groups):
            if index > 0:
                separator = QFrame(self)
                separator.setObjectName("RibbonGroupSeparator")
                separator.setFrameShape(QFrame.Shape.VLine)
                separator.setFrameShadow(QFrame.Shadow.Plain)
                self._layout.addWidget(separator)
            self._layout.addWidget(self._create_group_widget(group))

        self._layout.addStretch(1)

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _create_group_widget(self, group: RibbonGroupDef) -> QWidget:
        group_frame = QWidget(self)
        group_frame.setObjectName("RibbonGroup")

        frame_layout = QVBoxLayout(group_frame)
        frame_layout.setContentsMargins(10, 4, 10, 2)
        frame_layout.setSpacing(2)

        actions_widget = QWidget(group_frame)
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)

        large_actions = [action for action in group.actions if action.size == "large"]
        small_actions = [action for action in group.actions if action.size != "large"]

        for action in large_actions:
            actions_layout.addWidget(self._create_action_button(action))

        if small_actions:
            small_columns_container = QWidget(actions_widget)
            small_columns_layout = QHBoxLayout(small_columns_container)
            small_columns_layout.setContentsMargins(0, 0, 0, 0)
            small_columns_layout.setSpacing(6)

            for index in range(0, len(small_actions), 2):
                column = QWidget(small_columns_container)
                column_layout = QVBoxLayout(column)
                column_layout.setContentsMargins(0, 0, 0, 0)
                column_layout.setSpacing(4)
                for action in small_actions[index : index + 2]:
                    column_layout.addWidget(self._create_action_button(action))
                column_layout.addStretch(1)
                small_columns_layout.addWidget(column)

            actions_layout.addWidget(small_columns_container)

        frame_layout.addWidget(actions_widget, 1)

        title = QLabel(group.title, group_frame)
        title.setObjectName("RibbonGroupTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self._typography is not None:
            self._typography.apply(title, TypographyRole.GROUP_CAPTION)
        frame_layout.addWidget(title)

        return group_frame

    def _create_action_button(self, action: RibbonActionDef) -> QToolButton:
        button = QToolButton(self)
        button.clicked.connect(
            lambda _checked=False, action_key=action.key: self.action_triggered.emit(action_key)
        )
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setText(action.label)
        button.setIcon(self._make_placeholder_icon(action.icon_text, action.size == "large"))

        if action.size == "large":
            button.setObjectName("RibbonLargeButton")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIconSize(QSize(24, 24))
            large_height = max(64, self._row_height - 30)
            button.setFixedSize(84, large_height)
            if self._typography is not None:
                self._typography.apply(button, TypographyRole.RIBBON_LARGE)
        else:
            button.setObjectName("RibbonSmallButton")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(18, 18))
            button.setMinimumWidth(138)
            button.setFixedHeight(26)
            if self._typography is not None:
                self._typography.apply(button, TypographyRole.RIBBON_SMALL)

        return button

    def _make_placeholder_icon(self, label: str, large: bool) -> QIcon:
        size = 24 if large else 18
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        accent = self._theme_colors.get("accent", "#4d80c4")
        icon_text = self._theme_colors.get("icon_text", "#f4f8ff")
        color = QColor(accent)
        if not large:
            color = color.lighter(120)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, size, size, 4, 4)

        painter.setPen(QColor(icon_text))
        if self._typography is not None:
            family = self._typography.font(TypographyRole.BODY).family()
        else:
            family = "Segoe UI"
        font = QFont(family, 8 if large else 7, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label[:2])
        painter.end()
        return QIcon(pixmap)
