from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rotorlab_app.models.propeller import (
    ADVANCED_PROPELLER_MODULE_TYPE,
    PropellerEnvironmentSession,
    create_default_propeller_feature_state,
)
from rotorlab_app.ui.advanced_propeller import AdvancedPropellerWorkspace
from rotorlab_app.ui.orchestrate import OrchestrateWorkspace
from rotorlab_app.ui.ribbon import ContextRibbon
from rotorlab_app.ui.typography import (
    TypographyManager,
    TypographyProfile,
    TypographyRole,
    default_typography_profile,
)


THEMES: dict[str, dict[str, str]] = {
    "Dark": {
        "app_bg": "#252525",
        "title_bg": "#2b2b2b",
        "title_border": "#3a3a3a",
        "text_primary": "#e0e0e0",
        "text_muted": "#999999",
        "text_disabled": "#555555",
        "menu_bg": "#333333",
        "menu_border": "#454545",
        "menu_hover": "#3c3c3c",
        "tab_row_bg": "#252525",
        "tab_bg": "#2e2e2e",
        "tab_active": "#3c3c3c",
        "tab_border": "#444444",
        "context_bg": "#333333",
        "ribbon_group_bg": "#3a3a3a",
        "ribbon_group_border": "#474747",
        "ribbon_title": "#b7b7b7",
        "ribbon_hover": "#444444",
        "status_bg": "#2b2b2b",
        "status_border": "#3d3d3d",
        "workspace_bg": "#2f2f2f",
        "placeholder_sub": "#999999",
        "accent": "#0078d4",
        "icon_bg": "#5a5a5a",
        "icon_text": "#f1f1f1",
        "button_bg": "#383838",
        "button_hover": "#5a5a5a",
        "button_pressed": "#444444",
        "input_bg": "#383838",
        "input_focus": "#444444",
        "close_hover": "#c42b1c",
        "border": "#444444",
        "table_header_bg": "#353535",
        "table_row_even": "#2a2a2a",
        "table_row_odd": "#313131",
        "library_bg": "#252525",
        "library_alt": "#2e2e2e",
        "library_text": "#e0e0e0",
        "canvas_bg": "#484848",
        "node_bg": "#2f2f2f",
        "node_border": "#4a4a4a",
        "node_header_bg": "#353535",
        "node_header_text": "#e0e0e0",
        "node_text_sub": "#bdbdbd",
        "overlay_valid_border": "#0078d4",
        "overlay_valid_fill": "#0078d426",
        "overlay_active_border": "#e8a628",
        "port_input": "#0078d4",
        "port_output": "#e8a628",
        "port_border": "#232323",
        "port_compatible": "#69b66c",
        "port_active": "#e8a628",
        "port_disabled": "#6e6e6e",
        "connection_line": "#7d91a6",
        "connection_selected": "#0078d4",
        "connection_preview_valid": "#69b66c",
        "connection_preview_invalid": "#c95a5a",
    },
    "Light": {
        "app_bg": "#eef2f8",
        "title_bg": "#dce6f4",
        "title_border": "#b8c9e0",
        "text_primary": "#1a2a3f",
        "text_muted": "#58708f",
        "text_disabled": "#90a0b3",
        "menu_bg": "#f5f8fc",
        "menu_border": "#c6d3e5",
        "menu_hover": "#dbe8fa",
        "tab_row_bg": "#dbe5f2",
        "tab_bg": "#edf3fb",
        "tab_active": "#c9dcf4",
        "tab_border": "#b7cae2",
        "context_bg": "#e7eef9",
        "ribbon_group_bg": "#f7faff",
        "ribbon_group_border": "#c3d2e7",
        "ribbon_title": "#426285",
        "ribbon_hover": "#d4e3f8",
        "status_bg": "#dbe7f6",
        "status_border": "#b6c9e3",
        "workspace_bg": "#e9eef7",
        "placeholder_sub": "#5d7695",
        "accent": "#3f73bb",
        "icon_bg": "#d4deec",
        "icon_text": "#f7fbff",
        "button_bg": "#edf3fb",
        "button_hover": "#dbe8fa",
        "button_pressed": "#c9dcf4",
        "input_bg": "#ffffff",
        "input_focus": "#f0f5fd",
        "close_hover": "#c42b1c",
        "border": "#b4c6dd",
        "table_header_bg": "#e3ebf7",
        "table_row_even": "#f7f9fc",
        "table_row_odd": "#edf3fb",
        "library_bg": "#f1f5fc",
        "library_alt": "#e8eef8",
        "library_text": "#1b2b40",
        "canvas_bg": "#f7f9fc",
        "node_bg": "#ffffff",
        "node_border": "#376095",
        "node_header_bg": "#d7e4f4",
        "node_header_text": "#1a2a3f",
        "node_text_sub": "#566b84",
        "overlay_valid_border": "#28bf49",
        "overlay_valid_fill": "#28bf4926",
        "overlay_active_border": "#149634",
        "port_input": "#2f8fdf",
        "port_output": "#d97f2f",
        "port_border": "#38587f",
        "port_compatible": "#1ea84a",
        "port_active": "#d9a520",
        "port_disabled": "#8a95a4",
        "connection_line": "#4f78ac",
        "connection_selected": "#d9a520",
        "connection_preview_valid": "#1ea84a",
        "connection_preview_invalid": "#bf4444",
    },
}


