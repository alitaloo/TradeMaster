#!/usr/bin/env python3
"""
TradeMaster v2 - 基於回測結果的信號生成器
功能：讀取 strategy_complete_report.txt，對每隻股票使用最優策略生成實時買賣信號
支持：
  - 10 分鐘 K 線數據 (即時) - 盤中實時
  - 日線數據 (data/historical/) - 回測使用
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import logging
import json

# 嘗試導入 yfinance，如果失敗則標記
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("⚠️ yfinance 未安裝，將使用本地日線數據")

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 路徑配置
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data" / "historical"
INTRADAY_DIR = PROJECT_DIR / "data" / "intraday"  # 5分鐘K線
REPORT_FILE = PROJECT_DIR / "strategy_complete_report.txt"


class SignalGenerator:
    """信號生成器"""
    
    def __init__(self, report_file: Path = None):
        """
        初始化
        
        Args:
            report_file: 回測報告文件路徑
        """
        self.report_file = report_file or PROJECT_DIR / "strategy_complete_report.txt"
        self.stock_strategies = {}
        self.load_report()
    
    def load_report(self):
        """讀取回測報告，提取最優策略"""
        try:
            known_stocks = [
                "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA",
                "TSM", "AMD", "INTC", "AVGO", "UBER", "ORCL", "WDC", "MU", "COIN", "RKLB"
            ]
            
            with open(self.report_file, 'r') as f:
                for line in f:
                    for stock in known_stocks:
                        if stock in line and stock not in self.stock_strategies:
                            # 解析策略名稱
                            after = line[line.find(stock)+len(stock):]
                            words = after.split()
                            
                            strategy = words[0] if words else None
                            sharpe = 0.0
                            signal = None
                            
                            for w in words:
                                # 清理並找夏普值
                                if '.' in w and w.replace('.', '').replace('-', '').isdigit():
                                    sharpe = float(w)
                                # 找信號 (LONG 或 SHORT)
                                if 'LONG' in w:
                                    signal = 'LONG'
                                elif 'SHORT' in w:
                                    signal = 'SHORT'
                            
                            if strategy and signal:
                                self.stock_strategies[stock] = {
                                    'strategy': strategy,
                                    'ann_return': 0.0,
                                    'sharpe': sharpe,
                                    'signal': signal
                                }
                                logger.info(f"載入: {stock} -> {strategy} (夏普={sharpe:.2f}, {signal})")
            
            logger.info(f"✅ 成功載入 {len(self.stock_strategies)} 隻股票的最優策略")
            
        except Exception as e:
            logger.error(f"❌ 讀取報告失敗: {e}")
            self.stock_strategies = {}
    
    def get_strategies(self) -> Dict[str, Dict]:
        """獲取所有股票的最優策略"""
        return self.stock_strategies
    
    def get_stock_strategy(self, stock: str) -> Optional[Dict]:
        """獲取指定股票的最優策略"""
        return self.stock_strategies.get(stock)
    
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """計算技術指標"""
        d = df.copy()
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
    
    def apply_strategy(self, d: pd.DataFrame, strategy_name: str) -> str:
        """
        應用策略，返回當前信號
        
        Returns:
            'LONG' | 'SHORT' | 'HOLD'
        """
        s = strategy_name
        latest = d.iloc[-1]
        prev = d.iloc[-2] if len(d) > 1 else latest
        
        # 計算策略強度 (0-100)
        strength = self._calculate_strategy_strength(d, s)
        
        # 均線策略
        if s == "SMA(5>20)":
            signal = (latest['Close'] > latest['SMA20']) and (latest['SMA20'] > latest['SMA5'])
        elif s == "SMA(10>50)":
            signal = (latest['Close'] > latest['SMA50']) and (latest['SMA50'] > latest['SMA10'])
        elif s == "SMA(20>50)":
            signal = (latest['Close'] > latest['SMA50']) and (latest['SMA50'] > latest['SMA20'])
        elif s == "SMA(50>200)":
            signal = (latest['Close'] > latest['SMA200']) and (latest['SMA200'] > latest['SMA50'])
        elif s == "SMA50+MACD":
            signal = (latest['Close'] > latest['SMA50']) and (latest['MACD'] > 0)
        elif s == "Bearish_MA":
            # 反向：做空均線空頭排列
            signal = not ((latest['SMA5'] < latest['SMA20']) and (latest['SMA20'] < latest['SMA50']))
        
        # RSI 策略
        elif s == "RSI<30":
            signal = latest['RSI'] < 30
        elif s == "RSI<40":
            signal = latest['RSI'] < 40
        elif s == "RSI>60":
            signal = latest['RSI'] > 60
        elif s == "RSI>70":
            signal = latest['RSI'] > 70
        elif s == "RSI_Neutral":
            signal = (latest['RSI'] > 40) and (latest['RSI'] < 60)
        
        # BB 策略
        elif s == "BB_Mid":
            signal = (latest['BB_Pct'] > 0.4) and (latest['BB_Pct'] < 0.6)
        
        # ADX 策略
        elif s == "ADX>20+DI+":
            signal = (latest['ADX'] > 20) and (latest['PLUS_DI'] > latest['MINUS_DI'])
        
        # 複合策略
        elif s == "Trend+RSI":
            signal = (latest['Close'] > latest['SMA50']) and (latest['RSI'] > 40) and (latest['RSI'] < 70)
        
        # MACD 策略
        elif s == "MACD_Cross":
            signal = latest['MACD'] > latest['MACD_Sig']
        elif s == "MACD>0":
            signal = latest['MACD'] > 0
        
        else:
            logger.warning(f"未知策略: {s}, 使用默認邏輯")
            signal = latest['Close'] > latest['SMA50']
        
        # 強度閾值判斷
        if strength >= 60:
            return 'LONG' if signal else 'SHORT'
        elif strength <= 40:
            return 'SHORT' if not signal else 'LONG'
        else:
            return 'HOLD'  # 信號強度不足，不操作
    
    def _calculate_strategy_strength(self, d: pd.DataFrame, strategy_name: str) -> float:
        """計算策略信號強度 (0-100)"""
        latest = d.iloc[-1]
        prev = d.iloc[-2] if len(d) > 1 else latest
        s = strategy_name
        
        # 基礎強度
        base_strength = 50
        
        # RSI 強度 - 擴大閾值範圍
        if 'RSI' in s:
            if '<30' in s:
                base_strength = 100 if latest['RSI'] < 25 else (85 if latest['RSI'] < 30 else 60 if latest['RSI'] < 35 else 50)
            elif '<40' in s:
                base_strength = 100 if latest['RSI'] < 35 else (85 if latest['RSI'] < 38 else 60)
            elif '>60' in s:
                base_strength = 100 if latest['RSI'] > 75 else (85 if latest['RSI'] > 65 else 60)
            elif '>70' in s:
                base_strength = 100 if latest['RSI'] > 75 else (85 if latest['RSI'] > 70 else 60)
            elif 'Neutral' in s:
                distance = min(abs(latest['RSI'] - 40), abs(latest['RSI'] - 60))
                base_strength = 85 if distance > 15 else 65 if distance > 8 else 50
        
        # MA 策略強度 - 更明確
        elif 'SMA' in s or 'MA' in s:
            if latest['Close'] > latest['SMA50'] > latest['SMA200']:
                base_strength = 95
            elif latest['Close'] < latest['SMA50'] < latest['SMA200']:
                base_strength = 5
            elif latest['Close'] > latest['SMA50']:
                base_strength = 75
            elif latest['Close'] < latest['SMA50']:
                base_strength = 25
        
        # BB 策略強度
        elif 'BB' in s:
            if latest['BB_Pct'] < 0.15:
                base_strength = 100
            elif latest['BB_Pct'] < 0.25:
                base_strength = 80
            elif latest['BB_Pct'] > 0.85:
                base_strength = 100
            elif latest['BB_Pct'] > 0.75:
                base_strength = 80
            else:
                base_strength = 50
        
        # ADX 策略強度
        elif 'ADX' in s:
            if latest['ADX'] > 25:
                base_strength = 90 if latest['PLUS_DI'] > latest['MINUS_DI'] else 10
            elif latest['ADX'] > 15:
                base_strength = 70 if latest['PLUS_DI'] > latest['MINUS_DI'] else 30
            else:
                base_strength = 50
        
        # MACD 強度
        elif 'MACD' in s:
            macd_cross = latest['MACD'] - latest['MACD_Sig']
            if macd_cross > 0:
                base_strength = 85
            elif macd_cross < 0:
                base_strength = 15
            else:
                base_strength = 50
        
        # 複合策略強度
        elif 'Trend' in s:
            trend_score = 0
            if latest['Close'] > latest['SMA50']:
                trend_score += 45
            if 35 < latest['RSI'] < 70:
                trend_score += 45
            base_strength = trend_score
        
        # 添加趨勢確認 (5日變化)
        if len(d) > 5:
            price_change_5d = (latest['Close'] - d.iloc[-5]['Close']) / d.iloc[-5]['Close'] * 100
            if base_strength > 50 and price_change_5d > 2:
                base_strength = min(100, base_strength + 10)
            elif base_strength < 50 and price_change_5d < -2:
                base_strength = max(0, base_strength - 10)
        
        return base_strength
    
    def generate_signal(self, stock: str, data: pd.DataFrame = None, use_intraday: bool = True) -> Dict:
        """為單一股票生成信號
        
        Args:
            stock: 股票代碼
            data: 預設數據（可選）
            use_intraday: 是否優先使用 5 分鐘 K 線
        """
        try:
            strat_info = self.stock_strategies.get(stock)
            if not strat_info:
                return {'stock': stock, 'success': False, 'error': '未找到最優策略'}
            
            strategy = strat_info['strategy']
            data_source = None
            
            if data is None and use_intraday and YFINANCE_AVAILABLE:
                # 嘗試即時獲取 10 分鐘 K 線（5分鐘API有限制）
                try:
                    ticker = yf.Ticker(stock)
                    intraday = ticker.history(period="1d", interval="10m")
                    
                    if intraday is not None and not intraday.empty and len(intraday) > 50:
                        data = intraday
                        data_source = "5分鐘K線 (即時)"
                except Exception as e:
                    logger.debug(f"{stock}: 即時獲取失敗 ({e})，使用本地數據")
            
            # 如果沒有 5 分鐘數據，使用本地日線
            if data is None:
                daily_file = DATA_DIR / f"{stock}.csv"
                if daily_file.exists():
                    data = pd.read_csv(daily_file, index_col=0, parse_dates=True)
                    data_source = "日線"
                else:
                    return {'stock': stock, 'success': False, 'error': '無本地數據'}
            
            # 計算指標和生成信號
            d = self.compute_indicators(data)
            signal = self.apply_strategy(d, strategy)  # 返回 'LONG' | 'SHORT' | 'HOLD'
            latest = d.iloc[-1]
            
            return {
                'stock': stock,
                'success': True,
                'strategy': strategy,
                'backtest_sharpe': strat_info['sharpe'],
                'backtest_return': strat_info['ann_return'],
                'signal': signal,  # 'LONG' | 'SHORT' | 'HOLD'
                'price': float(latest['Close']),
                'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                'data_source': data_source,  # 5分鐘K線 或 日線
                'indicators': {
                    'RSI': round(float(latest['RSI']), 2),
                    'SMA50': round(float(latest['SMA50']), 2),
                    'SMA200': round(float(latest['SMA200']), 2),
                    'MACD': round(float(latest['MACD']), 4),
                    'ADX': round(float(latest['ADX']), 2),
                    'BB_Pct': round(float(latest['BB_Pct']), 2)
                }
            }
            
        except Exception as e:
            logger.error(f"生成信號失敗 {stock}: {e}")
            return {'stock': stock, 'success': False, 'error': str(e)}
    
    def calculate_signal_strength(self, d: pd.DataFrame, strategy: str, is_long: bool) -> int:
        """計算信號強度 (0-100)"""
        try:
            latest = d.iloc[-1]
            rsi = latest['RSI']
            
            if is_long:
                if rsi < 30: strength = 100
                elif rsi < 40: strength = 80
                elif rsi < 50: strength = 60
                else: strength = 40
            else:
                if rsi > 70: strength = 100
                elif rsi > 60: strength = 80
                elif rsi > 50: strength = 60
                else: strength = 40
            
            # MA 位置
            if latest['Close'] > latest['SMA50'] > latest['SMA200']:
                strength_ma = 100 if is_long else 0
            elif latest['Close'] < latest['SMA50'] < latest['SMA200']:
                strength_ma = 0 if is_long else 100
            else:
                strength_ma = 50
            
            # MACD
            macd_cross = latest['MACD'] - latest['MACD_Sig']
            if is_long:
                strength_macd = 80 if macd_cross > 0 else 40
            else:
                strength_macd = 80 if macd_cross < 0 else 40
            
            strength = int(strength * 0.35 + strength_ma * 0.30 + strength_macd * 0.35)
            return min(100, max(0, strength))
            
        except Exception:
            return 50
    
    def generate_all_signals(self, stocks: List[str] = None) -> Dict:
        """為所有股票生成信號"""
        if stocks is None:
            stocks = list(self.stock_strategies.keys())
        
        signals = {}
        long_count = short_count = hold_count = 0
        
        for stock in stocks:
            result = self.generate_signal(stock)
            if result['success']:
                signals[stock] = result
                if result['signal'] == 'LONG':
                    long_count += 1
                elif result['signal'] == 'SHORT':
                    short_count += 1
                else:
                    hold_count += 1
        
        # 只統計 LONG 和 SHORT
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
    
    def save_signals(self, signals: Dict, filepath: Path = None):
        """保存信號到文件"""
        filepath = filepath or PROJECT_DIR / "signals" / f"signals_{datetime.now():%Y%m%d_%H%M%S}.json"
        filepath.parent.mkdir(exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)
        
        logger.info(f"信號已保存: {filepath}")
        return filepath


def main():
    """主函數"""
    print("=" * 80)
    print("           TradeMaster v2 - 實時信號生成器")
    print(f"           {datetime.now()}")
    print("=" * 80)
    
    generator = SignalGenerator()
    result = generator.generate_all_signals()
    
    overview = result['overview']
    signals = result['signals']
    
    # 檢查數據源
    sample = list(signals.values())[0] if signals else {}
    data_source = sample.get('data_source', '未知')
    
    print(f"\n📊 市場概覽 (數據源: {data_source}):")
    print(f"   總股票數: {overview['total_stocks']}")
    print(f"   🟢 LONG: {overview['long_count']}")
    print(f"   🔴 SHORT: {overview['short_count']}")
    print(f"   🟡 HOLD: {overview['hold_count']}")
    print(f"   📈 市場情緒: {overview['market_sentiment']} ({overview['long_ratio']}% LONG)")
    
    # 只顯示 LONG 和 SHORT 信號
    actionable = {k: v for k, v in signals.items() if v['signal'] != 'HOLD'}
    
    print(f"\n📋 可執行信號 (共 {len(actionable)} 個):")
    print("-" * 80)
    print(f"{'股票':<8} {'策略':<18} {'信號':<8} {'價格':<12} {'RSI':<8} {'夏普':<6}")
    print("-" * 80)
    
    for stock, sig in sorted(actionable.items()):
        emoji = "🟢" if sig['signal'] == 'LONG' else "🔴"
        print(f"{stock:<8} {sig['strategy']:<18} {emoji} {sig['signal']:<6} ${sig['price']:<10.2f} {sig['indicators']['RSI']:<7.1f} {sig['backtest_sharpe']:<6.2f}")
    
    print("-" * 80)
    print(f"🟡 HOLD 信號 ({overview['hold_count']} 個) 已隱藏")
    
    # 分開顯示 HOLD 信號
    holds = {k: v for k, v in signals.items() if v['signal'] == 'HOLD'}
    if holds:
        print(f"\n📋 不操作信號 (HOLD):")
        for stock, sig in sorted(holds.items()):
            print(f"   • {stock}: {sig['strategy']} ({sig['indicators']['RSI']:.1f} RSI)")
    
    filepath = generator.save_signals(result)
    print(f"\n✅ 完整信號已保存: {filepath}")
    
    return result


if __name__ == "__main__":
    main()
