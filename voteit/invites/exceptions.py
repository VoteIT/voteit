class DataColValidationError(ValueError):
    name: str
    index: int  # Start at 1
    rows: list[int]  # Start at 1
    # May be a lazy translation proxy -- always str() it before returning
    message: str | None

    def __init__(self, *, name, index, rows, message: str | None = None):
        self.name = name
        self.index = index
        self.rows = rows
        self.message = message
        super().__init__()

    def __str__(self):
        if self.message:
            return str(self.message)
        return (
            f"Column {self.name} ({self.index}) validation failed at rows: {self.rows}"
        )
