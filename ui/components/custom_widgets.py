"""
custom_widgets.py

Contains highly customized PySide6 widgets used across the MyGantt application.

Phase 3 Updates:
- Applied Qt.WA_TransparentForMouseEvents to the CheckableComboBox LineEdit.
  This allows mouse clicks to fall through to the native QComboBox, restoring
  the default toggle (click to open, click to close) behavior.
"""

from PySide6.QtWidgets import QComboBox
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem

class CheckableComboBox(QComboBox):
    """
    Custom Checkable Multi-Select Dropdown.
    Allows users to check/uncheck multiple items, and updates the display text
    to show how many items are currently selected.
    """
    selection_changed = Signal()

    def __init__(self):
        super().__init__()
        # Make it editable so we can display custom text (e.g., "3 Types Selected")
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setAlignment(Qt.AlignCenter)

        # ---> THE PERFECT UX FIX <---
        # Makes the line edit a "ghost" to the mouse. Clicks fall right through
        # to the underlying QComboBox, restoring perfect native toggle behavior!
        self.lineEdit().setAttribute(Qt.WA_TransparentForMouseEvents)

        self.model = QStandardItemModel(self)
        self.setModel(self.model)
        self.view().pressed.connect(self.handle_item_pressed)
        self.model.dataChanged.connect(self.on_data_changed)

    def handle_item_pressed(self, index):
        """Toggles the check state of the item clicked in the dropdown list."""
        item = self.model.itemFromIndex(index)
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
        else:
            item.setCheckState(Qt.Checked)

    def on_data_changed(self):
        """Fired whenever an item is checked/unchecked to update UI and emit signals."""
        self.update_text()
        self.selection_changed.emit()

    def update_text(self):
        """Updates the placeholder text based on the number of checked items."""
        checked = self.get_checked_items()
        if not checked:
            self.lineEdit().setText("No Types Selected")
        elif len(checked) == 1:
            self.lineEdit().setText(checked[0])
        else:
            self.lineEdit().setText(f"{len(checked)} Types Selected")

    def add_item(self, text, checked=False):
        """Adds a new checkable item to the dropdown list."""
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
        self.model.appendRow(item)

    def get_checked_items(self):
        """Returns a list of strings representing the currently checked items."""
        return [self.model.item(i).text() for i in range(self.model.rowCount()) if
                self.model.item(i).checkState() == Qt.Checked]