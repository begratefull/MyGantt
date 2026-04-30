import sys
import ctypes
from PySide6.QtWidgets import QApplication

from ui.window import MyGanttWindow
from ui.styles import DARK_THEME
from data.workload_manager import WorkloadManager
from logic.controller import AppController

# Force Windows to show your app icon in the taskbar instead of the Python logo
myappid = 'mycompany.mygantt.app.1.0.0' # Arbitrary string
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

if __name__ == "__main__":
    print("1. Starting application...")
    app = QApplication(sys.argv)

    print("2. Applying theme...")
    app.setStyleSheet(DARK_THEME)

    print("3. Initializing Model...")
    model = WorkloadManager()

    print("4. Initializing View (Main Window)...")
    view = MyGanttWindow()

    print("5. Initializing Controller...")
    controller = AppController(view, model)

    print("6. Showing window...")
    view.showMaximized()

    print("7. Launch successful!")
    sys.exit(app.exec())