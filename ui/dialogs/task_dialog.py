"""
Provides the TaskDialog UI component for creating manual side-work.
Captures user input, validates data types, and formats the payload
for database insertion.
"""

import logging
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QDateEdit, QPushButton, QMessageBox, QLabel, QFrame
)
from PySide6.QtCore import Qt, QDate

logger = logging.getLogger(__name__)


class TaskDialog(QDialog):
    """
    A modal dialog window for creating manual side-work tasks.
    Captures Project Name, Assignee, Start Date, and Estimated Days.
    """

    def __init__(self, parent: Optional[Any] = None, configured_names: Optional[List[str]] = None) -> None:
        """
        Initializes the TaskDialog.

        Args:
            parent (Optional[Any]): The parent widget (typically the main window).
            configured_names (Optional[List[str]]): A list of engineer names to populate the assignee dropdown.
        """
        super().__init__(parent)
        self.configured_names = configured_names if configured_names else []
        self.task_data: Dict[str, Any] = {}

        try:
            self.setWindowTitle("Create Manual Task")
            self.setMinimumWidth(400)
            self.setModal(True)
            self._setup_ui()
        except Exception as e:
            logger.exception(f"Error initializing TaskDialog: {e}")

    def _setup_ui(self) -> None:
        """Constructs the layouts, input widgets, and action buttons for the dialog."""
        try:
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(20, 20, 20, 20)
            main_layout.setSpacing(15)

            # Header
            header_lbl = QLabel("New Side-Work Task")
            header_lbl.setObjectName("Header")
            main_layout.addWidget(header_lbl)

            # Form Layout for Inputs
            form_layout = QFormLayout()
            form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            form_layout.setVerticalSpacing(15)

            # Project Name Input
            self.inp_project_name = QLineEdit()
            self.inp_project_name.setPlaceholderText("Enter project or task name...")
            form_layout.addRow("Project Name:", self.inp_project_name)

            # Assignee Dropdown
            self.inp_assignee = QComboBox()
            self.inp_assignee.addItem("Unassigned")

            # Sanitize, deduplicate, and enforce Title Case for UI presentation
            cased_names = sorted(list({str(name).strip().title() for name in self.configured_names if str(name).strip()}))
            self.inp_assignee.addItems(cased_names)

            form_layout.addRow("Assign To:", self.inp_assignee)

            # Start Date Input
            self.inp_start_date = QDateEdit()
            self.inp_start_date.setCalendarPopup(True)
            self.inp_start_date.setDate(QDate.currentDate())
            self.inp_start_date.setDisplayFormat("M/d/yyyy")
            form_layout.addRow("Start Date:", self.inp_start_date)

            # Estimated Days Input
            self.inp_est_days = QLineEdit()
            self.inp_est_days.setText("1")
            self.inp_est_days.setPlaceholderText("e.g. 5")
            form_layout.addRow("Est. Days:", self.inp_est_days)

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

            self.btn_save = QPushButton("Create Task")
            self.btn_save.setObjectName("PrimaryButton")
            self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_save.clicked.connect(self.validate_and_accept)

            btn_layout.addWidget(self.btn_cancel)
            btn_layout.addWidget(self.btn_save)

            main_layout.addLayout(btn_layout)

        except Exception as e:
            logger.error(f"Error setting up TaskDialog UI: {e}")

    def validate_and_accept(self) -> None:
        """
        Validates the user input. Ensure project name exists and estimated days is an integer.
        If valid, constructs the data dictionary and accepts the dialog.
        """
        try:
            project_name = self.inp_project_name.text().strip()
            if not project_name:
                QMessageBox.warning(self, "Validation Error", "Project Name cannot be empty.")
                self.inp_project_name.setFocus()
                return

            est_days_str = self.inp_est_days.text().strip()
            if not est_days_str.isdigit() or int(est_days_str) < 1:
                QMessageBox.warning(self, "Validation Error", "Estimated Days must be a positive integer.")
                self.inp_est_days.setFocus()
                return

            assignee = self.inp_assignee.currentText()
            if assignee == "Unassigned":
                assignee = ""

            start_date = self.inp_start_date.date().toString("M/d/yyyy")

            self.task_data = {
                'PROJECT NAME': project_name,
                'ASSIGNED TO': assignee,
                'EST START DATE': start_date,
                'EST DAYS': est_days_str
            }

            self.accept()

        except Exception as e:
            logger.error(f"Error validating TaskDialog input: {e}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")

    def get_task_data(self) -> Dict[str, str]:
        """
        Retrieves the validated task data payload.

        Returns:
            Dict[str, str]: A dictionary containing the captured inputs formatted for the database.
        """
        return self.task_data