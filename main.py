import sys
from PySide6.QtWidgets import QApplication

from ui.window import MyGanttWindow
from ui.styles import DARK_THEME
from data.workload_manager import WorkloadManager
from logic.controller import AppController

if __name__ == "__main__":
    print("1. Starting application...")
    app = QApplication(sys.argv)

    print("2. Applying theme...")
    # Apply the global stylesheet to the entire app
    app.setStyleSheet(DARK_THEME)

    print("3. Initializing Model...")
    # Initialize the three parts of our MVC architecture
    model = WorkloadManager()

    print("4. Initializing View (Main Window)...")
    view = MyGanttWindow()

    print("5. Initializing Controller...")
    controller = AppController(view, model)

    print("6. Showing window...")
    # Show the window and run the app
    view.show()

    print("7. Launch successful!")
    sys.exit(app.exec())