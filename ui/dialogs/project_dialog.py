"""
Provides the ProjectDialog UI component for creating manual project containers.
Captures user input, validates data, and formats the payload for database insertion.
"""

import logging
from typing import Any, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPlainTextEdit, QPushButton, QMessageBox, QLabel, QFrame
)
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


class ProjectDialog(QDialog):
    """
    A modal dialog window for creating manual project containers.
    Captures Project Name and Project Description.
    """

    def __init__(self, parent: Optional[Any] = None) -> None:
        """
        Initializes the ProjectDialog.

        Args:
            parent (Optional[Any]): The parent widget (typically the main window).
        """
        super().__init__(parent)
        self.project_data: dict[str, Any] = {}

        try:
            self.setWindowTitle("Create Manual Project")
            self.setMinimumWidth(400)
            self.setModal(True)
            self._setup_ui()
        except Exception as e:
            logger.exception(f"Error initializing ProjectDialog: {e}")

    def _setup_ui(self) -> None:
        """Constructs the layouts, input widgets, and action buttons for the dialog."""
        try:
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(20, 20, 20, 20)
            main_layout.setSpacing(15)

            # Header
            header_lbl = QLabel("New Project")
            header_lbl.setObjectName("Header")
            main_layout.addWidget(header_lbl)

            # Form Layout for Inputs
            form_layout = QFormLayout()
            form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            form_layout.setVerticalSpacing(15)

            # Project Name Input
            self.inp_project_name = QLineEdit()
            self.inp_project_name.setPlaceholderText("Enter project name...")
            form_layout.addRow("Project Name:", self.inp_project_name)

            # Project Description Input
            self.inp_description = QPlainTextEdit()
            self.inp_description.setPlaceholderText("Enter project description (optional)...")
            self.inp_description.setMaximumHeight(80)
            form_layout.addRow("Description:", self.inp_description)

            main_layout.addLayout(form_layout)

            # Separator
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setObjectName("SeparatorLine")
            main_layout.addWidget(line)

            # Action Buttons
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            self.btn_cancel = QPushButton("Cancel")
            self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_cancel.clicked.connect(self.reject)

            self.btn_save = QPushButton("Create Project")
            self.btn_save.setObjectName("PrimaryButton")
            self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_save.clicked.connect(self.validate_and_accept)

            btn_layout.addWidget(self.btn_cancel)
            btn_layout.addWidget(self.btn_save)

            main_layout.addLayout(btn_layout)

        except Exception as e:
            logger.error(f"Error setting up ProjectDialog UI: {e}")

    def validate_and_accept(self) -> None:
        """
        Validates the user input. Ensures project name exists.
        If valid, constructs the data dictionary and accepts the dialog.
        """
        try:
            project_name = self.inp_project_name.text().strip()
            if not project_name:
                QMessageBox.warning(self, "Validation Error", "Project Name cannot be empty.")
                self.inp_project_name.setFocus()
                return

            description = self.inp_description.toPlainText().strip()

            self.project_data = {
                'PROJECT_NAME': project_name,
                'DESCRIPTION': description
            }

            self.accept()

        except Exception as e:
            logger.error(f"Error validating ProjectDialog input: {e}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")

    def get_project_data(self) -> dict[str, str]:
        """
        Retrieves the validated project data payload.

        Returns:
            dict[str, str]: A dictionary containing the captured inputs formatted for the database.
        """
        return self.project_data