@dataclass(frozen=True)
class TabContext:
    environment: str
    object_name: str
    tab_id: int
    node_id: str | None = None
    module_type: str | None = None


class ConsoleDialog(QDialog):
    def __init__(
        self,
        logs: list[str],
        typography_profile: TypographyProfile,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("RotorLab Console")
        self.resize(900, 420)
        self._typography = TypographyManager(typography_profile)

        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setPlainText("\n".join(logs) if logs else "No logs yet.")
        self._typography.apply(self.output, TypographyRole.MONO_LOG)

        layout = QVBoxLayout(self)
        layout.addWidget(self.output)


class TitleBar(QWidget):
    global_action_triggered = pyqtSignal(str)

    def __init__(self, main_window: QMainWindow, row_height: int = 34) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._drag_start_position: QPoint | None = None
        self._row_height = row_height

        self.setObjectName("TitleBar")
        self.setFixedHeight(row_height)
        self._typography_profile: TypographyProfile | None = None
        self._typography: TypographyManager | None = None
        self.menu_buttons: list[QToolButton] = []
        self.menus: list[QMenu] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)

        self.app_title_label = QLabel("RotorLab", self)
        self.app_title_label.setObjectName("TitleBarAppName")
        layout.addWidget(self.app_title_label)
        layout.addSpacing(8)

        self._add_menu_button(
            layout,
            "File",
            ["New Project", "Open Project", "Save", "Save As"],
        )
        self._add_menu_button(layout, "Edit", ["Undo", "Redo"])
        self._add_menu_button(layout, "Run", ["Validate Project", "Run Workflow", "Stop Execution"])
        self._add_menu_button(
            layout,
            "View",
            ["Toggle Left Panel", "Toggle Right Panel", "Open Task Monitor"],
            include_theme_selector=True,
        )
        self._add_menu_button(layout, "Tools", ["Preferences"])
        self._add_menu_button(layout, "Help", ["Documentation"])

        layout.addStretch(1)

        self.minimize_button = self._create_window_button("\ue921", "Minimize")
        self.maximize_button = self._create_window_button("\ue922", "Maximize")
        self.close_button = self._create_window_button("\ue8bb", "Close", "WindowCloseButton")

        self.minimize_button.clicked.connect(self._main_window.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_maximized)
        self.close_button.clicked.connect(self._main_window.close)

        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

    def _add_menu_button(
        self,
        layout: QHBoxLayout,
        title: str,
        actions: list[str],
        include_theme_selector: bool = False,
    ) -> None:
        button = QToolButton(self)
        button.setObjectName("TitleMenuButton")
        button.setText(title)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        menu = QMenu(button)
        for action_name in actions:
            action = QAction(action_name, self)
            action.triggered.connect(
                lambda _checked=False, name=action_name: self.global_action_triggered.emit(name)
            )
            menu.addAction(action)

        if include_theme_selector:
            menu.addSeparator()
            theme_menu = menu.addMenu("Theme")
            for theme_name in ("Dark", "Light"):
                action = QAction(theme_name, self)
                action.triggered.connect(
                    lambda _checked=False, name=theme_name: self.global_action_triggered.emit(
                        f"Theme: {name}"
                    )
                )
                theme_menu.addAction(action)

        button.setMenu(menu)
        self.menu_buttons.append(button)
        self.menus.append(menu)
        layout.addWidget(button)

    def _create_window_button(
        self,
        glyph: str,
        tooltip: str,
        object_name: str = "WindowControlButton",
    ) -> QPushButton:
        button = QPushButton(glyph, self)
        button.setObjectName(object_name)
        button.setFixedSize(46, self._row_height)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(tooltip)
        return button

    def _toggle_maximized(self) -> None:
        if self._main_window.isMaximized():
            self._main_window.showNormal()
        else:
            self._main_window.showMaximized()
        self.sync_maximize_button()

    def sync_maximize_button(self) -> None:
        self.maximize_button.setText("\ue923" if self._main_window.isMaximized() else "\ue922")

    def _apply_menu_font_recursive(self, menu: QMenu, font) -> None:
        menu.setFont(font)
        for action in menu.actions():
            action.setFont(font)
            submenu = action.menu()
            if submenu is not None:
                self._apply_menu_font_recursive(submenu, font)

    def apply_typography(self, profile: TypographyProfile) -> None:
        self._typography_profile = profile
        self._typography = TypographyManager(profile)

        self._typography.apply(self.app_title_label, TypographyRole.TITLE_BRAND)
        for menu_button in self.menu_buttons:
            self._typography.apply(menu_button, TypographyRole.MENU_ITEM)

        menu_font = self._typography.font(TypographyRole.MENU_ITEM)
        for menu in self.menus:
            self._apply_menu_font_recursive(menu, menu_font)

        self._typography.apply(self.minimize_button, TypographyRole.SYMBOL)
        self._typography.apply(self.maximize_button, TypographyRole.SYMBOL)
        self._typography.apply(self.close_button, TypographyRole.SYMBOL)

    def apply_theme(self, colors: dict[str, str]) -> None:
        self.setStyleSheet(
            f"""
            QWidget#TitleBar {{
                background-color: {colors["title_bg"]};
                border: 1px solid {colors["title_border"]};
                border-bottom: none;
            }}
            QLabel#TitleBarAppName {{
                color: {colors["text_primary"]};
                padding: 0 8px;
            }}
            QToolButton#TitleMenuButton {{
                color: {colors["text_primary"]};
                border: none;
                min-height: {self._row_height}px;
                padding: 0 12px;
            }}
            QToolButton#TitleMenuButton::menu-indicator {{
                image: none;
            }}
            QToolButton#TitleMenuButton:hover {{
                background-color: {colors["menu_hover"]};
            }}
            QPushButton#WindowControlButton,
            QPushButton#WindowCloseButton {{
                border: none;
                color: {colors["text_primary"]};
                min-width: 46px;
                min-height: {self._row_height}px;
                max-width: 46px;
                max-height: {self._row_height}px;
                background-color: transparent;
                padding: 0;
                margin: 0;
            }}
            QPushButton#WindowControlButton:hover {{
                background-color: {colors["menu_hover"]};
            }}
            QPushButton#WindowCloseButton:hover {{
                background-color: {colors["close_hover"]};
                color: #ffffff;
            }}
            QMenu {{
                background-color: {colors["menu_bg"]};
                color: {colors["text_primary"]};
                border: 1px solid {colors["menu_border"]};
            }}
            QMenu::item:selected {{
                background-color: {colors["menu_hover"]};
            }}
            """
        )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximized()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_start_position is None
            or not (event.buttons() & Qt.MouseButton.LeftButton)
            or self._main_window.isMaximized()
        ):
            super().mouseMoveEvent(event)
            return

        current_position = event.globalPosition().toPoint()
        delta = current_position - self._drag_start_position
        self._main_window.move(self._main_window.pos() + delta)
        self._drag_start_position = current_position
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_position = None
        super().mouseReleaseEvent(event)


