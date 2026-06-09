"""
Manages the application's Undo/Redo state and tracks staged edits
before they are committed to the SQLite database and Excel file.
"""

import copy
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class HistoryManager:
    """
    Maintains stacks of the user's unsaved actions, allowing for
    Ctrl+Z / Ctrl+Y functionality across both single and bulk interactions.
    """

    def __init__(self) -> None:
        self.undo_stack: List[Dict[str, Dict[str, Any]]] = []
        self.redo_stack: List[Dict[str, Dict[str, Any]]] = []

        # Format: { 'SMART_ID': {'MAN_ASSIGNED': 'Adam', 'MAN_EST_DAYS': '4'} }
        self.current_staged_edits: Dict[str, Dict[str, Any]] = {}

    def stage_edit(self, smart_id: str, edit_dict: Dict[str, Any]) -> None:
        """Records a single change and pushes the previous state to the undo stack."""
        try:
            self.undo_stack.append(copy.deepcopy(self.current_staged_edits))
            self.redo_stack.clear()

            if smart_id not in self.current_staged_edits:
                self.current_staged_edits[smart_id] = {}

            self.current_staged_edits[smart_id].update(edit_dict)
        except Exception as e:
            logger.error(f"Error staging edit for {smart_id}: {e}")

    def stage_bulk_edits(self, bulk_edits: Dict[str, Dict[str, Any]]) -> None:
        """
        Records multiple changes as a single undoable action.
        Format: { 'ID_1': {'MAN_ASSIGNED': 'Adam'}, 'ID_2': {'MAN_ASSIGNED': 'Adam'} }
        """
        try:
            self.undo_stack.append(copy.deepcopy(self.current_staged_edits))
            self.redo_stack.clear()

            for smart_id, edit_dict in bulk_edits.items():
                if smart_id not in self.current_staged_edits:
                    self.current_staged_edits[smart_id] = {}
                self.current_staged_edits[smart_id].update(edit_dict)
        except Exception as e:
            logger.error(f"Error staging bulk edits: {e}")

    def undo(self) -> bool:
        """Reverts the current state to the last action in the undo stack."""
        try:
            if not self.undo_stack:
                return False

            self.redo_stack.append(copy.deepcopy(self.current_staged_edits))
            self.current_staged_edits = self.undo_stack.pop()
            return True
        except Exception as e:
            logger.error(f"Error executing undo: {e}")
            return False

    def redo(self) -> bool:
        """Reapplies a previously undone state."""
        try:
            if not self.redo_stack:
                return False

            self.undo_stack.append(copy.deepcopy(self.current_staged_edits))
            self.current_staged_edits = self.redo_stack.pop()
            return True
        except Exception as e:
            logger.error(f"Error executing redo: {e}")
            return False

    def get_staged_edits(self) -> Dict[str, Dict[str, Any]]:
        """Returns the dictionary of unsaved changes."""
        return self.current_staged_edits

    def clear(self) -> None:
        """Wipes all history. Called after a successful global Save."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.current_staged_edits.clear()

    def has_changes(self) -> bool:
        """
        Checks if there are any unsaved changes currently staged.
        """
        return len(self.current_staged_edits) > 0