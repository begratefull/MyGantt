"""
custom_widgets.py

Contains highly customized PySide6 widgets used across the MyGantt application.

Phase 3 Updates:
- Applied Qt.WA_TransparentForMouseEvents to the CheckableComboBox LineEdit.
  This allows mouse clicks to fall through to the native QComboBox, restoring
  the default toggle (click to open, click to close) behavior.
"""

from typing import List
from PySide6.QtWidgets import QComboBox, QLineEdit
from PySide6.QtCore import Qt, Signal, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem

class CheckableComboBox(QComboBox):
    """
    Custom Checkable Multi-Select Dropdown.
    Allows users to check/uncheck multiple items, and updates the display text
    to show how many items are currently selected.
    """
    selection_changed = Signal()  # type: ignore

    def __init__(self) -> None:
        super().__init__()
        self.setEditable(True)

        line_edit: QLineEdit | None = self.lineEdit()
        if line_edit is not None:
            line_edit.setReadOnly(True)
            line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            line_edit.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Renamed to _model to avoid colliding with QComboBox's built-in model() method
        self._model = QStandardItemModel(self)
        self.setModel(self._model)

        view = self.view()
        if view is not None:
            view.pressed.connect(self.handle_item_pressed)

        self._model.dataChanged.connect(self.on_data_changed)

    def handle_item_pressed(self, index: QModelIndex) -> None:
        """Toggles the check state of the item clicked in the dropdown list."""
        item = self._model.itemFromIndex(index)
        if item is not None:
            if item.checkState() == Qt.CheckState.Checked:
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Checked)

    def on_data_changed(self) -> None:
        """Fired whenever an item is checked/unchecked to update UI and emit signals."""
        self.update_text()
        self.selection_changed.emit()

    def update_text(self) -> None:
        """Updates the placeholder text based on the number of checked items."""
        checked = self.get_checked_items()
        line_edit = self.lineEdit()

        if line_edit is not None:
            if not checked:
                line_edit.setText("No Types Selected")
            elif len(checked) == 1:
                line_edit.setText(checked[0])
            else:
                line_edit.setText(f"{len(checked)} Types Selected")

    def add_item(self, text: str, checked: bool = False) -> None:
        """Adds a new checkable item to the dropdown list."""
        item = QStandardItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        item.setData(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        self._model.appendRow(item)

    def get_checked_items(self) -> List[str]:
        """Returns a list of strings representing the currently checked items."""
        return [self._model.item(i).text() for i in range(self._model.rowCount()) if
                self._model.item(i).checkState() == Qt.CheckState.Checked]