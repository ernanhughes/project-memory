"""Per-query activation: state, decay, competition."""

from .decay import apply_threshold, hop_decay, normalise  # noqa: F401
from .inhibition import fan_divisor, lateral_inhibition  # noqa: F401
from .state import ActivationEvent, ActivationState  # noqa: F401
