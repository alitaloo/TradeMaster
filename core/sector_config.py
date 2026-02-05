#!/usr/bin/env python3
"""
行業配置模組 - Sector Configuration
根據行業特性配置不同的策略參數
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime


class Sector(Enum):
    """行業分類"""
    # 半導體
    SEMICONDUCTOR = "semiconductor"
    SEMICONDUCTOR_EQUIPMENT = "semiconductor_equipment"
    
    # 科技巨頭
    TECH_GIANT = "tech_giant"
    SOFTWARE = "software"
    INTERNET = "internet"
    
    # 消費電子
    CONSUMER_ELECTRONICS = "consumer_electronics"
    EV_AUTOMOBILE = "ev_automobile"
    
    # 儲存/數據
    STORAGE = "storage"
    DATA_CENTER = "data_center"
    
    # 金融科技
    CRYPTO = "crypto"
    FINTECH = "fintech"
    
    # 其他
    AEROSPACE = "aerospace"
    TRANSPORTATION = "transportation"
    ENTERPRISE_SOFTWARE = "enterprise_software"


@dataclass
class SectorConfig:
    """行業配置"""
    sector: Sector
    name: str
    
    # 策略偏好
    recommended_strategies: List[str]  # 推薦策略
    avoid_strategies: List[str] = None  # 避免策略
    
    # 倉位配置
    max_position_pct: float = 0.20  # 最大倉位比例
    max_sector_pct: float = 0.40     # 行業最大曝險
    
    # 波動率配置
    volatility_regime: str = "medium"  # 預期波動率
    atr_multiplier: float = 2.0       # ATR 倍數
    base_stop_loss_pct: float = 0.05  # 基礎止損
    
    # 特殊配置
    use_trend_filter: bool = True     # 是否使用趨勢過濾
    min_adx_threshold: float = 20.0   # 最小 ADX
    correlation_adjustment: float = 1.0 # 相關性調整係數


# 預設行業配置
SECTOR_CONFIGS: Dict[Sector, SectorConfig] = {
    # ===== 半導體 =====
    Sector.SEMICONDUCTOR: SectorConfig(
        sector=Sector.SEMICONDUCTOR,
        name="半導體",
        recommended_strategies=["MultiFactor", "MACDTrend", "TrendFollower"],
        avoid_strategies=["BollingerBounce"],
        max_position_pct=0.20,
        max_sector_pct=0.40,
        volatility_regime="high",
        atr_multiplier=2.5,
        base_stop_loss_pct=0.08,
        use_trend_filter=True,
        min_adx_threshold=25.0,
        correlation_adjustment=0.8  # 半導體高度相關，降低曝險
    ),
    
    Sector.SEMICONDUCTOR_EQUIPMENT: SectorConfig(
        sector=Sector.SEMICONDUCTOR_EQUIPMENT,
        name="半導體設備",
        recommended_strategies=["TrendFollower", "ADXTrend"],
        max_position_pct=0.15,
        max_sector_pct=0.25,
        volatility_regime="high",
        atr_multiplier=2.5,
        use_trend_filter=True,
        min_adx_threshold=25.0
    ),
    
    # ===== 科技巨頭 =====
    Sector.TECH_GIANT: SectorConfig(
        sector=Sector.TECH_GIANT,
        name="科技巨頭",
        recommended_strategies=["MultiFactor", "TrendFollower", "MACDTrend"],
        avoid_strategies=[],
        max_position_pct=0.25,
        max_sector_pct=0.50,
        volatility_regime="medium",
        atr_multiplier=2.0,
        base_stop_loss_pct=0.05,
        use_trend_filter=False,
        min_adx_threshold=20.0
    ),
    
    Sector.SOFTWARE: SectorConfig(
        sector=Sector.SOFTWARE,
        name="軟體",
        recommended_strategies=["RSI_Reversal", "MultiFactor"],
        avoid_strategies=[],
        max_position_pct=0.20,
        max_sector_pct=0.30,
        volatility_regime="medium",
        atr_multiplier=2.0,
        base_stop_loss_pct=0.05,
        use_trend_filter=False
    ),
    
    Sector.INTERNET: SectorConfig(
        sector=Sector.INTERNET,
        name="網路",
        recommended_strategies=["TrendFollower", "MACDTrend"],
        avoid_strategies=[],
        max_position_pct=0.20,
        max_sector_pct=0.30,
        volatility_regime="medium",
        atr_multiplier=2.0,
        use_trend_filter=True,
        min_adx_threshold=22.0
    ),
    
    # ===== 消費電子 =====
    Sector.CONSUMER_ELECTRONICS: SectorConfig(
        sector=Sector.CONSUMER_ELECTRONICS,
        name="消費電子",
        recommended_strategies=["MultiFactor", "RSI_Reversal"],
        avoid_strategies=["BollingerBounce"],
        max_position_pct=0.20,
        max_sector_pct=0.25,
        volatility_regime="medium",
        atr_multiplier=2.0,
        base_stop_loss_pct=0.06,
        use_trend_filter=False
    ),
    
    Sector.EV_AUTOMOBILE: SectorConfig(
        sector=Sector.EV_AUTOMOBILE,
        name="電動車",
        recommended_strategies=["BollingerBounce", "MomentumCombo"],
        avoid_strategies=["TrendFollower"],
        max_position_pct=0.15,
        max_sector_pct=0.20,
        volatility_regime="high",
        atr_multiplier=3.0,  # 寬止損
        base_stop_loss_pct=0.10,
        use_trend_filter=False,
        min_adx_threshold=30.0  # 只在強趨勢時交易
    ),
    
    # ===== 儲存/數據 =====
    Sector.STORAGE: SectorConfig(
        sector=Sector.STORAGE,
        name="儲存",
        recommended_strategies=["BollingerBounce", "RSI_Reversal"],
        avoid_strategies=["TrendFollower"],
        max_position_pct=0.15,
        max_sector_pct=0.25,
        volatility_regime="high",
        atr_multiplier=2.5,
        base_stop_loss_pct=0.08,
        use_trend_filter=True,
        min_adx_threshold=25.0
    ),
    
    Sector.DATA_CENTER: SectorConfig(
        sector=Sector.DATA_CENTER,
        name="數據中心",
        recommended_strategies=["TrendFollower", "MACDTrend"],
        max_position_pct=0.20,
        max_sector_pct=0.30,
        volatility_regime="medium",
        atr_multiplier=2.0,
        use_trend_filter=True,
        min_adx_threshold=22.0
    ),
    
    # ===== 加密貨幣 =====
    Sector.CRYPTO: SectorConfig(
        sector=Sector.CRYPTO,
        name="加密貨幣",
        recommended_strategies=["MomentumCombo", "TrendFollower"],
        avoid_strategies=["RSI_Reversal"],
        max_position_pct=0.10,  # 低倉位
        max_sector_pct=0.15,
        volatility_regime="very_high",
        atr_multiplier=4.0,  # 極寬止損
        base_stop_loss_pct=0.15,
        use_trend_filter=True,
        min_adx_threshold=35.0  # 只在極強趨勢時交易
    ),
    
    # ===== 企業軟體 =====
    Sector.ENTERPRISE_SOFTWARE: SectorConfig(
        sector=Sector.ENTERPRISE_SOFTWARE,
        name="企業軟體",
        recommended_strategies=["MultiFactor", "RSI_Reversal"],
        max_position_pct=0.20,
        max_sector_pct=0.30,
        volatility_regime="low",
        atr_multiplier=1.5,  # 窄止損
        base_stop_loss_pct=0.04,
        use_trend_filter=False
    ),
    
    # ===== 航天 =====
    Sector.AEROSPACE: SectorConfig(
        sector=Sector.AEROSPACE,
        name="航天",
        recommended_strategies=["MomentumCombo"],
        avoid_strategies=["TrendFollower", "RSI_Reversal"],
        max_position_pct=0.10,  # 低倉位
        max_sector_pct=0.15,
        volatility_regime="very_high",
        atr_multiplier=3.5,
        base_stop_loss_pct=0.12,
        use_trend_filter=True,
        min_adx_threshold=30.0
    ),
}


# 股票到行業的映射
STOCK_TO_SECTOR: Dict[str, Sector] = {
    # 半導體
    "NVDA": Sector.SEMICONDUCTOR,
    "TSM": Sector.SEMICONDUCTOR,
    "AMD": Sector.SEMICONDUCTOR,
    "INTC": Sector.SEMICONDUCTOR,
    "MU": Sector.SEMICONDUCTOR,
    "AMAT": Sector.SEMICONDUCTOR_EQUIPMENT,
    
    # 科技巨頭
    "AAPL": Sector.TECH_GIANT,
    "MSFT": Sector.TECH_GIANT,
    "GOOGL": Sector.INTERNET,
    "META": Sector.INTERNET,
    "AMZN": Sector.INTERNET,
    
    # 消費電子
    "TSLA": Sector.EV_AUTOMOBILE,
    
    # 儲存
    "WDC": Sector.STORAGE,
    
    # 加密
    "COIN": Sector.CRYPTO,
    
    # 企業軟體
    "ORCL": Sector.ENTERPRISE_SOFTWARE,
    
    # 出行
    "UBER": Sector.TRANSPORTATION,
    
    # 航天
    "RKLB": Sector.AEROSPACE,
}


class SectorConfigManager:
    """行業配置管理器"""
    
    def __init__(self, configs: Dict[Sector, SectorConfig] = None):
        self.configs = configs or SECTOR_CONFIGS
        self.stock_map = STOCK_TO_SECTOR.copy()
    
    def get_config(self, symbol: str) -> SectorConfig:
        """獲取股票的行業配置"""
        sector = self.stock_map.get(symbol.upper())
        
        if sector and sector in self.configs:
            return self.configs[sector]
        
        # 預設配置
        return SectorConfig(
            sector=Sector.TECH_GIANT,
            name="預設",
            recommended_strategies=["MultiFactor"],
            max_position_pct=0.20,
            max_sector_pct=0.30,
            volatility_regime="medium",
            atr_multiplier=2.0,
            base_stop_loss_pct=0.05,
            use_trend_filter=False,
            min_adx_threshold=20.0
        )
    
    def get_recommended_strategies(self, symbol: str) -> List[str]:
        """獲取推薦策略"""
        config = self.get_config(symbol)
        return config.recommended_strategies
    
    def get_avoid_strategies(self, symbol: str) -> List[str]:
        """獲取避免策略"""
        config = self.get_config(symbol)
        return config.avoid_strategies or []
    
    def get_max_position_pct(self, symbol: str) -> float:
        """獲取最大倉位比例"""
        return self.get_config(symbol).max_position_pct
    
    def get_max_sector_pct(self, sector: Sector) -> float:
        """獲取行業最大曝險"""
        if sector in self.configs:
            return self.configs[sector].max_sector_pct
        return 0.30
    
    def get_stop_loss_config(self, symbol: str) -> Dict:
        """獲取止損配置"""
        config = self.get_config(symbol)
        return {
            "atr_multiplier": config.atr_multiplier,
            "base_stop_loss_pct": config.base_stop_loss_pct
        }
    
    def get_trend_filter_config(self, symbol: str) -> Dict:
        """獲取趨勢過濾配置"""
        config = self.get_config(symbol)
        return {
            "use_filter": config.use_trend_filter,
            "min_adx": config.min_adx_threshold
        }
    
    def get_portfolio_adjustment(
        self,
        portfolio: Dict[str, float]
    ) -> Dict[str, float]:
        """
        根據行業配置調整投資組合
        
        計算每個行業的曝險，過高的話發出警告
        """
        sector_exposure = {}
        adjustments = {}
        
        for symbol, weight in portfolio.items():
            sector = self.stock_map.get(symbol.upper())
            if sector is None:
                continue
            
            sector_exposure[sector] = sector_exposure.get(sector, 0) + weight
        
        for sector, exposure in sector_exposure.items():
            max_pct = self.get_max_sector_pct(sector)
            
            if exposure > max_pct:
                # 曝險過高，需要調整
                adjustments[sector] = {
                    "current": exposure,
                    "max": max_pct,
                    "action": "REDUCE",
                    "reduce_by": exposure - max_pct
                }
        
        return adjustments
    
    def get_sector_correlation_adjustment(self, symbol: str) -> float:
        """獲取相關性調整係數"""
        config = self.get_config(symbol)
        return config.correlation_adjustment


# 便捷函數
def get_stock_config(symbol: str) -> SectorConfig:
    """快速獲取股票配置"""
    manager = SectorConfigManager()
    return manager.get_config(symbol)


def get_recommended_strategies(symbol: str) -> List[str]:
    """快速獲取推薦策略"""
    manager = SectorConfigManager()
    return manager.get_recommended_strategies(symbol)
