from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget, QAbstractItemView, \
    QPushButton


class DataViewWidget(QWidget):
    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header_lbl = QLabel("Raw Synced Excel Data")
        header_lbl.setObjectName("Header")
        main_layout.addWidget(header_lbl)

        self.raw_table_well = QFrame()
        self.raw_table_well.setObjectName("TableWell")
        raw_well_layout = QVBoxLayout(self.raw_table_well)
        raw_well_layout.setContentsMargins(2, 2, 2, 2)

        self.raw_table = QTableWidget()
        self.raw_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.raw_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.raw_table.setShowGrid(False)
        self.raw_table.verticalHeader().setVisible(False)

        raw_well_layout.addWidget(self.raw_table)
        main_layout.addWidget(self.raw_table_well)

        bottom_bar_data = QHBoxLayout()
        self.sync_btn = QPushButton("Sync Workload")
        self.sync_btn.setObjectName("PrimaryButton")
        bottom_bar_data.addWidget(self.sync_btn)
        bottom_bar_data.addStretch()
        main_layout.addLayout(bottom_bar_data)