class EventFormatError(ValueError):
    """Raised when an event payload or envelope cannot be serialized safely."""

    def __init__(self, message: str, *, payload: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload
