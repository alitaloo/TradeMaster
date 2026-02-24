# StrategyRegistry - 自動發現所有策略
# 從 strategies 目錄自動掃描並加載所有策略

import sys
import logging
from pathlib import Path
from typing import Dict, List, Type, Optional, Tuple
import importlib.util

sys.path.insert(0, '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2')

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """策略註冊中心 - 自動發現並管理所有策略"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._strategies: Dict[str, Type] = {}
        self._strategy_metadata: Dict[str, dict] = {}
        self._strategy_params: Dict[str, List[dict]] = {}  # 策略的預設參數組合
        self._scan_paths = [
            '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/strategies',
        ]
        self._initialized = True
        logger.info("StrategyRegistry initialized")
    
    def register(self, strategy_cls: Type, metadata: dict = None, param_combinations: List[dict] = None):
        """手動註冊策略"""
        strategy_name = strategy_cls.__name__
        
        if metadata is None:
            # 嘗試從策略類獲取元數據
            meta = getattr(strategy_cls, '_plugin_meta', None)
            if meta:
                metadata = {
                    'name': meta.name,
                    'type': meta.category,
                    'version': meta.version,
                    'author': meta.author,
                    'description': meta.description,
                    'parameters': meta.parameters,
                    'indicators': meta.indicators,
                    'signals': meta.signals,
                    'market_regimes': meta.market_regimes,
                }
            else:
                metadata = {'name': strategy_name, 'type': 'custom', 'version': '1.0.0'}
        
        self._strategies[strategy_name] = strategy_cls
        self._strategy_metadata[strategy_name] = metadata
        
        if param_combinations:
            self._strategy_params[strategy_name] = param_combinations
        else:
            # 從 metadata 獲取預設參數
            default_params = metadata.get('parameters', {})
            if default_params:
                self._strategy_params[strategy_name] = [default_params]
            else:
                self._strategy_params[strategy_name] = [{}]
        
        logger.info(f"Registered strategy: {strategy_name}")
    
    def discover_strategies(self, paths: List[str] = None) -> int:
        """自動發現並註冊策略"""
        if paths:
            self._scan_paths = paths
        
        discovered_count = 0
        
        for scan_path in self._scan_paths:
            path = Path(scan_path)
            if not path.exists():
                logger.warning(f"Path does not exist: {scan_path}")
                continue
            
            # 遍歷所有 Python 文件
            for py_file in path.rglob("*.py"):
                if py_file.name.startswith('_') or py_file.name == '__init__.py':
                    continue
                
                try:
                    # 動態加載模塊
                    module_name = f"strategies.{py_file.stem}"
                    spec = importlib.util.spec_from_file_location(
                        module_name,
                        py_file,
                        submodule_search_locations=[str(py_file.parent)]
                    )
                    
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        module.__package__ = module_name.rsplit('.', 1)[0] if '.' in module_name else module_name
                        module.__path__ = [str(py_file.parent)]
                        spec.loader.exec_module(module)
                        
                        # 查找帶有 _plugin_type = STRATEGY 的類
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name, None)
                            if (
                                isinstance(attr, type)
                                and hasattr(attr, '_plugin_type')
                                and hasattr(attr, '_plugin_meta')
                            ):
                                # 檢查是否是策略類型
                                from core.decorators import PluginType
                                if attr._plugin_type == PluginType.STRATEGY:
                                    self.register(attr)
                                    discovered_count += 1
                
                except Exception as e:
                    logger.warning(f"Failed to load {py_file}: {e}")
        
        logger.info(f"Discovered {discovered_count} strategies")
        return discovered_count
    
    def get_strategy(self, name: str) -> Optional[Type]:
        """獲取策略類"""
        # 支援名稱匹配
        if name in self._strategies:
            return self._strategies[name]
        
        # 嘗試透過元數據名稱查找
        for strategy_name, metadata in self._strategy_metadata.items():
            if metadata.get('name', '').lower() == name.lower():
                return self._strategies[strategy_name]
        
        return None
    
    def get_metadata(self, name: str) -> Optional[dict]:
        """獲取策略元數據"""
        if name in self._strategy_metadata:
            return self._strategy_metadata[name]
        
        for strategy_name, metadata in self._strategy_metadata.items():
            if metadata.get('name', '').lower() == name.lower():
                return metadata
        
        return None
    
    def get_param_combinations(self, name: str) -> List[dict]:
        """獲取策略的參數組合"""
        if name in self._strategy_params:
            return self._strategy_params[name]
        
        # 嘗試透過元數據名稱查找
        for strategy_name, params in self._strategy_params.items():
            if strategy_name.lower() == name.lower():
                return params
        
        return [{}]
    
    def list_strategies(self, category: str = None, market_regime: str = None) -> List[Tuple[str, dict]]:
        """列出所有策略"""
        results = []
        
        for name, metadata in self._strategy_metadata.items():
            if category and metadata.get('type') != category:
                continue
            
            if market_regime:
                regimes = metadata.get('market_regimes', [])
                if market_regime not in regimes:
                    continue
            
            results.append((name, metadata))
        
        return results
    
    def add_param_combination(self, name: str, params: dict):
        """為策略添加參數組合"""
        if name not in self._strategy_params:
            self._strategy_params[name] = []
        
        if params not in self._strategy_params[name]:
            self._strategy_params[name].append(params)
    
    def set_default_params(self, name: str, params_list: List[dict]):
        """設置策略的預設參數組合"""
        self._strategy_params[name] = params_list
    
    def get_all_strategies(self) -> Dict[str, Type]:
        """獲取所有策略類"""
        return self._strategies.copy()
    
    def get_all_with_params(self) -> List[Tuple[str, Type, dict]]:
        """獲取所有策略及其參數組合"""
        results = []
        for name, cls in self._strategies.items():
            for params in self._strategy_params.get(name, [{}]):
                results.append((name, cls, params))
        return results


# 創建全局單例
_default_registry = None

def get_registry() -> StrategyRegistry:
    """獲取默認的策略註冊中心實例"""
    global _default_registry
    if _default_registry is None:
        _default_registry = StrategyRegistry()
    return _default_registry
