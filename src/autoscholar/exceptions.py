class AutoScholarError(Exception):
    """Base exception for AutoScholar."""


class WorkspaceError(AutoScholarError):
    """Raised when a workspace is invalid or incomplete."""


class ValidationError(AutoScholarError):
    """Raised when input data fails validation."""
