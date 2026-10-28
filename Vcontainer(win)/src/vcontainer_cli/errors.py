class VcontainerApiError(RuntimeError):
    def __init__(self, status: int, detail: str | None):
        self.status = status
        self.detail = detail
        super().__init__(detail or f"API request failed ({status})")
