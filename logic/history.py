import copy


class HistoryManager:
    def __init__(self):
        # Stacks to keep track of state over time
        self.undo_stack = []
        self.redo_stack = []

        # The current active pool of unsaved changes
        # Format: { 'SMART_ID': {'MAN_ASSIGNED': 'Adam', 'MAN_EST_DAYS': '4', ...} }
        self.current_staged_edits = {}

    def stage_edit(self, smart_id: str, edit_dict: dict):
        """
        Records a new change. Pushes the current state to the undo stack.
        """
        # 1. Save a deep copy of the current state to the undo stack BEFORE changing it
        self.undo_stack.append(copy.deepcopy(self.current_staged_edits))

        # 2. Clear the redo stack (any new action invalidates the "future")
        self.redo_stack.clear()

        # 3. Apply the new edits to our current staged state
        if smart_id not in self.current_staged_edits:
            self.current_staged_edits[smart_id] = {}

        self.current_staged_edits[smart_id].update(edit_dict)

    def stage_bulk_edits(self, bulk_edits: dict):
        """
        Records multiple changes as a single undo-able action.
        Format: { 'SMART_ID_1': {'MAN_START_DATE': '...'}, 'SMART_ID_2': {'MAN_START_DATE': '...'} }
        """
        self.undo_stack.append(copy.deepcopy(self.current_staged_edits))
        self.redo_stack.clear()

        for smart_id, edit_dict in bulk_edits.items():
            if smart_id not in self.current_staged_edits:
                self.current_staged_edits[smart_id] = {}
            self.current_staged_edits[smart_id].update(edit_dict)

    def undo(self) -> bool:
        """
        Reverts to the previous state. Returns True if successful.
        """
        if not self.undo_stack:
            return False  # Nothing to undo

        # Push the current state to the redo stack so we don't lose it
        self.redo_stack.append(copy.deepcopy(self.current_staged_edits))

        # Pop the last state from the undo stack and make it current
        self.current_staged_edits = self.undo_stack.pop()
        return True

    def redo(self) -> bool:
        """
        Reapplies a previously undone state. Returns True if successful.
        """
        if not self.redo_stack:
            return False  # Nothing to redo

        # Push the current state to the undo stack so we can undo the redo!
        self.undo_stack.append(copy.deepcopy(self.current_staged_edits))

        # Pop the next state from the redo stack and make it current
        self.current_staged_edits = self.redo_stack.pop()
        return True

    def get_staged_edits(self) -> dict:
        """
        Returns the current dictionary of unsaved changes to feed into the DataManager.
        """
        return self.current_staged_edits

    def clear(self):
        """
        Wipes all history. Called after a successful Save.
        """
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.current_staged_edits.clear()

    def has_changes(self) -> bool:
        """
        Checks if there are any unsaved changes currently staged.
        """
        return len(self.current_staged_edits) > 0