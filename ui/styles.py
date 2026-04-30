DARK_THEME = """
/* --- GLOBAL --- */
QMainWindow { background-color: #1E1E1E; }
QWidget { color: #F0F0F0; font-family: 'Segoe UI', 'Roboto', sans-serif; font-size: 12px; }

/* Status Bar */
QStatusBar { color: #AAAAAA; background-color: #1E1E1E; border-top: 1px solid #3E3E42; }

/* --- CONTAINERS (The Card & Well System) --- */
QFrame#sidebarFrame, QFrame#mainCardFrame, QFrame#Panel {
    background-color: #252526; 
    border-radius: 10px;
    border: none;
}

QFrame#TableWell {
    background-color: #191919; 
    border-radius: 10px;
    border: 1px solid #3E3E42;
}

QFrame#DashCard { 
    background-color: #1E1E20; 
    border: 1px solid #3E3E42; 
    border-radius: 8px;
}

/* --- TYPOGRAPHY --- */
QLabel#Header { font-size: 20px; font-weight: 700; color: #F0F0F0; padding-bottom: 5px; }
QLabel#SubHeader { font-size: 12px; color: #AAAAAA; font-weight: bold; }

/* APP-WIDE UNIFIED CARD TITLES */
QLabel#CardTitle { 
    font-size: 15px; 
    font-weight: 800; 
    color: #FFFFFF; 
    padding-bottom: 2px;
}

QLabel#FilterLabel { color: #AAAAAA; font-weight: bold; font-size: 12px; margin-right: 5px; }

/* Specific KPI Panel Text */
QLabel#KpiLabel { color: #AAAAAA; font-weight: bold; }
QLabel#KpiValue { color: #4DB8FF; font-weight: bold; font-size: 14px; }

/* Specific Dashboard Text */
QLabel#DashMetric { font-size: 32px; font-weight: bold; color: #FFFFFF; }
QLabel#DashTitle { color: #AAAAAA; font-weight: bold; font-size: 12px; }

/* Unified KPI Blocks (Small nested data blocks) */
QFrame#KpiBlock { background-color: #2D2D30; border-radius: 4px; }
QLabel#KpiBlockTitle { color: #AAAAAA; font-size: 10px; font-weight: bold; }
QLabel#KpiBlockValue { color: #FFFFFF; font-size: 16px; font-weight: bold; }

/* --- TABLE STYLING --- */
QTableView, QTableWidget {
    background-color: transparent;
    border: none;
    gridline-color: transparent; 
    selection-background-color: #1F6AA5;
    selection-color: white;
    outline: none;
}

/* Left-hand Gantt Info Table specific corners */
QTableWidget#LeftTable {
    border-top-left-radius: 8px; 
    border-bottom-left-radius: 8px;
}

QHeaderView::section {
    background-color: #191919;
    color: #AAAAAA;
    padding: 4px 8px;
    border: none;
    border-bottom: 1px solid #3E3E42;
    border-right: 1px solid #3E3E42; 
    font-weight: 600;
}
QHeaderView::section:last { border-right: none; }

QTableWidget::item { padding-left: 5px; min-height: 25px; border: none; border-bottom: 1px solid #3E3E42; }
QTableWidget::item:selected { background-color: #007ACC; color: #FFFFFF; }

/* --- BUTTONS --- */
QPushButton { background-color: #3E3E42; border: none; border-radius: 5px; padding: 6px 15px; color: #F0F0F0; font-weight: 600; }
QPushButton:hover { background-color: #4E4E52; }
QPushButton:pressed { background-color: #1E1E1E; }

QPushButton#PrimaryButton { background-color: #1F6AA5; border: none; color: white; }
QPushButton#PrimaryButton:hover { background-color: #144870; }

QPushButton#NavButton { background-color: transparent; border: none; border-radius: 8px; text-align: left; padding-left: 10px; }
QPushButton#NavButton:hover { background-color: #3E3E42; }

/* ---> Active Navigation Highlight <--- */
QPushButton#NavButton:checked { 
    background-color: #007ACC; 
    border-radius: 4px; 
    border-left: 4px solid #4DB8FF; 
}

/* --- INPUTS & DROPDOWNS --- */
QLineEdit { background-color: #191919; border: 1px solid #3E3E42; border-radius: 4px; padding: 6px 10px; color: #F0F0F0; selection-background-color: #1F6AA5; }
QLineEdit:focus { border: 1px solid #1F6AA5; background-color: #252526; }

QComboBox { background-color: #252526; color: white; border: 1px solid #3E3E42; padding: 4px 10px; border-radius: 4px; min-width: 120px; }
QComboBox::drop-down { border: none; }
QComboBox::down-arrow { image: none; border-left: 1px solid #3E3E42; }
QComboBox QAbstractItemView { background-color: #1E1E1E; color: white; selection-background-color: #007ACC; border: 1px solid #3E3E42; }

/* --- SCROLLBARS --- */
QScrollBar:vertical { border: none; background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #4E4E52; min-height: 18px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #AAAAAA; }

QScrollBar:horizontal { border: none; background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #4E4E52; min-width: 18px; border-radius: 4px; }
QScrollBar::handle:horizontal:hover { background: #AAAAAA; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { height: 0px; width: 0px; background: none; }

/* --- GANTT SPECIFIC --- */
QSplitter::handle { background: #3E3E42; width: 1px; }
QGraphicsView { background: transparent; border: none; }
QGraphicsView#HeaderView { border-bottom: 1px solid #3E3E42; border-top-right-radius: 8px; }
QGraphicsView#CanvasView { border-bottom-right-radius: 8px; }

/* --- COMPONENTS & WIDGETS --- */
QChartView { background: transparent; border: none; }
QFrame#SeparatorLine { background-color: #3E3E42; }

/* --- MENUS --- */
QMenu { background-color: #252526; color: white; border: 1px solid #3E3E42; }
QMenu::item:selected { background-color: #007ACC; }
"""