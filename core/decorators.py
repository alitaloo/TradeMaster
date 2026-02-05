# Core decorators for plugin system
# Extracted from __init__.py for proper module imports

from typing import Dict, Type, List
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PluginType(Enum):
    INDICATOR = "indicator"
    STRATEGY = "strategy"
    RISK_RULE = "risk_rule"
    EXECUTOR = "executor"
    NOTIFIER = "notifier"


@dataclass
class PluginMetadata:
    """插件元數據"""
    name: str
    type: PluginType
    category: str
    version: str
    author: str
    description: str
    parameters: dict
    outputs: List[str]
    tags: List[str]
    indicators: List[str] = None
    signals: List[str] = None
    market_regimes: List[str] = None


def indicator(
    name: str,
    category: str = "custom",
    version: str = "1.0.0",
    author: str = "Unknown",
    description: str = "",
    parameters: dict = None,
    outputs: List[str] = None,
    tags: List[str] = None
):
    """指標裝飾器"""
    def decorator(cls):
        cls._plugin_type = PluginType.INDICATOR
        cls._plugin_meta = PluginMetadata(
            name=name,
            type=PluginType.INDICATOR,
            category=category,
            version=version,
            author=author,
            description=description,
            parameters=parameters or {},
            outputs=outputs or [],
            tags=tags or []
        )
        return cls
    return decorator


def strategy(
    name: str,
    type: str = "custom",
    indicators: List[str] = None,
    signals: List[str] = None,
    market_regimes: List[str] = None,
    version: str = "1.0.0",
    author: str = "Unknown",
    description: str = "",
    parameters: dict = None,
    tags: List[str] = None
):
    """策略裝飾器"""
    def decorator(cls):
        cls._plugin_type = PluginType.STRATEGY
        cls._plugin_meta = PluginMetadata(
            name=name,
            type=PluginType.STRATEGY,
            category=type,
            version=version,
            author=author,
            description=description,
            parameters=parameters or {},
            outputs=[],
            tags=tags or [],
            indicators=indicators or [],
            signals=signals or ["LONG", "SHORT", "HOLD"],
            market_regimes=market_regimes or []
        )
        return cls
    return decorator


def risk_rule(
    name: str,
    rule_type: str = "position_sizing",
    version: str = "1.0.0",
    author: str = "Unknown",
    description: str = "",
    parameters: dict = None,
    tags: List[str] = None
):
    """風控規則裝飾器"""
    def decorator(cls):
        cls._plugin_type = PluginType.RISK_RULE
        cls._plugin_meta = PluginMetadata(
            name=name,
            type=PluginType.RISK_RULE,
            category=rule_type,
            version=version,
            author=author,
            description=description,
            parameters=parameters or {},
            outputs=[],
            tags=tags or []
        )
        return cls
    return decorator
