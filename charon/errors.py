"""Application-level errors. Each carries a stable machine-readable code."""


class CharonError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        # Machine-readable specifics, e.g. which ids were unknown, sent as the error's details.
        self.details = details


class NotFoundError(CharonError):
    pass


class ConflictError(CharonError):
    pass


class InvalidInputError(CharonError):
    pass


class DownloaderError(CharonError):
    def __init__(self, message: str, code: str = "downloader_error") -> None:
        super().__init__(code, message)


class UnauthorizedError(CharonError):
    pass


class ForbiddenError(CharonError):
    pass


class FeedError(InvalidInputError):
    """A feed couldn't be fetched or read. Its message never contains the feed's URL."""
