"""Payment method resolution and creation."""

from __future__ import annotations

import logging

from app.exceptions import ManualReviewRequired
from app.verification.validators import map_payment_method, normalize_text

logger = logging.getLogger("fakturama_automation")


class PaymentMethodAutomation:
    def __init__(self, fakturama) -> None:
        self.f = fakturama
        self.ui = fakturama.ui

    def ensure_available(self, extracted_name: str | None) -> str:
        if not extracted_name:
            raise ManualReviewRequired(
                reason="Payment method missing in extracted data",
                stage="Payment Method",
            )
        mapped = map_payment_method(extracted_name)
        if self._exists(mapped):
            return mapped

        logger.info("Creating payment method: %s", mapped)
        self._create(mapped)
        if not self._exists(mapped):
            raise ManualReviewRequired(
                reason=f"Payment method {mapped!r} could not be created or found",
                stage="Payment Method",
            )
        return mapped

    def _exists(self, name: str) -> bool:
        window = self.f.window
        self.ui.click_menu_path(window, ["Data", "Terms of payment"])
        dialog = self.ui.wait_for_window(".*Terms of payment.*|.*Payment.*", timeout=self.ui.timeout)
        rows = self._search_rows(dialog, name)
        self.ui.click_button(dialog, title_re="Cancel|Close")
        exact = [row for row in rows if normalize_text(name) == normalize_text(" ".join(row))]
        if len(exact) > 1:
            raise ManualReviewRequired(
                reason=f"Multiple conflicting payment methods found for {name!r}",
                stage="Payment Method",
            )
        return len(exact) == 1

    def _create(self, name: str) -> None:
        window = self.f.window
        self.ui.click_menu_path(window, ["Data", "Terms of payment"])
        dialog = self.ui.wait_for_window(".*Terms of payment.*|.*Payment.*", timeout=self.ui.timeout)
        self.ui.click_button(dialog, title_re="New|Add")
        editor = self.ui.wait_for_window(".*Terms of payment.*|.*Payment.*", timeout=self.ui.timeout)

        self._set_field(editor, "Name", name)
        self._set_field(editor, "Description", name)
        self._set_field(editor, "Cash discount", "0")
        self._set_field(editor, "Discount Days", "0")
        self._set_field(editor, "Net Days", "0")

        self.ui.click_button(editor, title_re="^Save$")
        self.ui.wait_until(lambda: editor.is_visible(), timeout=self.ui.timeout)
        self.ui.click_button(dialog, title_re="Close|Cancel")

    def _set_field(self, editor, label: str, value: str) -> None:
        control = self.ui.find_edit_near_label(editor, label)
        self.ui.set_text(control, value)

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
