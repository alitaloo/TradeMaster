#!/usr/bin/env python3
"""
TradeMaster v2 - Top-K Ensemble 信號生成器
功能：從 MySQL 讀取 Top-K 策略配置，產生加權 ensemble 信號
"""

import pymysql
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import logging
import json

# 配置
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "alita",
    "password": "alitamysql",
    "database": "trademaster",
    "charset": "utf8mb4",
}

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TopKSignalGenerator:
    """Top-K Ensemble 信號生成器"""
    
    def __init__(self):
        self.stock_strategies = {}  # symbol -> {indicators, weights, ensemble_method}
        self.load_strategies_from_db()
    
    def load_strategies_from_db(self):
        """從 MySQL 讀取 Top-K 策略配置"""
        try:
            conn = pymysql.connect(**DB_CONFIG)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT symbol, timeframe, indicators, weights, ensemble_method
                    FROM stock_strategies
                    WHERE indicators IS NOT NULL
                """)
                
                for row in cur.fetchall():
                    symbol, timeframe, indicators_json, weights_json, method = row
                    
                    indicators = json.loads(indicators_json) if indicators_json else []
                    weights = json.loads(weights_json) if weights_json else []
                    
                    key = f"{symbol}"
                    self.stock_strategies[key] = {
                        'timeframe': timeframe,
                        'indicators': indicators,
                        'weights': weights,
                        'ensemble_method': method or 'weighted'
                    }
            
            conn.close()
            logger.info(f"✅ 從 MySQL 載入 {len(self.stock_strategies)} 個股票策略配置")
            
        except Exception as e:
            logger.error(f"❌ 讀取 MySQL 失敗: {e}")
            self.stock_strategies = {}
    
    def get_strategies(self, symbol: str) -> Optional[Dict]:
        """獲取指定股票的 Top-K 配置"""
        return self.stock_strategies.get(symbol)
    
    def get_all_strategies(self) -> Dict:
        """獲取所有股票策略配置"""
        return self.stock_strategies
    
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """計算技術指標"""
        d = df.copy()
        
        # 標準化欄位名稱 (支援大小寫)
        d.columns = [c.capitalize() if isinstance(c, str) else c for c in d.columns]
        
        d['Close'] = pd.to_numeric(d['Close'], errors='coerce')
        d['High'] = pd.to_numeric(d['High'], errors='coerce')
        d['Low'] = pd.to_numeric(d['Low'], errors='coerce')
        
        # 均線
        for p in [5, 10, 20, 50, 200]:
            d[f'SMA{p}'] = d['Close'].rolling(p, min_periods=1).mean()
        for p in [12, 26]:
            d[f'EMA{p}'] = d['Close'].ewm(span=p, adjust=False).mean()
        
        # MACD
        d['MACD'] = d['EMA12'] - d['EMA26']
        d['MACD_Sig'] = d['MACD'].ewm(span=9, adjust=False).mean()
        
        # RSI
        delta = d['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
        rs = gain / (loss.replace(0, np.nan))
        d['RSI'] = (100 - (100 / (1 + rs))).fillna(50)
        
        # Bollinger Bands
        m = d['Close'].rolling(20, min_periods=1).mean()
        s = d['Close'].rolling(20, min_periods=1).std()
        d['BB_Up'] = m + s * 2
        d['BB_Low'] = m - s * 2
        d['BB_Pct'] = ((d['Close'] - d['BB_Low']) / (d['BB_Up'] - d['BB_Low']).replace(0, np.nan)).fillna(0.5)
        
        # ADX
        h, l, c = d['High'], d['Low'], d['Close']
        pm = h.diff().clip(0)
        mm = (-l.diff()).clip(0)
        tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14, min_periods=1).mean()
        pdm = (pm / atr.replace(0, np.nan)) * 100
        mdm = (mm / atr.replace(0, np.nan)) * 100
        dx = ((pdm - mdm).abs() / (pdm + mdm).replace(0, np.nan)) * 100
        d['ADX'] = dx.rolling(14, min_periods=1).mean().fillna(0)
        d['PLUS_DI'] = pdm
        d['MINUS_DI'] = mdm
        
        return d
    
    def apply_single_strategy(self, d: pd.DataFrame, strategy_name: str) -> str:
        """應用單一策略，返回信號"""
        # 簡化的策略信號生成
        # 實際應該調用策略類
        
        # RSI 策略
        if 'RSI' in strategy_name:
            rsi = d['RSI'].iloc[-1]
            if rsi < 30:
                return "BUY"
            elif rsi > 70:
                return "SELL"
            return "HOLD"
        
        # MACD 策略
        if 'MACD' in strategy_name:
            macd = d['MACD'].iloc[-1]
            macd_sig = d['MACD_Sig'].iloc[-1]
            if macd > macd_sig:
                return "BUY"
            elif macd < macd_sig:
                return "SELL"
            return "HOLD"
        
        # MA 策略
        if 'MA' in strategy_name or 'Moving' in strategy_name:
            sma5 = d['SMA5'].iloc[-1]
            sma20 = d['SMA20'].iloc[-1]
            if sma5 > sma20:
                return "BUY"
            elif sma5 < sma20:
                return "SELL"
            return "HOLD"
        
        # ADX 策略
        if 'ADX' in strategy_name:
            adx = d['ADX'].iloc[-1]
            plus_di = d['PLUS_DI'].iloc[-1]
            minus_di = d['MINUS_DI'].iloc[-1]
            if adx > 25 and plus_di > minus_di:
                return "BUY"
            elif adx > 25 and minus_di > plus_di:
                return "SELL"
            return "HOLD"
        
        # 預設
        return "HOLD"
    
    def generate_ensemble_signal(self, d: pd.DataFrame, config: Dict) -> str:
        """產生 Top-K Ensemble 信號"""
        indicators = config.get('indicators', [])
        weights = config.get('weights', [])
        method = config.get('ensemble_method', 'weighted')
        
        if not indicators:
            return "HOLD"
        
        # 計算每個策略的信號
        signal_scores = {"BUY": 0, "SELL": 0, "HOLD": 0}
        
        for i, indicator in enumerate(indicators):
            weight = weights[i] if i < len(weights) else (1.0 / len(indicators))
            
            signal = self.apply_single_strategy(d, indicator)
            
            # 加權投票
            if signal == "BUY":
                signal_scores["BUY"] += weight
            elif signal == "SELL":
                signal_scores["SELL"] += weight
            else:
                signal_scores["HOLD"] += weight
        
        # 選擇最高分的信號
        if method == 'weighted':
            return max(signal_scores, key=signal_scores.get)
        else:
            # 投票制
            return max(signal_scores, key=signal_scores.get)
    
    def generate_signal(self, symbol: str, df: pd.DataFrame) -> Dict:
        """為指定股票生成信號"""
        config = self.get_strategies(symbol)
        
        if not config:
            return {
                'symbol': symbol,
                'signal': 'HOLD',
                'reason': 'No strategy config found'
            }
        
        # 計算指標
        d = self.compute_indicators(df)
        
        # 生成 Ensemble 信號
        signal = self.generate_ensemble_signal(d, config)
        
        return {
            'symbol': symbol,
            'signal': signal,
            'indicators': config.get('indicators', []),
            'weights': config.get('weights', []),
            'timeframe': config.get('timeframe'),
            'method': config.get('ensemble_method')
        }

    def save_signals_to_db(self, signals: Dict) -> int:
        """保存信號到資料庫"""
        saved_count = 0
        
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            for symbol, data in signals.items():
                signal_type = data.get('signal', 'HOLD')
                if signal_type == 'HOLD':
                    continue
                
                # 檢查是否已存在相同信號
                cur.execute("""
                    SELECT id FROM signals 
                    WHERE symbol = %s 
                    AND signal_type = %s 
                    AND status = 'pending'
                    AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
                """, (symbol, signal_type))
                
                if cur.fetchone():
                    continue
                
                # 計算數量
                price = data.get('price', 0)
                kelly = 0.25  # 預設 Kelly
                capital = 100000
                quantity = int(capital * kelly / price) if price > 0 else 0
                
                indicators = json.dumps(data.get('indicators', []))
                weights = json.dumps(data.get('weights', []))
                
                cur.execute("""
                    INSERT INTO signals 
                    (symbol, strategy_type, signal_type, price, quantity, confidence, status, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, NOW())
                """, (
                    symbol,
                    'TopK_Ensemble',
                    signal_type,
                    price,
                    quantity,
                    0.5,
                    json.dumps({'indicators': indicators, 'weights': weights})
                ))
                saved_count += 1
            
            conn.commit()
        conn.close()
        
        logger.info(f"信號已保存到資料庫: {saved_count} 筆")
        return saved_count


if __name__ == "__main__":
    # Test
    gen = TopKSignalGenerator()
    
    # 顯示配置
    print("\n📊 Top-K Ensemble 策略配置:")
    for symbol, config in gen.get_all_strategies().items():
        print(f"\n{symbol} ({config['timeframe']}):")
        for i, (ind, w) in enumerate(zip(config['indicators'], config['weights'])):
            print(f"  {i+1}. {ind}: {w*100:.1f}%")
