# Strategy Registry - Auto-discover all strategies

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Type, Optional
import importlib.util
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StrategyInfo:
    """Strategy metadata"""
    name: str
    class_name: str
    module_path: str
    category: str
    indicators: List[str]
    signals: List[str]
    market_regimes: List[str]
    version: str
    author: str
    description: str
    parameters: Dict
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "class_name": self.class_name,
            "module_path": self.module_path,
            "category": self.category,
            "indicators": self.indicators,
            "signals": self.signals,
            "market_regimes": self.market_regimes,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "parameters": self.parameters
        }


class StrategyRegistry:
    """Strategy Registry - Auto-discover all strategies"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._strategies: Dict[str, Type] = {}
        self._strategy_info: Dict[str, StrategyInfo] = {}
        self._discovered = False
        self._initialized = True
    
    def discover(self, base_path: str = None) -> Dict[str, StrategyInfo]:
        """Auto-discover all strategies from the strategies folder"""
        if self._discovered and self._strategies:
            return self._strategy_info
        
        if base_path is None:
            # Default to TradeMaster_v2/strategies
            base_path = Path(__file__).parent.parent / "strategies"
        else:
            base_path = Path(base_path)
        
        if not base_path.exists():
            logger.warning(f"Strategies path does not exist: {base_path}")
            return {}
        
        # Discover strategies from all subdirectories
        strategy_dirs = [
            base_path,
            base_path / "trend",
            base_path / "momentum",
            base_path / "mean_reversion",
            base_path / "volume",
            base_path / "composite",
        ]
        
        for strategy_dir in strategy_dirs:
            if strategy_dir.exists():
                self._discover_from_dir(strategy_dir)
        
        self._discovered = True
        logger.info(f"Discovered {len(self._strategies)} strategies: {list(self._strategies.keys())}")
        return self._strategy_info
    
    def _discover_from_dir(self, strategy_dir: Path):
        """Discover strategies from a directory"""
        for py_file in strategy_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            module_name = py_file.stem
            module_path = str(py_file.relative_to(Path(__file__).parent.parent))
            
            try:
                spec = importlib.util.spec_from_file_location(
                    f"strategies.{py_file.parent.name}.{module_name}" if py_file.parent.name != "strategies" else f"strategies.{module_name}",
                    py_file
                )
                
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                    
                    # Find classes with _plugin_type = STRATEGY
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name, None)
                        if (
                            isinstance(attr, type)
                            and hasattr(attr, '_plugin_type')
                            and hasattr(attr, '_plugin_meta')
                        ):
                            meta = attr._plugin_meta
                            self._strategies[meta.name] = attr
                            self._strategy_info[meta.name] = StrategyInfo(
                                name=meta.name,
                                class_name=attr_name,
                                module_path=module_path,
                                category=meta.category,
                                indicators=meta.indicators or [],
                                signals=meta.signals or ["LONG", "SHORT", "HOLD"],
                                market_regimes=meta.market_regimes or [],
                                version=meta.version,
                                author=meta.author,
                                description=meta.description,
                                parameters=meta.parameters or {}
                            )
                            
            except Exception as e:
                logger.warning(f"Failed to load strategy from {py_file}: {e}")
    
    def get_strategy(self, name: str) -> Optional[Type]:
        """Get strategy class by name"""
        if not self._discovered:
            self.discover()
        return self._strategies.get(name)
    
    def get_strategy_info(self, name: str) -> Optional[StrategyInfo]:
        """Get strategy info by name"""
        if not self._discovered:
            self.discover()
        return self._strategy_info.get(name)
    
    def list_strategies(self, category: str = None) -> List[StrategyInfo]:
        """List all strategies, optionally filtered by category"""
        if not self._discovered:
            self.discover()
        
        if category:
            return [
                info for info in self._strategy_info.values()
                if info.category == category
            ]
        return list(self._strategy_info.values())
    
    def list_categories(self) -> List[str]:
        """List all strategy categories"""
        if not self._discovered:
            self.discover()
        
        categories = set(info.category for info in self._strategy_info.values())
        return sorted(categories)
    
    def reload(self):
        """Reload all strategies"""
        self._strategies.clear()
        self._strategy_info.clear()
        self._discovered = False
        return self.discover()


# Singleton instance
_registry = None


def get_registry() -> StrategyRegistry:
    """Get the strategy registry singleton"""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry


def discover_strategies(base_path: str = None) -> Dict[str, StrategyInfo]:
    """Convenience function to discover strategies"""
    return get_registry().discover(base_path)


def list_strategies(category: str = None) -> List[StrategyInfo]:
    """Convenience function to list strategies"""
    return get_registry().list_strategies(category)


def get_strategy(name: str) -> Optional[Type]:
    """Convenience function to get a strategy class"""
    return get_registry().get_strategy(name)
