from __future__ import annotations


class PlatformError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class MissingKeyError(PlatformError):
    def __init__(self) -> None:
        super().__init__("MISSING_KEY", "Authorization bearer key is required.", 401)


class InvalidKeyError(PlatformError):
    def __init__(self) -> None:
        super().__init__("INVALID_KEY", "The platform key is unknown or revoked.", 401)


class BusyError(PlatformError):
    def __init__(self) -> None:
        super().__init__("BUSY", "The platform is at its session concurrency limit.", 429)


class SpawnFailedError(PlatformError):
    def __init__(self) -> None:
        super().__init__("SPAWN_FAILED", "The agent worker could not be started.", 503)

