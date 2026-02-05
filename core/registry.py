# Plugin Registry - 線程安全插件註冊中心

from typing import Dict, Type, List
from pathlib import Path
import importlib.util
import logging

logger = logging.getLogger(__name__)


class PluginRegistry:
    """插件註冊中心"""
    
    _instance = None
    _lock = __import__('threading').Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._indicators: Dict[str, Type] = {}
        self._strategies: Dict[str, Type] = {}
        self._risk_rules: Dict[str, Type] = {}
        self._metadata: Dict[str, object] = {}
        self._initialized = True
    
    def register(self, cls) -> None:
        """註冊插件"""
        from .decorators import PluginType
        
        meta = getattr(cls, '_plugin_meta', None)
        if meta is None:
            raise ValueError(f"Class {cls.__name__} has no plugin metadata")
        
        plugin_type = getattr(cls, '_plugin_type', None)
        if plugin_type is None:
            raise ValueError(f"Class {cls.__name__} has no plugin type")
        
        if plugin_type == PluginType.INDICATOR:
            self._indicators[meta.name] = cls
        elif plugin_type == PluginType.STRATEGY:
            self._strategies[meta.name] = cls
        elif plugin_type == PluginType.RISK_RULE:
            self._risk_rules[meta.name] = cls
        else:
            raise ValueError(f"Unknown plugin type: {plugin_type}")
        
        self._metadata[meta.name] = meta
    
    def get_indicator(self, name: str):
        """獲取指標類"""
        return self._indicators.get(name)
    
    def get_strategy(self, name: str):
        """獲取策略類"""
        return self._strategies.get(name)
    
    def get_risk_rule(self, name: str):
        """獲取風控規則類"""
        return self._risk_rules.get(name)
    
    def list_indicators(self, category: str = None):
        """列出指標"""
        from .decorators import PluginType
        
        if category:
            return [
                (name, meta) for name, meta in self._metadata.items()
                if meta.type == PluginType.INDICATOR and meta.category == category
            ]
        return [
            (name, meta) for name, meta in self._metadata.items()
            if meta.type == PluginType.INDICATOR
        ]
    
    def list_strategies(self, market_regime: str = None):
        """列出策略"""
        from .decorators import PluginType
        
        if market_regime:
            return [
                (name, meta) for name, meta in self._metadata.items()
                if meta.type == PluginType.STRATEGY 
                and market_regime in (meta.market_regimes or [])
            ]
        return [
            (name, meta) for name, meta in self._metadata.items()
            if meta.type == PluginType.STRATEGY
        ]
    
    def list_risk_rules(self, rule_type: str = None):
        """列出風控規則"""
        from .decorators import PluginType
        
        if rule_type:
            return [
                (name, meta) for name, meta in self._metadata.items()
                if meta.type == PluginType.RISK_RULE and meta.category == rule_type
            ]
        return [
            (name, meta) for name, meta in self._metadata.items()
            if meta.type == PluginType.RISK_RULE
        ]
    
    def get_metadata(self, name: str):
        """獲取插件元數據"""
        return self._metadata.get(name)
    
    def discover_plugins(self, package_path: str):
        """自動發現並註冊插件"""
        import importlib.util
        import os
        
        package_path = Path(package_path).resolve()
        
        # 計算相對於 TradeMaster_v2 的相對路徑
        try:
            tm_path = Path(__file__).parent.parent.resolve()
            rel_path = package_path.relative_to(tm_path)
            package_name = str(rel_path).replace(os.sep, '.')
        except ValueError:
            # 如果無法計算相對路徑，使用基本名稱
            package_name = package_path.name
        
        for py_file in package_path.rglob("*.py"):
            if py_file.name == "__init__.py":
                module_name = package_name
            else:
                module_name = f"{package_name}.{py_file.stem}"
            
            try:
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    py_file,
                    submodule_search_locations=[] if py_file.name != "__init__.py" else [str(py_file.parent)]
                )
                
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    
                    # 設定 __package__ 以支援相對導入
                    module.__package__ = package_name
                    module.__path__ = [str(package_path)]
                    
                    spec.loader.exec_module(module)
                    
                    # 查找帶有 _plugin_type 屬性的類
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name, None)
                        if (
                            isinstance(attr, type)
                            and hasattr(attr, '_plugin_type')
                        ):
                            self.register(attr)
                            
            except Exception as e:
                # 記錄錯誤但繼續
                logger.warning(f"Failed to load {py_file}: {e}")
