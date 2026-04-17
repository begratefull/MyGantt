import hashlib
import os
import re
import shutil
import logging
import pandas as pd


class ExcelParser:
    def __init__(self):
        self.raw_header_mapping = {
            "ORDERNUMBER": "ORDER NUMBER",
            "LINEITEM": "LINE ITEM",
            "PRIORITY": "PRIORITY",
            "DATETOENG": "DATE TO ENG",
            "SHIPTONUMBERPROJECT": "PROJECT NAME",
            "INTERGRATIONREFERENCENUMBERQUOTE": "QUOTE NO",
            "INTEGRATIONREFERENCENUMBERQUOTE": "QUOTE NO",
            "SALESCONTACT": "SALES CONTACT",
            "TYPE": "TYPE",
            "CONFIGUREDSTRINGLUMINARIESPECIFICATION": "LUMINARIE SPECIFICATION",
            "SELL": "SELL $",
            "ASSIGNEDTO": "RAW_ASSIGNED",
            "ENGSTARTDATE": "RAW_START_DATE",
            "DUEDATE": "ENG DUE DATE",
            "COMPLETEDATE": "COMPLETE DATE",
            "SHIPDATE": "ESD",
            "REQUIREMENT": "REQUIREMENT",
            "REQUIRMENT": "REQUIREMENT",
            "STATUS": "STATUS"
        }
        self.unique_expected_cols = list(dict.fromkeys(self.raw_header_mapping.values()))

    @staticmethod
    def _generate_smart_id(row):
        order = str(row.get('ORDER NUMBER', '')).strip()
        quote = str(row.get('QUOTE NO', '')).strip()
        line = str(row.get('LINE ITEM', '')).strip()

        if order and order.upper() not in ['NAN', '']:
            base = order
        elif quote and quote.upper() not in ['NAN', '']:
            base = quote
        else:
            project = str(row.get('PROJECT NAME', '')).strip()
            req = str(row.get('REQUIREMENT', '')).strip()
            short_hash = hashlib.md5(f"{project}-{req}".encode('utf-8')).hexdigest()[:6].upper()
            base = f"UNK-{short_hash}"

        if line and line.upper() not in ['NAN', '']:
            return f"{base}-{line}"
        return base

    @staticmethod
    def _format_date(value):
        if pd.isna(value) or str(value).strip() in ["", "nan"]: return ""
        try:
            dt = pd.to_datetime(value)
            return f"{dt.month}/{dt.day}/{dt.year}"
        except Exception:
            return str(value)

    def parse_file(self, file_path: str):
        """
        Reads the Excel file, cleans the data, maps headers, and generates SMART_IDs.
        Returns a tuple: (DataFrame or None, Error Message)
        """
        temp_path = "temp_sync_shadow.xlsx"
        try:
            if not os.path.exists(file_path):
                return None, f"Could not find the synced file at:\n{file_path}"

            shutil.copy2(file_path, temp_path)

            df = pd.read_excel(temp_path, sheet_name='ENG WORKLOAD MASTER 2026', header=None, engine='openpyxl')

            def clean_cell(val):
                if pd.isna(val): return ""
                if isinstance(val, float) and val.is_integer(): return str(int(val))
                return str(val).strip()

            for col in list(df.columns):
                df[col] = df[col].map(clean_cell)

            header_idx = -1
            for idx, row in df.head(50).iterrows():
                if "ORDER NUMBER" in [str(cell).upper() for cell in row]:
                    header_idx = idx
                    break

            if header_idx == -1:
                return None, "Could not find 'ORDER NUMBER' header row."

            df.columns = [str(c).strip() for c in df.iloc[header_idx]]
            df = df.iloc[header_idx + 1:].reset_index(drop=True)

            rename_dict = {}
            for actual_col in list(df.columns):
                norm_col = re.sub(r'[\W_]+', '', str(actual_col).upper())
                if norm_col in self.raw_header_mapping:
                    rename_dict[actual_col] = self.raw_header_mapping[norm_col]

            df = df.rename(columns=rename_dict)

            end_idx = -1
            for idx, row in df.iterrows():
                if "END OF LINE" in [str(cell).upper() for cell in row]:
                    end_idx = idx
                    break
            if end_idx != -1:
                df = df.iloc[:end_idx]

            # --- NEW: Strip Empty Rows ---
            # If the row has no Order Number, no Quote Number, AND no Project Name, it's considered empty junk.
            if all(c in df.columns for c in ["ORDER NUMBER", "QUOTE NO", "PROJECT NAME"]):
                mask = (df['ORDER NUMBER'] != "") | (df['QUOTE NO'] != "") | (df['PROJECT NAME'] != "")
                df = df[mask].reset_index(drop=True)

            columns_to_keep = [c for c in df.columns if c in self.unique_expected_cols]
            df = df[columns_to_keep]

            df['SMART_ID'] = df.apply(self._generate_smart_id, axis=1)
            counts = df.groupby('SMART_ID').cumcount()
            df['SMART_ID'] = df['SMART_ID'] + counts.apply(lambda x: f"_{x}" if x > 0 else "")

            for col in ["DATE TO ENG", "RAW_START_DATE", "ENG DUE DATE", "COMPLETE DATE", "ESD"]:
                if col in df.columns:
                    df[col] = df[col].apply(self._format_date)

            for expected_col in self.unique_expected_cols:
                if expected_col not in df.columns:
                    df[expected_col] = ""

            final_cols = ["SMART_ID"] + self.unique_expected_cols
            df = df[final_cols]

            return df, ""

        except Exception as e:
            import traceback
            logging.error(f"Error parsing Excel: {str(e)}\n\nTraceback:\n{traceback.format_exc()}")
            return None, "Sync failed! Check error log."
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass