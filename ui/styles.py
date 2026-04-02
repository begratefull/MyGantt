# styles.py

DARK_THEME = """
/* --- GLOBAL --- */
QMainWindow { background-color: #1E1E1E; }
QWidget { color: #F0F0F0; font-family: 'Segoe UI', 'Roboto', sans-serif; font-size: 12px; }

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

/* --- TYPOGRAPHY --- */
QLabel#Header { font-size: 20px; font-weight: 700; color: #F0F0F0; padding-bottom: 5px; }
QLabel#SubHeader { font-size: 11px; color: #AAAAAA; }

/* --- TABLE STYLING (No Grids, Custom Headers) --- */
QTableView, QTableWidget {
    background-color: transparent;
    border: none;
    gridline-color: transparent; 
    selection-background-color: #1F6AA5;
    selection-color: white;
    outline: none;
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

QTableWidget::item {
    padding-left: 5px;
    min-height: 25px; 
    border: none; 
    border-bottom: 1px solid #3E3E42; 
}
QTableWidget::item:selected { 
    background-color: #1F6AA5;
    color: #FFFFFF; 
}

/* --- BUTTONS --- */
QPushButton {
    background-color: #3E3E42;
    border: none; 
    border-radius: 5px; padding: 6px 15px;
    color: #F0F0F0; font-weight: 600;
}
QPushButton:hover { background-color: #4E4E52; }
QPushButton:pressed { background-color: #1E1E1E; }

QPushButton#PrimaryButton { background-color: #1F6AA5; border: none; color: white; }
QPushButton#PrimaryButton:hover { background-color: #144870; }

/* Slim Tray Icon Buttons (Using Image Assets) */
QPushButton#NavButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
}
QPushButton#NavButton:hover { 
    background-color: #3E3E42; 
}

/* --- INPUTS --- */
QLineEdit {
    background-color: #191919;
    border: 1px solid #3E3E42;
    border-radius: 4px; padding: 6px 10px;
    color: #F0F0F0;
    selection-background-color: #1F6AA5;
}
QLineEdit:focus { border: 1px solid #1F6AA5; background-color: #252526; }

/* --- SCROLLBARS --- */
/* Vertical */
QScrollBar:vertical { 
    border: none; 
    background: transparent; 
    width: 12px; /* Increased from 10px */
    margin: 2px; 
}
QScrollBar::handle:vertical { 
    background: #4E4E52; 
    min-height: 18px; /* Make the grab-handle slightly longer */
    border-radius: 4px; /* Round out the thicker bar */
}
QScrollBar::handle:vertical:hover { background: #AAAAAA; }

/* Horizontal */
QScrollBar:horizontal { 
    border: none; 
    background: transparent; 
    height: 12px; /* Increased from 10px */
    margin: 2px; 
}
QScrollBar::handle:horizontal { 
    background: #4E4E52; 
    min-width: 18px; /* Make the grab-handle slightly longer */
    border-radius: 4px; 
}
QScrollBar::handle:horizontal:hover { background: #AAAAAA; }

/* Hide the little arrow buttons at the ends */
QScrollBar::add-line, QScrollBar::sub-line { height: 0px; width: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""