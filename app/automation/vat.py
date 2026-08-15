"""VAT resolution and creation."""

from __future__ import annotations

import logging
from decimal import Decimal

from app.exceptions import ManualReviewRequired
from app.verification.validators import normalize_text, vat_name

logger = logging.getLogger("fakturama_automation")


class VatAutomation:
    def __init__(self, fakturama) -> None:
        self.f = fakturama
        self.ui = fakturama.ui

    def ensure_vat(self, percentage: Decimal) -> str:
        name = vat_name(percentage)
        if self._find_valid(name, percentage):
            return name

        logger.info("Creating VAT: %s", name)
        self._create(name, percentage)
        if not self._find_valid(name, percentage):
            raise ManualReviewRequired(
                reason=f"VAT {name} could not be created or verified",
                stage="VAT Resolution",
            )
        return name

    def _find_valid(self, name: str, percentage: Decimal) -> bool:
        window = self.f.window
        self.ui.click_menu_path(window, ["Data", "VATs"])
        dialog = self.ui.wait_for_window(".*VAT.*", timeout=self.ui.timeout)
        rows = self._search_rows(dialog, name)
        self.ui.click_button(dialog, title_re="Cancel|Close")

        matches = []
        for row in rows:
            row_text = " ".join(row)
            if normalize_text(name) in normalize_text(row_text):
                if str(percentage.normalize()) in row_text.replace(",", "."):
                    matches.append(row)
        if len(matches) > 1:
            raise ManualReviewRequired(
                reason=f"Multiple conflicting VAT records for {name}",
                stage="VAT Resolution",
            )
        return len(matches) == 1

    def _create(self, name: str, percentage: Decimal) -> None:
        window = self.f.window
        self.ui.click_menu_path(window, ["Data", "VATs"])
        dialog = self.ui.wait_for_window(".*VAT.*", timeout=self.ui.timeout)
        self.ui.click_button(dialog, title_re="New|Add")
        editor = self.ui.wait_for_window(".*VAT.*", timeout=self.ui.timeout)

        self._set_field(editor, "Name", name)
        self._set_field(editor, "Description", name)
        self._set_field(editor, "Value", str(percentage))
        self._set_combo(editor, "VAT code", "S")

        self.ui.click_button(editor, title_re="^Save$")
        self.ui.wait_until(lambda: editor.is_visible(), timeout=self.ui.timeout)
        self.ui.click_button(dialog, title_re="Close|Cancel")

    def _set_field(self, editor, label: str, value: str) -> None:
        control = self.ui.find_edit_near_label(editor, label)
        self.ui.set_text(control, value)

    def _set_combo(self, editor, label: str, value: str) -> None:
        combos = [c.wrapper_object() for c in editor.descendants(control_type="ComboBox")]
        for combo in combos:
            parent_text = " ".join(
                self.ui.get_text(t.wrapper_object())
                for t in combo.parent().descendants(control_type="Text")
            )
            if label.lower() in parent_text.lower():
                self.ui.select_combo(combo, value)
                return

    def _search_rows(self, dialog, search_text: str) -> list[list[str]]:
        try:
            search = self.ui.find_edit_near_label(dialog, "Search")
            self.ui.set_text(search, search_text)
            search.type_keys("{ENTER}", set_foreground=True)
        except Exception:  # noqa: BLE001
            pass
        tables = dialog.descendants(control_type="Table") or dialog.descendants(control_type="DataGrid")
        if not tables:
            return []
        return self.ui.read_table_rows(tables[0].wrapper_object())
