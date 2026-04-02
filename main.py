import sys
from PySide6.QtWidgets import QApplication

# Updated imports pulling from our new folder structure!
from ui.window import MyGanttWindow
from ui.styles import DARK_THEME
from data.manager import DataManager
from logic.controller import AppController

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Apply the global stylesheet to the entire app
    app.setStyleSheet(DARK_THEME)

    # Initialize the three parts of our MVC architecture
    model = DataManager()
    view = MyGanttWindow()
    controller = AppController(view, model)

    # Show the window and run the app
    view.show()
    sys.exit(app.exec())