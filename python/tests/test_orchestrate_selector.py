from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLabel

from rotorlab_app.ui.main_window import RotorLabMainWindow
from rotorlab_app.ui.typography import default_typography_profile


@pytest.fixture
def window(qtbot):
    main_window = RotorLabMainWindow(typography_profile=default_typography_profile())
    qtbot.addWidget(main_window)
    main_window.show()
    qtbot.wait(50)
    return main_window


def test_module_selector_has_title(window):
    title = window.orchestrate.module_selector.findChild(QLabel, "ModuleSelectorTitle")
    assert title is not None
    assert title.text() == "Module Selection"


def test_module_categories_are_collapsible(window):
    tree = window.orchestrate.library
    category = tree.category_items[0]
    assert category.isExpanded()

    tree._on_item_clicked(category, 0)
    assert not category.isExpanded()

    tree._on_item_clicked(category, 0)
    assert category.isExpanded()


def test_module_items_have_placeholder_icons(window):
    for module_item in window.orchestrate.library.module_items:
        assert not module_item.icon(0).isNull()


def test_module_selector_collapse_stops_at_icon_mode(window, qtbot):
    selector = window.orchestrate.module_selector
    splitter = window.orchestrate._splitter

    splitter.setSizes([10, 1400])
    qtbot.wait(50)

    assert selector.width() >= selector.collapsed_width
    assert selector.is_icon_mode()
    assert selector.icon_rail.isVisible()
    assert selector.icon_rail.count() > 0
