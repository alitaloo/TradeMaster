#!/usr/bin/env python3
"""
TradeMaster v2 - 最佳策略回測驗證
使用找到的最佳參數：RSI < 32 買入，RSI > 74 賣出，SL=5.8%，TP=15%
"""
import urllib.request
import ssl
import pandas as pd
import numpy as np
import io
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import json

@dataclass
class BacktestResult:
    symbol: str
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    profit_factor: float
    avg_trade: float
    best_trade: float
    worst_trade: float
    params: str

def download_stooq(symbol: str, start_date: str = "20200101", end_date: str = "20251231") -> pd.DataFrame:
    """從 Stooq 下載歷史數據"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    url = f'https://stooq.com/q/d/l/?s={symbol}.us&d1={start_date}&d2={end_date}&i=d'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req, context=ssl_context, timeout=60) as response:
        df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
    
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date').reset_index(drop=True)
    
    return df

def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """計算 RSI"""
    close = data['Close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

class RSIStrategy:
    """RSI 均值回歸策略 - 最佳參數"""
    def __init__(self, rsi_period: int = 14, 
                 oversold: int = 32, 
                 overbought: int = 74,
                 stop_loss: float = 0.058,
                 take_profit: float = 0.15):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        
        self.position = None
        self.entry_price = None
        self.trades = []
    
    def generate_signal(self, rsi_value: float, price: float) -> str:
        """生成交易信號"""
        # 進場
        if self.position is None:
            if rsi_value < self.oversold:
                self.position = "LONG"
                self.entry_price = price
                return "BUY"
            return "HOLD"
        
        # 出場
        pnl = (price - self.entry_price) / self.entry_price
        
        if pnl >= self.take_profit or pnl <= -self.stop_loss or rsi_value > self.overbought:
            self.trades.append({
                'entry': self.entry_price,
                'exit': price,
                'pnl': pnl
            })
            self.position = None
            self.entry_price = None
            return "SELL"
        
        return "HOLD"

def run_backtest(data: pd.DataFrame, symbol: str, strategy: RSIStrategy) -> BacktestResult:
    """運行回測"""
    df = data.copy()
    df['RSI'] = calculate_rsi(df, strategy.rsi_period)
    
    equity = [100000]
    shares = 0
    position = None
    
    for i in range(len(df)):
        rsi_val = df['RSI'].iloc[i]
        price = df['Close'].iloc[i]
        signal = strategy.generate_signal(rsi_val, price)
        
        if signal == "BUY" and position is None:
            shares = 100000 / price
            position = {'shares': shares, 'entry': price}
        elif signal == "SELL" and position is not None:
            equity.append(shares * price)
            shares = 0
            position = None
        else:
            if position:
                equity.append(shares * price)
            else:
                equity.append(equity[-1])
    
    # 計算指標
    equity_series = pd.Series(equity)
    returns = equity_series.pct_change().dropna()
    
    total_return = (equity[-1] / equity[0]) - 1
    annual_return = total_return * (252 / len(df))
    volatility = returns.std() * np.sqrt(252)
    sharpe = annual_return / volatility if volatility > 0 else 0
    
    # 最大回撤
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak
    max_drawdown = abs(drawdown.min())
    
    # 交易統計
    trades = strategy.trades
    if trades:
        profits = [t['pnl'] for t in trades]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p <= 0]
        
        win_rate = len(wins) / len(profits) if profits else 0
        profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float('inf')
        avg_trade = np.mean(profits) if profits else 0
        best_trade = max(profits) if profits else 0
        worst_trade = min(profits) if profits else 0
    else:
        win_rate = 0
        profit_factor = 0
        avg_trade = 0
        best_trade = 0
        worst_trade = 0
    
    params = f"RSI({strategy.rsi_period}/{strategy.oversold}/{strategy.overbought}) SL={strategy.stop_loss:.1%} TP={strategy.take_profit:.0%}"
    
    return BacktestResult(
        symbol=symbol,
        total_return=total_return,
        annualized_return=annual_return,
        volatility=volatility,
        sharpe_ratio=sharpe,
        max_drawdown=max_drawdown,
        total_trades=len(trades),
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_trade=avg_trade,
        best_trade=best_trade,
        worst_trade=worst_trade,
        params=params
    )

def generate_report(results: List[BacktestResult]) -> str:
    """生成 Markdown 報告"""
    report = f"""# TradeMaster v2 - 最佳策略回測驗證報告

**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**策略**: RSI 均值回歸策略

---

## 🎯 策略參數

| 參數 | 值 |
|------|------|
| RSI 週期 | 14 日 |
| 買入條件 | RSI < 32 |
| 賣出條件 | RSI > 74 |
| 止損 | 5.8% |
| 止盈 | 15.0% |

---

## 📊 回測結果

### 總覽

