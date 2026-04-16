from PySide6.QtWidgets import QComboBox
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem

class CheckableComboBox(QComboBox):
    """Custom Checkable Multi-Select Dropdown"""
    selection_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setAlignment(Qt.AlignCenter)
        self.model = QStandardItemModel(self)
        self.setModel(self.model)
        self.view().pressed.connect(self.handle_item_pressed)
        self.model.dataChanged.connect(self.on_data_changed)

    def handle_item_pressed(self, index):
        item = self.model.itemFromIndex(index)
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
        else:
            item.setCheckState(Qt.Checked)

    def on_data_changed(self):
        self.update_text()
        self.selection_changed.emit()

    def update_text(self):
        checked = self.get_checked_items()
        if not checked:
            self.lineEdit().setText("No Types Selected")
        elif len(checked) == 1:
            self.lineEdit().setText(checked[0])
        else:
            self.lineEdit().setText(f"{len(checked)} Types Selected")

    def add_item(self, text, checked=False):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
        self.model.appendRow(item)

    def get_checked_items(self):
        return [self.model.item(i).text() for i in range(self.model.rowCount()) if
                self.model.item(i).checkState() == Qt.Checked]