class RotorLabMainWindow(QMainWindow):
    def __init__(self, typography_profile: TypographyProfile | None = None) -> None:
        super().__init__()
        self.setWindowTitle("RotorLab")
        self.resize(1400, 860)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._row_height = 34
        self._ribbon_height = self._row_height * 3
        self._current_theme = "Dark"
        self._typography_profile = typography_profile or default_typography_profile()
        self._typography = TypographyManager(self._typography_profile)

        self._logs: list[str] = []
        self._next_tab_id = 1
        self._tab_context_by_id: dict[int, TabContext] = {}
        self._tab_widget_by_id: dict[int, QWidget] = {}
        self._propeller_sessions_by_node_id: dict[str, PropellerEnvironmentSession] = {}

        self.title_bar = TitleBar(self, self._row_height)
        self.title_bar.global_action_triggered.connect(self._on_global_action)

        self.environment_tabs = QTabBar(self)
        self.environment_tabs.setObjectName("EnvironmentTabs")
        self.environment_tabs.setDocumentMode(True)
        self.environment_tabs.setExpanding(False)
        self.environment_tabs.setUsesScrollButtons(True)
        self.environment_tabs.setTabsClosable(True)
        self.environment_tabs.setFixedHeight(self._row_height)
        self.environment_tabs.currentChanged.connect(self._on_tab_changed)
        self.environment_tabs.tabCloseRequested.connect(self._on_tab_close_requested)

        self.context_ribbon = ContextRibbon(self._ribbon_height, self)
        self.context_ribbon.action_triggered.connect(self._on_context_ribbon_action)

        self.workspace_stack = QStackedWidget(self)
        self.orchestrate = OrchestrateWorkspace(self)
        self.orchestrate.status_message.connect(self._update_state)
        self.orchestrate.node_activated.connect(self._on_module_activated)

        self._create_shell_layout()
        self._build_status_bar()
        self._add_initial_orchestrate_tab()
        self._apply_theme(self._current_theme)
        self._apply_typography()

    def _create_shell_layout(self) -> None:
        top_section = QWidget(self)
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        top_layout.addWidget(self.title_bar)

        self.environment_row = QWidget(self)
        self.environment_row.setObjectName("EnvironmentRow")
        self.environment_row.setFixedHeight(self._row_height)
        env_layout = QHBoxLayout(self.environment_row)
        env_layout.setContentsMargins(0, 0, 0, 0)
        env_layout.setSpacing(0)
        env_layout.addWidget(self.environment_tabs)
        top_layout.addWidget(self.environment_row)

        self.context_row = QWidget(self)
        self.context_row.setObjectName("ContextRow")
        self.context_row.setFixedHeight(self._ribbon_height)
        context_layout = QHBoxLayout(self.context_row)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(0)
        context_layout.addWidget(self.context_ribbon)
        top_layout.addWidget(self.context_row)

        shell = QWidget(self)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(top_section)
        shell_layout.addWidget(self.workspace_stack, 1)
        self.setCentralWidget(shell)

    def _build_status_bar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)

        self.state_label = QLabel("Ready", self)
        status.addWidget(self.state_label, 1)

        self.console_button = QPushButton("Open Console", self)
        self.console_button.clicked.connect(self._open_console_dialog)
        status.addPermanentWidget(self.console_button)

    def _add_initial_orchestrate_tab(self) -> None:
        tab_id = self._next_tab_id
        self._next_tab_id += 1

        index = self.environment_tabs.addTab("Orchestrate")
        self.environment_tabs.setTabData(index, tab_id)
        self.environment_tabs.setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
        self.environment_tabs.setTabButton(index, QTabBar.ButtonPosition.LeftSide, None)

        context = TabContext(environment="Orchestrate", object_name="Workflow", tab_id=tab_id)
        self._tab_context_by_id[tab_id] = context
        self._tab_widget_by_id[tab_id] = self.orchestrate
        self.workspace_stack.addWidget(self.orchestrate)

        self.environment_tabs.setCurrentIndex(index)
        self._rebuild_context_ribbon(context)
        self.log("Orchestrate environment initialized.")

    def open_environment_tab(
        self,
        environment: str,
        object_name: str,
        node_id: str | None = None,
        module_type: str | None = None,
    ) -> None:
        for index in range(self.environment_tabs.count()):
            tab_id = self.environment_tabs.tabData(index)
            if tab_id is None:
                continue
            context = self._tab_context_by_id[int(tab_id)]
            if node_id is not None and context.node_id == node_id:
                self.environment_tabs.setCurrentIndex(index)
                self._update_state(f"Focused existing tab: {environment}: {object_name}")
                return
            if node_id is None and context.environment == environment and context.object_name == object_name:
                self.environment_tabs.setCurrentIndex(index)
                self._update_state(f"Focused existing tab: {environment}: {object_name}")
                return

        tab_id = self._next_tab_id
        self._next_tab_id += 1
        label = f"{environment}: {object_name}"
        tab_index = self.environment_tabs.addTab(label)
        self.environment_tabs.setTabData(tab_index, tab_id)

        widget = self._create_environment_widget(environment, object_name, node_id, module_type)
        current_colors = THEMES.get(self._current_theme)
        if current_colors is not None and hasattr(widget, "apply_theme"):
            widget.apply_theme(current_colors)  # type: ignore[attr-defined]
        if hasattr(widget, "apply_typography"):
            widget.apply_typography(self._typography_profile)  # type: ignore[attr-defined]
        self.workspace_stack.addWidget(widget)

        context = TabContext(
            environment=environment,
            object_name=object_name,
            tab_id=tab_id,
            node_id=node_id,
            module_type=module_type,
        )
        self._tab_context_by_id[tab_id] = context
        self._tab_widget_by_id[tab_id] = widget

        self.environment_tabs.setCurrentIndex(tab_index)
        self._update_state(f"Opened {label}")

    def _create_environment_widget(
        self,
        environment: str,
        object_name: str,
        node_id: str | None,
        module_type: str | None,
    ) -> QWidget:
        if environment == "Advanced Propeller" and node_id is not None:
            session = self._propeller_sessions_by_node_id.get(node_id)
            if session is None:
                session = PropellerEnvironmentSession(
                    feature_state=create_default_propeller_feature_state(node_id, object_name)
                )
                self._propeller_sessions_by_node_id[node_id] = session
            workspace = AdvancedPropellerWorkspace(session, self)
            workspace.status_message.connect(self._update_state)
            return workspace
        return self._create_environment_placeholder(environment, object_name)

    def _create_environment_placeholder(self, environment: str, object_name: str) -> QWidget:
        widget = QWidget(self)
        widget.setObjectName("EnvironmentPlaceholder")
        layout = QVBoxLayout(widget)
        title = QLabel(f"{environment} Workspace", widget)
        title.setObjectName("PlaceholderTitle")
        subtitle = QLabel(f"Context: {object_name}", widget)
        subtitle.setObjectName("PlaceholderSubtitle")
        description = QLabel(
            "This environment is a placeholder while the dedicated workspace is under construction.",
            widget,
        )
        description.setWordWrap(True)
        description.setObjectName("PlaceholderDescription")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(description)
        layout.addStretch(1)

        self._typography.apply(title, TypographyRole.PANEL_HEADER)
        self._typography.apply(subtitle, TypographyRole.GROUP_CAPTION)
        self._typography.apply(description, TypographyRole.BODY)
        return widget

    def _on_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        tab_id = self.environment_tabs.tabData(index)
        if tab_id is None:
            return

        context = self._tab_context_by_id[int(tab_id)]
        widget = self._tab_widget_by_id[int(tab_id)]
        self.workspace_stack.setCurrentWidget(widget)
        self._rebuild_context_ribbon(context)
        self._update_state(f"Active environment: {context.environment}")

    def _on_tab_close_requested(self, index: int) -> None:
        if index == 0:
            return

        tab_id = self.environment_tabs.tabData(index)
        if tab_id is None:
            return

        tab_key = int(tab_id)
        context = self._tab_context_by_id.get(tab_key)
        widget = self._tab_widget_by_id.get(tab_key)
        if context is None or widget is None:
            return

        self.workspace_stack.removeWidget(widget)
        widget.deleteLater()
        self.environment_tabs.removeTab(index)
        del self._tab_context_by_id[tab_key]
        del self._tab_widget_by_id[tab_key]
        self.log(f"Closed tab: {context.environment}: {context.object_name}")

    def _rebuild_context_ribbon(self, context: TabContext) -> None:
        self.context_ribbon.set_environment(context.environment)

    def _on_context_ribbon_action(self, action_name: str) -> None:
        current_widget = self.workspace_stack.currentWidget()
        if current_widget is not None and hasattr(current_widget, "handle_action"):
            handled = current_widget.handle_action(action_name)  # type: ignore[attr-defined]
            if handled:
                return
        if action_name == "Open CAD Tab":
            self.open_environment_tab("CAD", "Propeller_01")
            return
        if action_name == "Open Simulation Tab":
            self.open_environment_tab("Simulation", "BEMT_Run_01")
            return
        if action_name == "Open Results Tab":
            self.open_environment_tab("Results", "Sweep_A")
            return

        self._on_context_action(action_name)

    def _on_global_action(self, action_name: str) -> None:
        if action_name.startswith("Theme:"):
            theme_name = action_name.split(":", 1)[1].strip()
            self._apply_theme(theme_name)
            self._apply_typography()
            self._update_state(f"Theme changed: {theme_name}")
            return

        self.log(f"Global action triggered: {action_name}")
        self._update_state(action_name)

    def _on_context_action(self, action_name: str) -> None:
        self.log(f"Context action triggered: {action_name}")
        self._update_state(action_name)

    def _on_module_activated(self, request) -> None:
        environment = "Results"
        if request.module_type == ADVANCED_PROPELLER_MODULE_TYPE:
            environment = "Advanced Propeller"
        elif request.category == "Geometry":
            environment = "CAD"
        elif request.category == "Simulation":
            environment = "Simulation"
        elif request.category == "Analysis" or request.category == "Results":
            environment = "Results"

        self.open_environment_tab(
            environment,
            request.module_name,
            node_id=request.node_id,
            module_type=request.module_type,
        )

    def _open_console_dialog(self) -> None:
        dialog = ConsoleDialog(self._logs, self._typography_profile, self)
        dialog.exec()

    def _apply_theme(self, theme_name: str) -> None:
        colors = THEMES.get(theme_name)
        if colors is None:
            return

        self._current_theme = theme_name
        self.title_bar.apply_theme(colors)
        self.context_ribbon.apply_theme(colors)
        for widget in self._tab_widget_by_id.values():
            if hasattr(widget, "apply_theme"):
                widget.apply_theme(colors)  # type: ignore[attr-defined]

        self.setStyleSheet(
            f"""
            QMainWindow {{
                background-color: {colors["app_bg"]};
                color: {colors["text_primary"]};
            }}
            QWidget#EnvironmentRow {{
                background-color: {colors["tab_row_bg"]};
                border-top: 1px solid {colors["title_border"]};
                border-bottom: 1px solid {colors["tab_border"]};
            }}
            QTabBar#EnvironmentTabs {{
                background-color: {colors["tab_row_bg"]};
                color: {colors["text_primary"]};
            }}
            QTabBar#EnvironmentTabs::tab {{
                background-color: {colors["tab_bg"]};
                color: {colors["text_primary"]};
                border: 1px solid {colors["tab_border"]};
                padding: 6px 14px;
            }}
            QTabBar#EnvironmentTabs::tab:selected {{
                background-color: {colors["tab_active"]};
            }}
            QTabBar#EnvironmentTabs::tab:hover:!selected {{
                background-color: {colors["menu_hover"]};
            }}
            QWidget#ContextRow {{
                background-color: {colors["context_bg"]};
                border-bottom: 1px solid {colors["border"]};
            }}
            QWidget#ContextRibbon {{
                background-color: {colors["context_bg"]};
            }}
            QWidget#RibbonGroup {{
                background-color: {colors["ribbon_group_bg"]};
                border: 1px solid {colors["ribbon_group_border"]};
                border-radius: 6px;
                margin: 3px 6px 0 0;
            }}
            QFrame#RibbonGroupSeparator {{
                color: {colors["border"]};
                background-color: {colors["border"]};
                min-width: 1px;
                max-width: 1px;
                margin-top: 8px;
                margin-bottom: 20px;
                margin-left: 2px;
                margin-right: 2px;
            }}
            QLabel#RibbonGroupTitle {{
                color: {colors["ribbon_title"]};
            }}
            QToolButton#RibbonLargeButton,
            QToolButton#RibbonSmallButton {{
                color: {colors["text_primary"]};
                border: 1px solid transparent;
                background-color: transparent;
                text-align: left;
                padding: 2px;
            }}
            QToolButton#RibbonLargeButton:hover,
            QToolButton#RibbonSmallButton:hover {{
                background-color: {colors["ribbon_hover"]};
                border-color: {colors["border"]};
            }}
            QWidget#EnvironmentPlaceholder {{
                background-color: {colors["workspace_bg"]};
            }}
            QLabel#PlaceholderTitle {{
                color: {colors["text_primary"]};
            }}
            QLabel#PlaceholderSubtitle {{
                color: {colors["placeholder_sub"]};
            }}
            QLabel#PlaceholderDescription {{
                color: {colors["text_primary"]};
            }}
            QStatusBar {{
                background-color: {colors["status_bg"]};
                color: {colors["text_primary"]};
                border-top: 1px solid {colors["status_border"]};
            }}
            QStatusBar QPushButton {{
                background-color: {colors["button_bg"]};
                color: {colors["text_primary"]};
                border: 1px solid {colors["status_border"]};
                padding: 2px 8px;
            }}
            QStatusBar QPushButton:hover {{
                background-color: {colors["button_hover"]};
            }}
            QStatusBar QPushButton:pressed {{
                background-color: {colors["button_pressed"]};
            }}
            QMenu {{
                background-color: {colors["menu_bg"]};
                color: {colors["text_primary"]};
                border: 1px solid {colors["menu_border"]};
            }}
            QMenu::item:selected {{
                background-color: {colors["menu_hover"]};
            }}
            """
        )

    def _apply_placeholder_typography(self, widget: QWidget) -> None:
        title = widget.findChild(QLabel, "PlaceholderTitle")
        subtitle = widget.findChild(QLabel, "PlaceholderSubtitle")
        description = widget.findChild(QLabel, "PlaceholderDescription")
        if title is not None:
            self._typography.apply(title, TypographyRole.PANEL_HEADER)
        if subtitle is not None:
            self._typography.apply(subtitle, TypographyRole.GROUP_CAPTION)
        if description is not None:
            self._typography.apply(description, TypographyRole.BODY)

    def _apply_typography(self) -> None:
        app = QApplication.instance()
        self._typography.apply_application(app)

        self.title_bar.apply_typography(self._typography_profile)
        self.context_ribbon.apply_typography(self._typography_profile)

        self._typography.apply(self.environment_tabs, TypographyRole.TAB_LABEL)
        self._typography.apply(self.state_label, TypographyRole.STATUS)
        self._typography.apply(self.console_button, TypographyRole.STATUS)

        status_bar = self.statusBar()
        if status_bar is not None:
            self._typography.apply(status_bar, TypographyRole.STATUS)

        for widget in self._tab_widget_by_id.values():
            if hasattr(widget, "apply_typography"):
                widget.apply_typography(self._typography_profile)  # type: ignore[attr-defined]
            elif widget.objectName() == "EnvironmentPlaceholder":
                self._apply_placeholder_typography(widget)

    def changeEvent(self, event) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if hasattr(self, "title_bar"):
            self.title_bar.sync_maximize_button()

    def _update_state(self, message: str) -> None:
        self.state_label.setText(message)
        self.log(f"STATE: {message}")

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._logs.append(f"[{timestamp}] {message}")
