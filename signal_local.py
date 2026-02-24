#!/usr/bin/env python3
"""
TradeMaster v2 - 基於回測結果的信號生成器（純本地版）
功能：讀取 strategy_complete_report.txt，使用本地日線數據生成實時買賣信號
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import logging
import json

# 導入技術指標
from core.indicators import calculate_adx

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 路徑配置
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data" / "historical"
REPORT_FILE = PROJECT_DIR / "strategy_complete_report.txt"


class SignalGenerator:
    """信號生成器"""
    
    def __init__(self, report_file: Path = None):
        self.report_file = report_file or REPORT_FILE
        self.stock_strategies = {}
        self.load_report()
    
    def load_report(self):
        """讀取回測報告"""
        try:
            # 2026-02-12: 優化股票池 - 剔除 TSLA、INTC、RKLB
            known_stocks = [
                "AAPL", "MSFT", "NVDA", "TSM", "AMZN", "META", "UBER", "MU", "AMD", "ORCL"
            ]
            
            with open(self.report_file, 'r') as f:
                for line in f:
                    for stock in known_stocks:
                        if stock in line and stock not in self.stock_strategies:
                            after = line[line.find(stock)+len(stock):]
                            words = after.split()
                            strategy = words[0] if words else None
                            sharpe = 0.0
                            signal = None
                            
                            for w in words:
                                if '.' in w and w.replace('.', '').replace('-', '').isdigit():
                                    sharpe = float(w)
                                if 'LONG' in w:
                                    signal = 'LONG'
                                elif 'SHORT' in w:
                                    signal = 'SHORT'
                            
                            if strategy and signal:
                                self.stock_strategies[stock] = {
                                    'strategy': strategy,
                                    'sharpe': sharpe,
                                    'signal': signal
                                }
            
            logger.info(f"✅ 載入 {len(self.stock_strategies)} 隻股票的最優策略")
        except Exception as e:
            logger.error(f"❌ 讀取報告失敗: {e}")
    
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """計算技術指標"""
        d = df.copy()
        d['Close'] = pd.to_numeric(d['Close'], errors='coerce')
        d['High'] = pd.to_numeric(d['High'], errors='coerce')
        d['Low'] = pd.to_numeric(d['Low'], errors='coerce')
        
        for p in [5, 10, 20, 50, 200]:
            d[f'SMA{p}'] = d['Close'].rolling(p, min_periods=1).mean()
        for p in [12, 26]:
            d[f'EMA{p}'] = d['Close'].ewm(span=p, adjust=False).mean()
        
        d['MACD'] = d['EMA12'] - d['EMA26']
        d['MACD_Sig'] = d['MACD'].ewm(span=9, adjust=False).mean()
        
        delta = d['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
        rs = gain / (loss.replace(0, np.nan))
        d['RSI'] = (100 - (100 / (1 + rs))).fillna(50)
        
        m = d['Close'].rolling(20, min_periods=1).mean()
        s = d['Close'].rolling(20, min_periods=1).std()
        d['BB_Up'] = m + s * 2
        d['BB_Low'] = m - s * 2
        d['BB_Pct'] = ((d['Close'] - d['BB_Low']) / (d['BB_Up'] - d['BB_Low']).replace(0, np.nan)).fillna(0.5)
        
        # 使用標準 Wilder's Smoothing ADX 計算
        adx_result = calculate_adx(d, period=14)
        d['ADX'] = adx_result['ADX']
        d['PLUS_DI'] = adx_result['PLUS_DI']
        d['MINUS_DI'] = adx_result['MINUS_DI']
        
        return d
    
    def apply_strategy(self, d: pd.DataFrame, strategy_name: str) -> str:
        """應用策略"""
        s = strategy_name
        latest = d.iloc[-1]
        base_strength = 50
        
        if 'RSI' in s:
            if '<30' in s:
                base_strength = 100 if latest['RSI'] < 25 else (85 if latest['RSI'] < 30 else 60)
            elif '<40' in s:
                base_strength = 100 if latest['RSI'] < 35 else (85 if latest['RSI'] < 38 else 60)
            elif '>60' in s:
                base_strength = 100 if latest['RSI'] > 75 else (85 if latest['RSI'] > 65 else 60)
            elif '>70' in s:
                base_strength = 100 if latest['RSI'] > 75 else (85 if latest['RSI'] > 70 else 60)
            elif 'Neutral' in s:
                base_strength = 85 if 35 < latest['RSI'] < 65 else 50
        
        elif 'SMA(50>200)' in s:
            # SMA50 > SMA200 = 短期上漲，但回測顯示 SHORT
            # 修正：價格低於兩均線時 SHORT
            if latest['Close'] < latest['SMA50'] < latest['SMA200']:
                base_strength = 5  # SHORT
            elif latest['Close'] > latest['SMA50'] > latest['SMA200']:
                base_strength = 95  # LONG
            elif latest['Close'] > latest['SMA50']:
                base_strength = 75
            else:
                base_strength = 25
        
        elif 'SMA50+MACD' in s:
            # SMA50 支撐 + MACD 確認
            if latest['Close'] > latest['SMA50'] and latest['MACD'] > latest['MACD_Sig']:
                base_strength = 95
            elif latest['Close'] < latest['SMA50'] and latest['MACD'] < latest['MACD_Sig']:
                base_strength = 5
            elif latest['MACD'] > latest['MACD_Sig']:
                base_strength = 75
            else:
                base_strength = 25
        
        elif 'BB' in s:
            # BB_Mid: 价格在通道中間時根據趨勢
            if latest['BB_Pct'] < 0.2:
                base_strength = 100
            elif latest['BB_Pct'] > 0.8:
                base_strength = 100
            else:
                base_strength = 50
        
        elif 'ADX' in s:
            if latest['ADX'] > 25:
                base_strength = 90 if latest['PLUS_DI'] > latest['MINUS_DI'] else 10
            else:
                base_strength = 50
        
        elif 'MACD' in s:
            base_strength = 85 if latest['MACD'] > latest['MACD_Sig'] else 15
        
        elif 'Trend' in s:
            score = 0
            if latest['Close'] > latest['SMA50']:
                score += 45
            if 35 < latest['RSI'] < 70:
                score += 45
            base_strength = score
        
        elif 'Bearish_MA' in s:
            # 做空均線空頭排列：SMA5 < SMA20 < SMA50
            is_bearish = (latest['SMA5'] < latest['SMA20'] and latest['SMA20'] < latest['SMA50'])
            # 不是空頭排列時 LONG，是空頭排列時 SHORT
            base_strength = 25 if is_bearish else 75
        
        # 強度閾值
        if base_strength >= 60:
            return 'LONG'
        elif base_strength <= 40:
            return 'SHORT'
        return 'HOLD'
    
    def generate_signal(self, stock: str) -> Dict:
        """生成信號"""
        try:
            strat_info = self.stock_strategies.get(stock)
            if not strat_info:
                return {'stock': stock, 'success': False}
            
            daily_file = DATA_DIR / f"{stock}.csv"
            if not daily_file.exists():
                return {'stock': stock, 'success': False, 'error': '無數據'}
            
            data = pd.read_csv(daily_file, index_col=0, parse_dates=True)
            d = self.compute_indicators(data)
            signal = self.apply_strategy(d, strat_info['strategy'])
            latest = d.iloc[-1]
            
            return {
                'stock': stock,
                'success': True,
                'strategy': strat_info['strategy'],
                'backtest_sharpe': strat_info['sharpe'],
                'signal': signal,
                'price': float(latest['Close']),
                'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                'data_source': '日線',
                'indicators': {
                    'RSI': round(float(latest['RSI']), 1),
                    'SMA50': round(float(latest['SMA50']), 2),
                    'Close': round(float(latest['Close']), 2)
                }
            }
        except Exception as e:
            return {'stock': stock, 'success': False, 'error': str(e)}
    
    def generate_all_signals(self) -> Dict:
        """生成所有信號"""
        signals = {}
        long_count = short_count = hold_count = 0
        
        for stock in self.stock_strategies:
            result = self.generate_signal(stock)
            if result.get('success'):
                signals[stock] = result
                if result['signal'] == 'LONG':
                    long_count += 1
                elif result['signal'] == 'SHORT':
                    short_count += 1
                else:
                    hold_count += 1
        
        actionable = long_count + short_count
        overview = {
            'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            'total_stocks': len(signals),
            'long_count': long_count,
            'short_count': short_count,
            'hold_count': hold_count,
            'market_sentiment': 'BULLISH' if long_count > short_count else ('BEARISH' if short_count > long_count else 'NEUTRAL'),
            'long_ratio': round(long_count / actionable * 100, 1) if actionable > 0 else 0
        }
        
        return {'overview': overview, 'signals': signals}


def main():
    print("=" * 80)
    print("           TradeMaster v2 - 實時信號生成器 (本地版)")
    print(f"           {datetime.now()}")
    print("=" * 80)
    
    generator = SignalGenerator()
    result = generator.generate_all_signals()
    
    overview = result['overview']
    signals = result['signals']
    
    print(f"\n📊 市場概覽 (數據源: 日線):")
    print(f"   總股票數: {overview['total_stocks']}")
    print(f"   🟢 LONG: {overview['long_count']}")
    print(f"   🔴 SHORT: {overview['short_count']}")
    print(f"   🟡 HOLD: {overview['hold_count']}")
    print(f"   📈 市場情緒: {overview['market_sentiment']} ({overview['long_ratio']}% LONG)")
    
    actionable = {k: v for k, v in signals.items() if v['signal'] != 'HOLD'}
    
    print(f"\n📋 可執行信號 (共 {len(actionable)} 個):")
    print("-" * 80)
    print(f"{'股票':<8} {'策略':<18} {'信號':<8} {'價格':<12} {'RSI':<8} {'夏普':<6}")
    print("-" * 80)
    
    for stock, sig in sorted(actionable.items()):
        emoji = "🟢" if sig['signal'] == 'LONG' else "🔴"
        print(f"{stock:<8} {sig['strategy']:<18} {emoji} {sig['signal']:<6} ${sig['price']:<10.2f} {sig['indicators']['RSI']:<7.1f} {sig['backtest_sharpe']:<6.2f}")
    
    print("-" * 80)
    
    holds = {k: v for k, v in signals.items() if v['signal'] == 'HOLD'}
    if holds:
        print(f"\n🟡 HOLD ({len(holds)} 個): " + ", ".join(sorted(holds.keys())))
    
    print(f"\n✅ 市場情緒: {overview['market_sentiment']}")


if __name__ == "__main__":
    main()
