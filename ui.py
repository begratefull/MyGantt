from PySide6.QtWidgets import (QMainWindow, QPushButton, QTableWidget,
                               QVBoxLayout, QWidget, QMessageBox, QTableWidgetItem)


class MyGanttWindow(QMainWindow):
    """Handles all the visual elements of the application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyGantt")
        self.resize(800, 600)

        # Set up the layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create our widgets
        self.paste_btn = QPushButton("Paste from Excel")
        layout.addWidget(self.paste_btn)

        self.table = QTableWidget()
        layout.addWidget(self.table)

    def display_dataframe(self, df):
        """Takes a Pandas DataFrame and draws it into the UI table."""
        self.table.setRowCount(df.shape[0])
        self.table.setColumnCount(df.shape[1])
        self.table.setHorizontalHeaderLabels(df.columns.astype(str))

        for row in range(df.shape[0]):
            for col in range(df.shape[1]):
                cell_value = str(df.iat[row, col])
                item = QTableWidgetItem(cell_value)
                self.table.setItem(row, col, item)

    def show_warning(self, title, message):
        """Pops up a warning box for the user."""
        QMessageBox.warning(self, title, message)