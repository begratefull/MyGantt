from PySide6.QtGui import QGuiApplication


class AppController:
    """Bridges the gap between the UI and the Data."""

    def __init__(self, view, model):
        self.view = view
        self.model = model

        # Connect the UI button to our logic function
        self.view.paste_btn.clicked.connect(self.handle_paste)

    def handle_paste(self):
        # 1. Grab the raw text directly from the operating system's clipboard
        clipboard = QGuiApplication.clipboard()
        raw_text = clipboard.text()

        # Check if the clipboard actually has text
        if not raw_text.strip():
            self.view.show_warning("Warning", "Clipboard is empty or doesn't contain text!")
            return

        # 2. Hand the text to our DataManager to turn into a Pandas DataFrame
        df = self.model.parse_excel_text(raw_text)

        # 3. Check if Pandas successfully parsed it, then tell the UI to display it
        if df is None or df.empty:
            self.view.show_warning("Warning", "Could not format the copied data.")
            return

        self.view.display_dataframe(df)