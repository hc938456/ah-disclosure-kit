class AhFilingsError(RuntimeError):
    """Base error for ah-disclosure."""


class ProviderError(AhFilingsError):
    """Raised when an upstream provider fails."""


class OptionalDependencyError(AhFilingsError):
    """Raised when an optional dependency is required but missing."""


class ConfigurationError(AhFilingsError):
    """Raised when configuration is invalid."""
