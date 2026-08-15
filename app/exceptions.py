"""Application-specific exceptions."""


class ManualReviewRequired(Exception):
    """Raised when automation must stop for human intervention."""

    def __init__(
        self,
        reason: str,
        stage: str,
        suggested_action: str | None = None,
    ) -> None:
        self.reason = reason
        self.stage = stage
        self.suggested_action = suggested_action or (
            "Review the logged context, correct the issue, and re-run automation."
        )
        super().__init__(reason)

    def format_message(self) -> str:
        lines = [
            "=" * 40,
            "MANUAL REVIEW REQUIRED",
            "=" * 40,
            "",
            f"Stage: {self.stage}",
            f"Reason: {self.reason}",
            "",
            f"Suggested action: {self.suggested_action}",
            "",
            "Automation stopped safely.",
            "=" * 40,
        ]
        return "\n".join(lines)


class AutomationError(Exception):
    """Raised for unexpected automation failures."""
