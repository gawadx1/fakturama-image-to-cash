"""Order editor automation."""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from pywinauto.base_wrapper import BaseWrapper

from app.automation.ui_helpers import UIHelpers
from app.exceptions import ManualReviewRequired
from app.models.order import OrderData, OrderItem
from app.verification.validators import validate_order_totals

logger = logging.getLogger("fakturama_automation")


class OrderAutomation:
    def __init__(self, fakturama) -> None:
        self.f = fakturama
        self.ui: UIHelpers = fakturama.ui

    def open_new_order(self, order: OrderData) -> BaseWrapper:
        window = self.f.window
        try:
            self.ui.click_menu_path(window, ["Order", "New order"])
        except Exception:
            self.ui.click_button(window, title_re="New order|New Order")

        editor = self.ui.wait_for_window(".*Order.*", timeout=self.ui.timeout)
        self._set_field(editor, "Date", self._format_date(order.order_date))
        if order.external_reference:
            self._set_field(editor, "Cust.Ref.", order.external_reference)
        self._set_combo(editor, "Price", "Net")
        self._set_combo(editor, "VAT", "With VAT")
        return editor

    def _set_field(self, editor: BaseWrapper, label: str, value: str) -> None:
        if not value:
            return
        control = self.ui.find_edit_near_label(editor, label)
        self.ui.set_text(control, value)

    def _set_combo(self, editor: BaseWrapper, label: str, value: str) -> None:
        combos = [
            c.wrapper_object()
            for c in editor.descendants(control_type="ComboBox")
            if c.is_visible()
        ]
        if not combos:
            return
        for combo in combos:
            parent_text = " ".join(
                self.ui.get_text(t.wrapper_object())
                for t in combo.parent().descendants(control_type="Text")
            )
            if label.lower() in parent_text.lower():
                self.ui.select_combo(combo, value)
                return
        self.ui.select_combo(combos[0], value)

    def _format_date(self, value) -> str:
        if value is None:
            return ""
        return value.strftime("%d.%m.%Y")

    def complete_order(self, order: OrderData, editor: BaseWrapper) -> None:
        validate_order_totals(order)
        for item in order.items:
            self._complete_line_item(editor, item)
        self._set_field(editor, "Discount", "0")
        if order.shipping_cost is None:
            self._set_combo(editor, "Shipping", "Free of shipping costs")

    def _complete_line_item(self, editor: BaseWrapper, item: OrderItem) -> None:
        self.f.products.select_product_on_order(editor, item.sku)
        self._set_line_value(editor, "Qty", str(item.quantity))
        self._set_line_value(editor, "U.Price", str(item.unit_net_price))
        self._set_line_value(editor, "VAT", str(item.vat_percentage))
        if item.discount_percentage > 0:
            self._set_line_value(editor, "Discount", str(item.discount_percentage))

    def _set_line_value(self, editor: BaseWrapper, label: str, value: str) -> None:
        edits = [e.wrapper_object() for e in editor.descendants(control_type="Edit") if e.is_enabled()]
        for edit in edits:
            surrounding = edit.window_text()
            if label.lower() in surrounding.lower():
                self.ui.set_text(edit, value)
                return
        self._set_field(editor, label, value)

    def save_order(self, editor: BaseWrapper) -> str:
        order_number = self._read_field(editor, "Order No.")
        self.ui.click_button(editor, title_re="^Save$")
        self.ui.wait_until(lambda: editor.is_visible(), timeout=self.ui.timeout)
        return order_number or self._read_field(editor, "Order No.")

    def _read_field(self, editor: BaseWrapper, label: str) -> str:
        try:
            return self.ui.get_text(self.ui.find_edit_near_label(editor, label))
        except Exception:  # noqa: BLE001
            return ""

    def verify_saved_order(self, order: OrderData, order_number: str) -> None:
        window = self.f.window
        self.ui.click_menu_path(window, ["Data", "Documents"])
        docs = self.ui.wait_for_window(".*Documents.*", timeout=self.ui.timeout)
        rows = self._find_document_rows(docs, order_number)
        if len(rows) != 1:
            raise ManualReviewRequired(
                reason=f"Expected exactly one order row for {order_number}, found {len(rows)}",
                stage="Order Verification",
            )
        row = rows[0]
        row_text = " ".join(row)
        if order.external_reference and order.external_reference not in row_text:
            raise ManualReviewRequired(
                reason=f"Order verification failed: Cust.Ref. {order.external_reference} not found",
                stage="Order Verification",
            )
        if order.totals.gross_total is not None:
            total_text = str(order.totals.gross_total)
            if total_text.replace(".", ",") not in row_text and total_text not in row_text:
                logger.warning("Could not confirm gross total in documents list row")

    def _find_document_rows(self, docs: BaseWrapper, doc_number: str) -> list[list[str]]:
        tables = docs.descendants(control_type="Table")
        if not tables:
            tables = docs.descendants(control_type="DataGrid")
        if not tables:
            raise ManualReviewRequired(
                reason="Documents table not found",
                stage="Order Verification",
            )
        table = tables[0].wrapper_object()
        return [
            row
            for row in self.ui.read_table_rows(table)
            if any(doc_number in cell for cell in row)
        ]

    def reopen_order_editor(self, order_number: str) -> BaseWrapper:
        window = self.f.window
        self.ui.click_menu_path(window, ["Data", "Documents"])
        docs = self.ui.wait_for_window(".*Documents.*", timeout=self.ui.timeout)
        rows = self._find_document_rows(docs, order_number)
        if not rows:
            raise ManualReviewRequired(
                reason=f"Order {order_number} not found in documents",
                stage="Invoice Creation",
            )
        tables = docs.descendants(control_type="Table") or docs.descendants(control_type="DataGrid")
        table = tables[0].wrapper_object()
        for item in table.descendants(control_type="DataItem"):
            if order_number in self.ui.get_text(item.wrapper_object()):
                self.ui.click_control(item.wrapper_object())
                break
        self.ui.click_button(docs, title_re="Open|Edit")
        return self.ui.wait_for_window(".*Order.*", timeout=self.ui.timeout)
