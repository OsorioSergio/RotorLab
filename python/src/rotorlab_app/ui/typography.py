from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QWidget


class TypographyRole(StrEnum):
    APP_BASE = "app_base"
    TITLE_BRAND = "title_brand"
    MENU_ITEM = "menu_item"
    TAB_LABEL = "tab_label"
    RIBBON_LARGE = "ribbon_large"
    RIBBON_SMALL = "ribbon_small"
    GROUP_CAPTION = "group_caption"
    PANEL_HEADER = "panel_header"
    BODY = "body"
    STATUS = "status"
    MONO_LOG = "mono_log"
    SYMBOL = "symbol"


@dataclass(frozen=True)
class FontRoleSpec:
    families: tuple[str, ...]
    point_size: int
    weight: QFont.Weight = QFont.Weight.Normal
    italic: bool = False
    letter_spacing: float | None = None


@dataclass(frozen=True)
class TypographyProfile:
    specs: dict[TypographyRole, FontRoleSpec]
    fallback_families: tuple[str, ...] = (
        "Segoe UI",
        "Arial",
        "Sans Serif",
    )

    def spec(self, role: TypographyRole) -> FontRoleSpec:
        return self.specs[role]


def default_typography_profile() -> TypographyProfile:
    return TypographyProfile(
        specs={
            TypographyRole.APP_BASE: FontRoleSpec(
                families=("Segoe UI",),
                point_size=10,
                weight=QFont.Weight.Normal,
            ),
            TypographyRole.TITLE_BRAND: FontRoleSpec(
                families=("Segoe UI",),
                point_size=11,
                weight=QFont.Weight.DemiBold,
            ),
            TypographyRole.MENU_ITEM: FontRoleSpec(
                families=("Segoe UI",),
                point_size=10,
                weight=QFont.Weight.Medium,
            ),
            TypographyRole.TAB_LABEL: FontRoleSpec(
                families=("Segoe UI",),
                point_size=10,
                weight=QFont.Weight.Medium,
            ),
            TypographyRole.RIBBON_LARGE: FontRoleSpec(
                families=("Segoe UI",),
                point_size=10,
                weight=QFont.Weight.Medium,
            ),
            TypographyRole.RIBBON_SMALL: FontRoleSpec(
                families=("Segoe UI",),
                point_size=10,
                weight=QFont.Weight.Normal,
            ),
            TypographyRole.GROUP_CAPTION: FontRoleSpec(
                families=("Segoe UI",),
                point_size=9,
                weight=QFont.Weight.Normal,
            ),
            TypographyRole.PANEL_HEADER: FontRoleSpec(
                families=("Segoe UI",),
                point_size=11,
                weight=QFont.Weight.DemiBold,
            ),
            TypographyRole.BODY: FontRoleSpec(
                families=("Segoe UI",),
                point_size=10,
                weight=QFont.Weight.Normal,
            ),
            TypographyRole.STATUS: FontRoleSpec(
                families=("Segoe UI",),
                point_size=9,
                weight=QFont.Weight.Normal,
            ),
            TypographyRole.MONO_LOG: FontRoleSpec(
                families=("Consolas", "Cascadia Mono", "Courier New"),
                point_size=10,
                weight=QFont.Weight.Normal,
            ),
            TypographyRole.SYMBOL: FontRoleSpec(
                families=("Segoe MDL2 Assets",),
                point_size=10,
                weight=QFont.Weight.Normal,
            ),
        }
    )


class TypographyManager:
    def __init__(self, profile: TypographyProfile) -> None:
        self.profile = profile

    def font(self, role: TypographyRole) -> QFont:
        spec = self.profile.spec(role)
        font = QFont()

        family_chain = list(spec.families)
        for family in self.profile.fallback_families:
            if family not in family_chain:
                family_chain.append(family)

        # PyQt6 exposes setFamilies on modern Qt builds. Fall back gracefully.
        try:
            font.setFamilies(family_chain)
        except AttributeError:
            font.setFamily(family_chain[0])

        font.setPointSize(spec.point_size)
        font.setWeight(spec.weight)
        font.setItalic(spec.italic)

        if spec.letter_spacing is not None:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spec.letter_spacing)

        return font

    def apply(self, widget: QWidget, role: TypographyRole) -> None:
        widget.setFont(self.font(role))

    def apply_application(self, app: QApplication | None) -> None:
        if app is None:
            return
        app.setFont(self.font(TypographyRole.APP_BASE))

