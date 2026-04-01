import pandas as pd
import io


class DataManager:
    """Handles all data processing, Pandas operations, and future database saves."""

    def parse_excel_text(self, raw_text):
        try:
            # DEBUGGING: Let's see exactly what your computer is copying
            print("--- RAW CLIPBOARD TEXT START ---")
            # Using repr() is a neat trick that reveals hidden characters like tabs (\t) and newlines (\n)
            print(repr(raw_text))
            print("--- RAW CLIPBOARD TEXT END ---")

            # StringIO turns our raw string into a readable format for Pandas
            # sep='\t' tells it to split columns by the 'Tab' character
            df = pd.read_csv(io.StringIO(raw_text), sep='\t')
            return df

        except Exception as e:
            # DEBUGGING: Let's see the exact error Pandas is throwing
            print(f"Pandas parsing error: {e}")
            return None