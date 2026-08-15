"""Reusable pywinauto UIA helper functions."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from pywinauto import Desktop
from pywinauto.application import Application
from pywinauto.base_wrapper import BaseWrapper
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PywinautoTimeoutError

from app.exceptions import AutomationError, ManualReviewRequired

logger = logging.getLogger("fakturama_automation")


class UIHelpers:
    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.desktop = Desktop(backend="uia")

    def wait_until(self, predicate, timeout: float | None = None, interval: float = 0.25) -> Any:
        deadline = time.time() + (timeout or self.timeout)
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                return predicate()
            except Exception as exc:  # noqa: BLE001 - polling loop
                last_error = exc
                time.sleep(interval)
        raise PywinautoTimeoutError(f"Timed out after {timeout or self.timeout}s: {last_error}")

    def find_window(
        self,
        title_re: str,
        timeout: float | None = None,
        top_level_only: bool = True,
    ) -> BaseWrapper:
        def _find() -> BaseWrapper:
            windows = self.desktop.windows(title_re=title_re, top_level_only=top_level_only)
            visible = [w for w in windows if w.is_visible()]
            if not visible:
                raise ElementNotFoundError(f"No visible window matching /{title_re}/")
            return visible[0]

        return self.wait_until(_find, timeout=timeout)

    def wait_for_window(self, title_re: str, timeout: float | None = None) -> BaseWrapper:
        logger.debug("Waiting for window: %s", title_re)
        return self.find_window(title_re, timeout=timeout)

    def child(
        self,
        parent: BaseWrapper,
        *,
        title: str | None = None,
        title_re: str | None = None,
        control_type: str | None = None,
        automation_id: str | None = None,
        class_name: str | None = None,
        best_match: str | None = None,
    ) -> BaseWrapper:
        kwargs: dict[str, Any] = {}
        if title is not None:
            kwargs["title"] = title
        if title_re is not None:
            kwargs["title_re"] = title_re
        if control_type is not None:
            kwargs["control_type"] = control_type
        if automation_id is not None:
            kwargs["auto_id"] = automation_id
        if class_name is not None:
            kwargs["class_name"] = class_name
        if best_match is not None:
            kwargs["best_match"] = best_match
        return parent.child_window(**kwargs)

    def find_control(
        self,
        parent: BaseWrapper,
        *,
        title: str | None = None,
        title_re: str | None = None,
        control_type: str | None = None,
        automation_id: str | None = None,
        class_name: str | None = None,
        timeout: float | None = None,
    ) -> BaseWrapper:
        def _find() -> BaseWrapper:
            control = self.child(
                parent,
                title=title,
                title_re=title_re,
                control_type=control_type,
                automation_id=automation_id,
                class_name=class_name,
            )
            control.wait("exists enabled visible", timeout=1)
            return control.wrapper_object()

        return self.wait_until(_find, timeout=timeout)

    def wait_for_control(self, parent: BaseWrapper, **kwargs: Any) -> BaseWrapper:
        return self.find_control(parent, **kwargs)

    def exists(self, parent: BaseWrapper, **kwargs: Any) -> bool:
        try:
            control = self.child(parent, **kwargs)
            return control.exists(timeout=0.5)
        except Exception:  # noqa: BLE001
            return False

    def click_control(self, control: BaseWrapper) -> None:
        control.set_focus()
        control.click_input()

    def set_text(self, control: BaseWrapper, value: str, clear: bool = True) -> None:
        control.set_focus()
        if clear:
            control.type_keys("^a{BACKSPACE}", set_foreground=True)
        if value:
            control.type_keys(value, with_spaces=True, set_foreground=True)

    def get_text(self, control: BaseWrapper) -> str:
        for getter in ("window_text", "get_value", "texts"):
            if hasattr(control, getter):
                try:
                    result = getattr(control, getter)()
                    if isinstance(result, list):
                        return " ".join(str(x) for x in result if x).strip()
                    return str(result or "").strip()
                except Exception:  # noqa: BLE001
                    continue
        return ""

    def select_combo(self, control: BaseWrapper, value: str) -> None:
        control.set_focus()
        try:
            control.select(value)
            return
        except Exception:  # noqa: BLE001
            pass
        self.set_text(control, value, clear=True)
        control.type_keys("{ENTER}", set_foreground=True)

    def click_button(self, parent: BaseWrapper, title: str | None = None, title_re: str | None = None) -> None:
        button = self.find_control(
            parent,
            title=title,
            title_re=title_re,
            control_type="Button",
        )
        self.click_control(button)

    def click_menu_path(self, window: BaseWrapper, path: list[str]) -> None:
        menu = self.find_control(window, control_type="MenuBar")
        self.click_control(menu)
        for item in path:
            menu_item = self.find_control(
                window,
                title_re=f"^{re.escape(item)}$",
                control_type="MenuItem",
            )
            self.click_control(menu_item)

    def dump_tree(self, root: BaseWrapper, max_depth: int = 4, depth: int = 0) -> str:
        lines: list[str] = []
        indent = "  " * depth
        try:
            info = root.element_info
            lines.append(
                f"{indent}{info.control_type} | title={info.name!r} | "
                f"auto_id={info.automation_id!r} | class={info.class_name!r} | "
                f"enabled={info.enabled} | visible={info.visible}"
            )
            if depth < max_depth:
                for child in root.children():
                    lines.append(self.dump_tree(child, max_depth=max_depth, depth=depth + 1))
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{indent}<error: {exc}>")
        return "\n".join(lines)

    def require_control(
        self,
        parent: BaseWrapper,
        stage: str,
        **kwargs: Any,
    ) -> BaseWrapper:
        try:
            return self.find_control(parent, **kwargs)
        except (ElementNotFoundError, PywinautoTimeoutError) as exc:
            raise ManualReviewRequired(
                reason=f"Required UI control not found: {kwargs}",
                stage=stage,
                suggested_action="Run --inspect-ui and update selectors for this Fakturama version.",
            ) from exc

    def capture_screenshot(self, window: BaseWrapper, path: str) -> None:
        try:
            image = window.capture_as_image()
            image.save(path)
            logger.info("Screenshot saved: %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not capture screenshot %s: %s", path, exc)

    def _list_visible_window_titles(self) -> list[str]:
        titles: list[str] = []
        for window in self.desktop.windows():
            try:
                if window.is_visible():
                    title = window.window_text().strip()
                    if title:
                        titles.append(title)
            except Exception:  # noqa: BLE001
                continue
        return titles

    def _find_fakturama_window(self, app: Application | None = None) -> BaseWrapper:
        patterns = [
            ".*Fakturama.*",
            ".*fakturama.*",
            ".*Workspace.*",
        ]
        for pattern in patterns:
            try:
                if app is not None:
                    window = app.window(title_re=pattern)
                    if window.exists(timeout=1):
                        return window.wrapper_object()
                windows = self.desktop.windows(title_re=pattern, top_level_only=True)
                visible = [w for w in windows if w.is_visible()]
                if visible:
                    return visible[0]
            except Exception:  # noqa: BLE001
                continue

        # Eclipse/SWT apps sometimes expose the shell before the title is populated.
        for window in self.desktop.windows(top_level_only=True):
            try:
                if not window.is_visible():
                    continue
                class_name = window.element_info.class_name or ""
                title = window.window_text().strip()
                if class_name in {"SWT_Window0", "WorkbenchWindow"} and title:
                    return window
            except Exception:  # noqa: BLE001
                continue

        raise ElementNotFoundError("Fakturama main window not found")

    def connect_or_launch(self, exe_path: str) -> tuple[Application, BaseWrapper]:
        app: Application | None = None
        try:
            app = Application(backend="uia").connect(title_re=".*Fakturama.*", timeout=3)
            logger.info("Connected to existing Fakturama instance")
        except (ElementNotFoundError, PywinautoTimeoutError):
            logger.info("Launching Fakturama from %s", exe_path)
            app = Application(backend="uia").start(f'"{exe_path}"')

        def _resolve_window() -> BaseWrapper:
            window = self._find_fakturama_window(app)
            window.wait("visible enabled", timeout=2)
            window.set_focus()
            return window

        try:
            main_window = self.wait_until(
                _resolve_window,
                timeout=max(self.timeout * 4, 60),
            )
        except PywinautoTimeoutError as exc:
            visible = ", ".join(self._list_visible_window_titles()[:12])
            raise AutomationError(
                "Timed out waiting for Fakturama main window. "
                f"Visible windows: {visible or '(none)'}"
            ) from exc
        return app, main_window

    def find_edit_near_label(self, parent: BaseWrapper, label: str) -> BaseWrapper:
        label_control = self.find_control(
            parent,
            title_re=f".*{re.escape(label)}.*",
            control_type="Text",
            timeout=3,
        )
        parent_rect = parent.rectangle()
        label_rect = label_control.rectangle()
        edits = [
            e.wrapper_object()
            for e in parent.descendants(control_type="Edit")
            if e.is_visible() and e.is_enabled()
        ]
        if not edits:
            raise ElementNotFoundError(f"No edit controls found near label {label!r}")

        def distance(edit: BaseWrapper) -> int:
            rect = edit.rectangle()
            vertical = abs(rect.top - label_rect.top)
            horizontal = abs(rect.left - label_rect.left)
            if rect.left >= label_rect.left - 20:
                horizontal = max(0, horizontal - 100)
            return vertical * 10 + horizontal

        return min(edits, key=distance)

    def find_checkbox_near_label(self, parent: BaseWrapper, label: str) -> BaseWrapper:
        checkbox = self.child(
            parent,
            title_re=f".*{re.escape(label)}.*",
            control_type="CheckBox",
        )
        if checkbox.exists(timeout=1):
            return checkbox.wrapper_object()
        return self.find_control(
            parent,
            title_re=f".*{re.escape(label)}.*",
            control_type="CheckBox",
        )

    def read_table_rows(self, table: BaseWrapper) -> list[list[str]]:
        rows: list[list[str]] = []
        for item in table.descendants(control_type="DataItem"):
            cells = [
                self.get_text(cell.wrapper_object())
                for cell in item.descendants(control_type="Text")
            ]
            if any(cell.strip() for cell in cells):
                rows.append(cells)
        if rows:
            return rows

        for item in table.descendants(control_type="ListItem"):
            text = self.get_text(item.wrapper_object())
            if text:
                rows.append(re.split(r"\t|\s{2,}", text))
        return rows

    def search_and_select_single_row(
        self,
        dialog: BaseWrapper,
        search_text: str,
        stage: str,
        match_fn,
    ) -> None:
        search_box = None
        for label in ("Search", "Filter", "Name", "Company"):
            try:
                search_box = self.find_edit_near_label(dialog, label)
                break
            except Exception:  # noqa: BLE001
                continue
        if search_box is None:
            edits = [e.wrapper_object() for e in dialog.descendants(control_type="Edit")]
            if not edits:
                raise ManualReviewRequired(
                    reason="Search field not found in selector dialog",
                    stage=stage,
                )
            search_box = edits[0]

        self.set_text(search_box, search_text)
        search_box.type_keys("{ENTER}", set_foreground=True)

        table = None
        for control_type in ("Table", "List", "DataGrid"):
            matches = dialog.descendants(control_type=control_type)
            if matches:
                table = matches[0].wrapper_object()
                break
        if table is None:
            raise ManualReviewRequired(
                reason="Result table not found in selector dialog",
                stage=stage,
            )

        def _matching_rows() -> list[list[str]]:
            return [row for row in self.read_table_rows(table) if match_fn(row)]

        matching = self.wait_until(_matching_rows, timeout=5)
        if len(matching) > 1:
            raise ManualReviewRequired(
                reason=f"Multiple conflicting matches found for {search_text!r}",
                stage=stage,
            )
        if not matching:
            return

        for item in table.descendants(control_type="DataItem"):
            row_text = " ".join(
                self.get_text(cell.wrapper_object())
                for cell in item.descendants(control_type="Text")
            )
            if match_fn(re.split(r"\t|\s{2,}", row_text)):
                self.click_control(item.wrapper_object())
                break
        else:
            list_items = table.descendants(control_type="ListItem")
            if list_items:
                self.click_control(list_items[0].wrapper_object())

        self.click_button(dialog, title_re="^OK$")