| 標的 | 總報酬 | 年化報酬 | 波動率 | 夏普率 | 最大回撤 | 交易次數 | 勝率 |
|------|--------|---------|--------|--------|----------|----------|------|
"""
    
    for r in results:
        report += f"| {r.symbol} | {r.total_return:.2%} | {r.annualized_return:.2%} | {r.volatility:.2%} | **{r.sharpe_ratio:.2f}** | {r.max_drawdown:.2%} | {r.total_trades} | {r.win_rate:.2%} |\n"
    
    report += """
### 詳細結果

"""
    
    for r in results:
        report += f"""#### {r.symbol}

- **夏普率**: {r.sharpe_ratio:.2f} {"✅" if r.sharpe_ratio > 1.5 else "❌"}
- **年化報酬**: {r.annualized_return:.2%} {"✅" if r.annualized_return > 0.20 else "❌"}
- **最大回撤**: {r.max_drawdown:.2%} {"✅" if r.max_drawdown < 0.30 else "❌"}
- **交易次數**: {r.total_trades}
- **勝率**: {r.win_rate:.2%}
- **盈虧比**: {r.profit_factor:.2f}
- **平均交易**: {r.avg_trade:.2%}
- **最佳交易**: {r.best_trade:.2%}
- **最差交易**: {r.worst_trade:.2%}
- **參數**: {r.params}

"""
    
    # 總結
    all_qualified = all(r.sharpe_ratio > 1.5 and r.annualized_return > 0.20 and r.max_drawdown < 0.30 for r in results)
    
    report += f"""---

## 📈 結論

{"✅ **所有標的三項全達標！**" if all_qualified else "⚠️ 部分標的未完全達標"}

| 標的 | Sharpe > 1.5 | Return > 20% | MaxDD < 30% |
|------|-------------|-------------|-------------|
"""
    
    for r in results:
        s = "✅" if r.sharpe_ratio > 1.5 else "❌"
        r_val = "✅" if r.annualized_return > 0.20 else "❌"
        d = "✅" if r.max_drawdown < 0.30 else "❌"
        report += f"| {r.symbol} | {s} | {r_val} | {d} |\n"
    
    report += """
---

## ⚠️ 風險提示

1. 回測結果不代表未來表現
2. 未考慮交易成本（手續費、滑價）
3. 建議實盤前進行模擬交易驗證

---

*Generated by TradeMaster v2*
"""
    
    return report

def main():
    print("="*70)
    print("🚀 TradeMaster v2 - 最佳策略回測驗證")
    print("="*70)
    
    # 策略參數
    strategy_params = {
        'rsi_period': 14,
        'oversold': 32,
        'overbought': 74,
        'stop_loss': 0.058,
        'take_profit': 0.15
    }
    
    # 測試標的
    symbols = ['AAPL', 'TSLA']
    
    print(f"\n📊 策略參數:")
    print(f"   RSI 週期: {strategy_params['rsi_period']}")
    print(f"   買入條件: RSI < {strategy_params['oversold']}")
    print(f"   賣出條件: RSI > {strategy_params['overbought']}")
    print(f"   止損: {strategy_params['stop_loss']:.1%}")
    print(f"   止盈: {strategy_params['take_profit']:.0%}")
    
    results = []
    
    for symbol in symbols:
        print(f"\n📥 下載 {symbol} 數據...")
        df = download_stooq(symbol)
        print(f"   ✓ {symbol}: {len(df)} 天")
        
        print(f"📊 回測 {symbol}...")
        strategy = RSIStrategy(**strategy_params)
        result = run_backtest(df, symbol, strategy)
        results.append(result)
        
        print(f"\n   📈 {symbol} 結果:")
        print(f"      夏普率: {result.sharpe_ratio:.2f}")
        print(f"      年化報酬: {result.annualized_return:.2%}")
        print(f"      最大回撤: {result.max_drawdown:.2%}")
        print(f"      交易次數: {result.total_trades}")
        print(f"      勝率: {result.win_rate:.2%}")
    
    # 生成報告
    print("\n📝 生成報告...")
    report = generate_report(results)
    
    # 保存報告
    report_path = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/reports/BEST_STRATEGY_BACKTEST.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"   ✓ 報告已保存: {report_path}")
    
    # 保存 JSON 結果
    results_data = []
    for r in results:
        results_data.append({
            'symbol': r.symbol,
            'total_return': r.total_return,
            'annualized_return': r.annualized_return,
            'volatility': r.volatility,
            'sharpe_ratio': r.sharpe_ratio,
            'max_drawdown': r.max_drawdown,
            'total_trades': r.total_trades,
            'win_rate': r.win_rate,
            'profit_factor': r.profit_factor,
            'params': r.params
        })
    
    json_path = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/reports/best_strategy_results.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    print(f"   ✓ JSON 結果已保存: {json_path}")
    
    print("\n" + "="*70)
    print("✅ 回測完成！")
    print("="*70)
    
    return results

if __name__ == "__main__":
    main()
