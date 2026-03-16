from __future__ import annotations

import pytest
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLabel, QToolButton

from rotorlab_app.ui.main_window import ConsoleDialog, RotorLabMainWindow
from rotorlab_app.ui.typography import TypographyManager, TypographyRole, default_typography_profile


def _font_signature(font: QFont) -> tuple[str, int, int]:
    return (font.family(), font.pointSize(), int(font.weight()))


def _ribbon_widgets(window: RotorLabMainWindow) -> tuple[QToolButton, QToolButton, QLabel]:
    large = window.context_ribbon.findChild(QToolButton, "RibbonLargeButton")
    small = window.context_ribbon.findChild(QToolButton, "RibbonSmallButton")
    caption = window.context_ribbon.findChild(QLabel, "RibbonGroupTitle")
    assert large is not None
    assert small is not None
    assert caption is not None
    return large, small, caption


@pytest.fixture
def typography_profile():
    return default_typography_profile()


@pytest.fixture
def typography_manager(typography_profile):
    return TypographyManager(typography_profile)


@pytest.fixture
def window(qtbot, typography_profile):
    main_window = RotorLabMainWindow(typography_profile=typography_profile)
    qtbot.addWidget(main_window)
    main_window.show()
    qtbot.wait(50)
    return main_window


def test_window_boot_applies_global_base_font(window, typography_manager):
    app = QApplication.instance()
    assert app is not None

    expected = typography_manager.font(TypographyRole.APP_BASE)
    assert _font_signature(app.font()) == _font_signature(expected)


def test_typography_roles_mapped_to_core_widgets(window, typography_manager):
    large, small, caption = _ribbon_widgets(window)

    assert _font_signature(window.title_bar.app_title_label.font()) == _font_signature(
        typography_manager.font(TypographyRole.TITLE_BRAND)
    )
    assert _font_signature(window.title_bar.menu_buttons[0].font()) == _font_signature(
        typography_manager.font(TypographyRole.MENU_ITEM)
    )
    assert _font_signature(window.environment_tabs.font()) == _font_signature(
        typography_manager.font(TypographyRole.TAB_LABEL)
    )
    assert _font_signature(large.font()) == _font_signature(
        typography_manager.font(TypographyRole.RIBBON_LARGE)
    )
    assert _font_signature(small.font()) == _font_signature(
        typography_manager.font(TypographyRole.RIBBON_SMALL)
    )
    assert _font_signature(caption.font()) == _font_signature(
        typography_manager.font(TypographyRole.GROUP_CAPTION)
    )
    assert _font_signature(window.state_label.font()) == _font_signature(
        typography_manager.font(TypographyRole.STATUS)
    )
    assert _font_signature(window.console_button.font()) == _font_signature(
        typography_manager.font(TypographyRole.STATUS)
    )

    header_item = window.orchestrate.library.item(0)
    module_item = window.orchestrate.library.item(1)
    assert _font_signature(header_item.font()) == _font_signature(
        typography_manager.font(TypographyRole.GROUP_CAPTION)
    )
    assert _font_signature(module_item.font()) == _font_signature(
        typography_manager.font(TypographyRole.BODY)
    )


def test_window_controls_use_symbol_font(window, typography_manager):
    expected = typography_manager.font(TypographyRole.SYMBOL)
    for button in (
        window.title_bar.minimize_button,
        window.title_bar.maximize_button,
        window.title_bar.close_button,
    ):
        assert _font_signature(button.font()) == _font_signature(expected)
        assert "MDL2" in button.font().family()


def test_theme_switch_preserves_typography_roles(window):
    def snapshot() -> dict[str, tuple[str, int, int]]:
        large, small, caption = _ribbon_widgets(window)
        return {
            "title": _font_signature(window.title_bar.app_title_label.font()),
            "menu": _font_signature(window.title_bar.menu_buttons[0].font()),
            "tab": _font_signature(window.environment_tabs.font()),
            "ribbon_large": _font_signature(large.font()),
            "ribbon_small": _font_signature(small.font()),
            "caption": _font_signature(caption.font()),
            "status": _font_signature(window.state_label.font()),
            "lib_header": _font_signature(window.orchestrate.library.item(0).font()),
            "lib_item": _font_signature(window.orchestrate.library.item(1).font()),
        }

    before = snapshot()
    window._on_global_action("Theme: Light")
    after = snapshot()
    assert before == after


def test_console_and_new_environment_placeholder_typography(window, typography_profile, typography_manager):
    dialog = ConsoleDialog(["engine log line"], typography_profile)
    expected_mono = typography_manager.font(TypographyRole.MONO_LOG)
    assert _font_signature(dialog.output.font()) == _font_signature(expected_mono)

    window.open_environment_tab("CAD", "Propeller_01")
    placeholder = window.workspace_stack.currentWidget()
    title = placeholder.findChild(QLabel, "PlaceholderTitle")
    subtitle = placeholder.findChild(QLabel, "PlaceholderSubtitle")
    description = placeholder.findChild(QLabel, "PlaceholderDescription")
    assert title is not None
    assert subtitle is not None
    assert description is not None

    assert _font_signature(title.font()) == _font_signature(
        typography_manager.font(TypographyRole.PANEL_HEADER)
    )
    assert _font_signature(subtitle.font()) == _font_signature(
        typography_manager.font(TypographyRole.GROUP_CAPTION)
    )
    assert _font_signature(description.font()) == _font_signature(
        typography_manager.font(TypographyRole.BODY)
    )

