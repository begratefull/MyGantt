# logic/logger.py
import logging
from PySide6.QtCore import QObject, Signal

class Signaller(QObject):
    """A simple QObject to hold a signal for thread-safe UI updates."""
    log_signal = Signal(str)

class UIQTextLogHandler(logging.Handler):
    """
    A custom logging handler that intercepts standard Python logs
    and emits them via a PySide6 Signal so they can be safely
    appended to the UI console from any background thread.
    """
    def __init__(self):
        super().__init__()
        self.signaller = Signaller()

    def emit(self, record):
        # Format the log message based on the logger's configuration
        msg = self.format(record)
        # Emit the message through the signal safely to the UI thread
        self.signaller.log_signal.emit(msg)