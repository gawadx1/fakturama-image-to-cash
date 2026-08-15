"""Invoice creation and payment automation."""

from __future__ import annotations

import logging

from pywinauto.base_wrapper import BaseWrapper

from app.exceptions import ManualReviewRequired
from app.models.order import OrderData, PaymentStatus
from app.verification.validators import normalize_text

logger = logging.getLogger("fakturama_automation")


class InvoiceAutomation:
    def __init__(self, fakturama) -> None:
        self.f = fakturama
        self.ui = fakturama.ui

    def create_from_order(self, order_editor: BaseWrapper) -> BaseWrapper:
        for label in (
            "Create a follow-up document",
            "Follow-up document",
            "Create follow-up",
        ):
            try:
                self.ui.click_button(order_editor, title_re=label)
                break
            except Exception:  # noqa: BLE001
                continue
        else:
            menu = self.ui.require_control(
                order_editor,
                stage="Invoice Creation",
                title_re=".*follow-up.*|.*Invoice.*",
                control_type="MenuItem",
            )
            self.ui.click_control(menu)

        try:
            self.ui.click_button(order_editor, title_re="^Invoice$")
        except Exception:  # noqa: BLE001
            pass

        return self.ui.wait_for_window(".*Invoice.*", timeout=self.ui.timeout)

    def complete_invoice(
        self,
        order: OrderData,
        invoice_editor: BaseWrapper,
        payment_method: str,
    ) -> None:
        editor_text = self.ui.get_text(invoice_editor)
        if order.external_reference and order.external_reference not in editor_text:
            logger.warning("Cust.Ref. not visible on invoice editor")
        try:
            self._set_combo(invoice_editor, "Payment", payment_method)
        except Exception as exc:  # noqa: BLE001
            raise ManualReviewRequired(
                reason=f"Payment method {payment_method!r} unavailable on invoice",
                stage="Invoice Completion",
            ) from exc

    def apply_payment_status(self, order: OrderData, invoice_editor: BaseWrapper) -> None:
        status = order.payment.payment_status
        paid_checkbox = self.ui.find_checkbox_near_label(invoice_editor, "Paid")
        if status == PaymentStatus.PAID:
            if not paid_checkbox.get_toggle_state():
                self.ui.click_control(paid_checkbox)
            if order.payment.payment_date:
                self._set_field(
                    invoice_editor,
                    "Payment Date",
                    order.payment.payment_date.strftime("%d.%m.%Y"),
                )
            if order.totals.gross_total is not None:
                self._set_field(invoice_editor, "Value", str(order.totals.gross_total))
        else:
            if paid_checkbox.get_toggle_state():
                self.ui.click_control(paid_checkbox)

    def save_invoice(self, invoice_editor: BaseWrapper) -> str:
        invoice_number = self._read_field(invoice_editor, "Invoice No.")
        self.ui.click_button(invoice_editor, title_re="^Save$")
        self.ui.wait_until(lambda: invoice_editor.is_visible(), timeout=self.ui.timeout)
        return invoice_number or self._read_field(invoice_editor, "Invoice No.")

    def verify_saved_invoice(
        self,
        order: OrderData,
        invoice_number: str,
        order_number: str,
    ) -> None:
        window = self.f.window
        self.ui.click_menu_path(window, ["Data", "Documents"])
        docs = self.ui.wait_for_window(".*Documents.*", timeout=self.ui.timeout)
        invoice_rows = self.f.orders._find_document_rows(docs, invoice_number)
        order_rows = self.f.orders._find_document_rows(docs, order_number)

        if len(invoice_rows) != 1:
            raise ManualReviewRequired(
                reason=f"Expected one invoice row for {invoice_number}, found {len(invoice_rows)}",
                stage="Final Verification",
            )
        if len(order_rows) != 1:
            raise ManualReviewRequired(
                reason=f"Expected original order {order_number} to remain present",
                stage="Final Verification",
            )

        if order.payment.payment_status == PaymentStatus.PAID:
            invoice_text = " ".join(invoice_rows[0])
            if order.payment.payment_date:
                date_text = order.payment.payment_date.strftime("%d.%m.%Y")
                if date_text not in invoice_text:
                    logger.warning("Payment date not confirmed in documents list")

        logger.info("Invoice verified")

    def _set_field(self, editor: BaseWrapper, label: str, value: str) -> None:
        control = self.ui.find_edit_near_label(editor, label)
        self.ui.set_text(control, value)

    def _set_combo(self, editor: BaseWrapper, label: str, value: str) -> None:
        combos = [c.wrapper_object() for c in editor.descendants(control_type="ComboBox")]
        for combo in combos:
            parent_text = " ".join(
                self.ui.get_text(t.wrapper_object())
                for t in combo.parent().descendants(control_type="Text")
            )
            if label.lower() in parent_text.lower():
                self.ui.select_combo(combo, value)
                return

    def _read_field(self, editor: BaseWrapper, label: str) -> str:
        try:
            return self.ui.get_text(self.ui.find_edit_near_label(editor, label))
        except Exception:  # noqa: BLE001
            return ""
