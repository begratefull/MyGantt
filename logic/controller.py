from PySide6.QtGui import QGuiApplication


class AppController:
    def __init__(self, view, model):
        self.view = view
        self.model = model

        self.excel_path = r"C:\Users\fgibil1a\OneDrive - Legrand France\Development\Engineering Workload_Data\Engineering_Workload_Sync.xlsx"

        self.refresh_tables()

        self.view.sync_btn.clicked.connect(self.handle_sync)
        # UPDATED: Now connects to the new Backlog table
        self.view.backlog_table.itemSelectionChanged.connect(self.handle_row_selection)
        self.view.save_edit_btn.clicked.connect(self.handle_save_edit)

    def refresh_tables(self):
        raw_df = self.model.get_raw_data()
        plan_df = self.model.get_planning_data()

        self.view.display_dataframe(self.view.raw_table, raw_df)

        # UPDATED: Paint the backlog table instead of the old plan table
        if not plan_df.empty:
            # For now, just show everything in the backlog. We will filter this later!
            self.view.display_dataframe(self.view.backlog_table, plan_df)
            self.view.backlog_table.setColumnHidden(0, True)  # Hide SMART_ID

    def handle_sync(self):
        self.view.sync_btn.setText("Syncing Data...")
        self.view.sync_btn.setEnabled(False)
        QGuiApplication.processEvents()

        success, error_msg = self.model.sync_from_excel(self.excel_path)

        if not success:
            self.view.show_warning("Sync Error", f"Could not sync data:\n\n{error_msg}")
        else:
            self.refresh_tables()

        self.view.sync_btn.setText("Sync Workload")
        self.view.sync_btn.setEnabled(True)

    def handle_row_selection(self):
        selected_rows = self.view.backlog_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()

        smart_id = self.view.backlog_table.item(row, 0).text()
        project = self.view.backlog_table.item(row, 4).text()

        assignee = self.view.backlog_table.item(row, 6).text()
        est_days = self.view.backlog_table.item(row, 8).text()

        # Grab the KPI data
        eng_due = self.view.backlog_table.item(row, 11).text()
        esd = self.view.backlog_table.item(row, 10).text()
        eng_var = self.view.backlog_table.item(row, 14).text()
        esd_var = self.view.backlog_table.item(row, 13).text()

        # Populate the Inspector Panel
        self.view.inp_smart_id.setText(smart_id)
        self.view.kpi_title.setText(f"Job: {project[:15]}...")

        self.view.inp_assignee.setText(assignee)
        self.view.inp_est_days.setText(est_days)

        self.view.kpi_due_date.setText(eng_due if eng_due else "--")
        self.view.kpi_esd.setText(esd if esd else "--")
        self.view.kpi_eng_var.setText(eng_var if eng_var else "--")
        self.view.kpi_esd_var.setText(esd_var if esd_var else "--")

    def handle_save_edit(self):
        smart_id = self.view.inp_smart_id.text()
        assignee = self.view.inp_assignee.text()
        est_days = self.view.inp_est_days.text()

        # We don't have a start date input anymore (that will come from dragging the Gantt block!)
        # So we just pass whatever was already in the database for start_date to avoid overwriting it
        current_start_date = ""
        df = self.model.get_planning_data()
        if not df.empty:
            match = df[df['SMART_ID'] == smart_id]
            if not match.empty:
                current_start_date = match.iloc[0]['EST START DATE']

        self.model.update_job_details(smart_id, assignee, est_days, current_start_date)
        self.refresh_tables()