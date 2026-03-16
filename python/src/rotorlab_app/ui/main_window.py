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
        "app_bg": "#131923",
        "title_bg": "#172231",
        "title_border": "#243345",
        "text_primary": "#e8eef7",
        "text_muted": "#9fb0c8",
        "menu_bg": "#1b2636",
        "menu_border": "#2a3d56",
        "menu_hover": "#2d4360",
        "tab_row_bg": "#0f1723",
        "tab_bg": "#1a2738",
        "tab_active": "#2c3f5a",
        "tab_border": "#2e4158",
        "context_bg": "#111c2b",
        "ribbon_group_bg": "#152334",
        "ribbon_group_border": "#2d4562",
        "ribbon_title": "#9cb1cc",
        "ribbon_hover": "#314967",
        "status_bg": "#101a2a",
        "status_border": "#24364d",
        "workspace_bg": "#161f2d",
        "placeholder_sub": "#8d9eb6",
        "accent": "#4d80c4",
        "icon_text": "#f4f8ff",
        "close_hover": "#c42b1c",
        "border": "#2a3a50",
        "library_bg": "#252d39",
        "library_alt": "#2d3542",
        "library_text": "#e7edf7",
        "canvas_bg": "#d0d4da",
        "node_bg": "#f8fbff",
        "node_border": "#2e4f77",
        "node_text_sub": "#5f6b7a",
        "overlay_valid_border": "#2fd651",
        "overlay_valid_fill": "#2fd65130",
        "overlay_active_border": "#1cb73d",
        "port_input": "#5db4ff",
        "port_output": "#ffb15f",
        "port_border": "#223349",
        "port_compatible": "#3bcf67",
        "port_active": "#ffd166",
        "port_disabled": "#6e7f93",
        "connection_line": "#6d91bf",
        "connection_selected": "#ffd166",
        "connection_preview_valid": "#3bcf67",
        "connection_preview_invalid": "#d15858",
    },
    "Light": {
        "app_bg": "#eef2f8",
        "title_bg": "#dce6f4",
        "title_border": "#b8c9e0",
        "text_primary": "#1a2a3f",
        "text_muted": "#58708f",
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
        "icon_text": "#f7fbff",
        "close_hover": "#c42b1c",
        "border": "#b4c6dd",
        "library_bg": "#f1f5fc",
        "library_alt": "#e8eef8",
        "library_text": "#1b2b40",
        "canvas_bg": "#f7f9fc",
        "node_bg": "#ffffff",
        "node_border": "#376095",
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

    def open_environment_tab(self, environment: str, object_name: str) -> None:
        for index in range(self.environment_tabs.count()):
            tab_id = self.environment_tabs.tabData(index)
            if tab_id is None:
                continue
            context = self._tab_context_by_id[int(tab_id)]
            if context.environment == environment and context.object_name == object_name:
                self.environment_tabs.setCurrentIndex(index)
                self._update_state(f"Focused existing tab: {environment}: {object_name}")
                return

        tab_id = self._next_tab_id
        self._next_tab_id += 1
        label = f"{environment}: {object_name}"
        tab_index = self.environment_tabs.addTab(label)
        self.environment_tabs.setTabData(tab_index, tab_id)

        placeholder = self._create_environment_placeholder(environment, object_name)
        self.workspace_stack.addWidget(placeholder)

        context = TabContext(environment=environment, object_name=object_name, tab_id=tab_id)
        self._tab_context_by_id[tab_id] = context
        self._tab_widget_by_id[tab_id] = placeholder

        self.environment_tabs.setCurrentIndex(tab_index)
        self._update_state(f"Opened {label}")

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
        self.orchestrate.apply_theme(colors)

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
            QWidget#ContextRow {{
                background-color: {colors["context_bg"]};
                border-bottom: 1px solid {colors["border"]};
            }}
            QWidget#ContextRibbon {{
                background-color: {colors["context_bg"]};
            }}
            QWidget#RibbonGroup {{
                background-color: transparent;
                border: none;
                margin: 0px 2px;
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
                background-color: transparent;
                color: {colors["text_primary"]};
                border: 1px solid {colors["status_border"]};
                padding: 2px 8px;
            }}
            QStatusBar QPushButton:hover {{
                background-color: {colors["menu_hover"]};
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
        self.orchestrate.apply_typography(self._typography_profile)

        self._typography.apply(self.environment_tabs, TypographyRole.TAB_LABEL)
        self._typography.apply(self.state_label, TypographyRole.STATUS)
        self._typography.apply(self.console_button, TypographyRole.STATUS)

        status_bar = self.statusBar()
        if status_bar is not None:
            self._typography.apply(status_bar, TypographyRole.STATUS)

        for widget in self._tab_widget_by_id.values():
            if widget.objectName() == "EnvironmentPlaceholder":
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
