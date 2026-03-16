import sys

from PyQt6.QtWidgets import QApplication

from rotorlab_app.ui.main_window import RotorLabMainWindow
from rotorlab_app.ui.typography import TypographyManager, default_typography_profile


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("RotorLab")

    typography_profile = default_typography_profile()
    typography = TypographyManager(typography_profile)
    typography.apply_application(app)

    window = RotorLabMainWindow(typography_profile=typography_profile)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
