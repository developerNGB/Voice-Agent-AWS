"""Security exceptions."""


class AccessDeniedError(PermissionError):
    """Raised whenever isolation or authorization checks fail.

    The message shown to callers/tests is a stable ``ACCESS_DENIED`` string
    plus a short reason, so the demo/tests can assert on it.
    """

    def __init__(self, reason: str = ""):
        self.reason = reason
        super().__init__(f"ACCESS_DENIED: {reason}" if reason else "ACCESS_DENIED")
