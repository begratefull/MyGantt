import sqlite3
import pandas as pd
import os


def run_backfill():
    # 1. Connect to your database
    db_path = os.path.join("data", "gantt_data.db")
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ==========================================
    # NEW FIX: Add the missing columns dynamically
    # ==========================================
    print("Checking database schema...")
    new_columns = ["EST ESD VARIANCE", "EST ENG VARIANCE", "COMPLETION VARIANCE"]
    for col in new_columns:
        try:
            cursor.execute(f'ALTER TABLE my_planning_data ADD COLUMN "{col}" TEXT')
            print(f"Added missing column: {col}")
        except sqlite3.OperationalError:
            # If the column already exists, SQLite throws an error, which we safely ignore!
            pass
    # ==========================================

    # 2. Get all COMPLETE jobs
    query = '''
        SELECT p."SMART_ID", r."ESD", r."ENG DUE DATE", r."COMPLETE DATE"
        FROM my_planning_data p
        JOIN raw_workload r ON p."SMART_ID" = r."SMART_ID"
        WHERE r."STATUS" = 'COMPLETE' OR r."COMPLETE DATE" != ''
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    # 3. Variance Logic (Target Date - Actual Date)
    # 3. Variance Logic (Target Date - Actual Date in Working Days)
    def calc_var(actual_date, target_date):
        try:
            if not actual_date or not target_date:
                return ""
            end_dt = pd.to_datetime(actual_date)
            target_dt = pd.to_datetime(target_date)

            if target_dt >= end_dt:
                # Early or on-time (Positive)
                delta = len(pd.bdate_range(end_dt, target_dt)) - 1
            else:
                # Late (Negative)
                delta = -(len(pd.bdate_range(target_dt, end_dt)) - 1)

            return f"{delta} days"
        except:
            return ""

    updated_count = 0

    # 4. Process and update each row
    for smart_id, esd, eng_due, complete in rows:
        if not complete:
            continue

        esd_var = calc_var(complete, esd)
        eng_var = calc_var(complete, eng_due)
        comp_var = eng_var

        cursor.execute('''
            UPDATE my_planning_data
            SET "EST ESD VARIANCE" = ?, "EST ENG VARIANCE" = ?, "COMPLETION VARIANCE" = ?
            WHERE "SMART_ID" = ?
        ''', (esd_var, eng_var, comp_var, smart_id))

        updated_count += 1

    conn.commit()
    conn.close()
    print(f"Success! Backfilled historical variances for {updated_count} completed jobs.")


if __name__ == "__main__":
    run_backfill()