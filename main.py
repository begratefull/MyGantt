import sys
from PySide6.QtWidgets import QApplication

# Import our custom classes
from ui import MyGanttWindow
from data import DataManager
from logic import AppController

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Initialize the three parts of our MVC architecture
    model = DataManager()
    view = MyGanttWindow()
    controller = AppController(view, model)

    # Show the window and run the app
    view.show()
    sys.exit(app.exec())