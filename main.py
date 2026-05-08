import sys
import ctypes
import logging
from PySide6.QtWidgets import QApplication

from ui.window import MyGanttWindow
from ui.styles import DARK_THEME
from data.workload_manager import WorkloadManager
from logic.controller import AppController
from logic.logger import UIQTextLogHandler

# Force Windows to show your app icon in the taskbar instead of the Python logo
myappid = 'mycompany.mygantt.app.1.0.0'  # Arbitrary string
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


def setup_global_logger(ui_view):
    """Configures application-wide logging and attaches the UI handler."""
    logger = logging.getLogger()  # Get the root logger
    logger.setLevel(logging.INFO)

    # Standard formatter for the logs
    formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%H:%M:%S')

    # 1. Console Handler (Standard Output for PyCharm terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File Handler (Saves to a text file for historical debug)
    file_handler = logging.FileHandler("mygantt_debug.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 3. Custom UI Handler (Sends logs to the in-app console)
    ui_handler = UIQTextLogHandler()
    ui_handler.setFormatter(formatter)

    # Connect the signal from the handler to the View's method
    ui_handler.signaller.log_signal.connect(ui_view.append_log_message)
    logger.addHandler(ui_handler)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME)

    # Instantiate the View FIRST so we can pass it to the logger setup
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