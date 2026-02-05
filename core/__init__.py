# Core decorators for plugin system
# Re-export from decorators.py for backward compatibility

from .decorators import (
    PluginType,
    PluginMetadata,
    indicator,
    strategy,
    risk_rule
)

from .base_classes import (
    BaseIndicator,
    IndicatorResult,
    SignalResult,
    BaseStrategy
)

from .registry import PluginRegistry
