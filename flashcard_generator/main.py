import sys

from PySide6.QtWidgets import QApplication

from .ui import theme
from .ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    theme.apply_app_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
