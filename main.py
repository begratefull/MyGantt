import sys
import os
import ctypes
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from ui.window import MyGanttWindow
from ui.styles import DARK_THEME
from data.workload_manager import WorkloadManager
from logic.controller import AppController
from logic.logger import UIQTextLogHandler

# Force Windows to show your app icon in the taskbar instead of the Python logo
myappid = 'legrand.mygantt.app.1.0.0'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def setup_global_logger(ui_view):
    """Configures application-wide logging and attaches the UI handler."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%H:%M:%S')

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler("mygantt_debug.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    ui_handler = UIQTextLogHandler()
    ui_handler.setFormatter(formatter)

    ui_handler.signaller.log_signal.connect(ui_view.append_log_message)
    logger.addHandler(ui_handler)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME)

    # Use the native Windows .ico file for the application level icon
    icon_path = get_resource_path(os.path.join("ui", "resources", "app_icon.ico"))
    app.setWindowIcon(QIcon(icon_path))

    view = MyGanttWindow()
    setup_global_logger(view)

    logging.info("=========================================")
    logging.info("Starting MyGantt Application...")

    logging.info("Initializing Data Model...")
    model = WorkloadManager()

    logging.info("Initializing Application Controller...")
    controller = AppController(view, model)

    logging.info("Displaying Main Window...")
    view.showMaximized()

    logging.info("Launch sequence complete!")
    sys.exit(app.exec())