#!/usr/bin/env python3
"""
TradeMaster v2 - 策略分析腳本

使用方法:
1. 先下載數據: python3 download_data.py --download
2. 再運行分析: python3 analyze_strategies.py

數據會從本地文件讀取，避免 API rate limit
"""

import pandas as pd
import numpy as np
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# 添加路徑
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data" / "historical"
DB_PATH = PROJECT_ROOT / "data" / "trademaster.db"

# 配置
# 2026-02-12: 優化股票池 - 剔除 TSLA、INTC、RKLB（高波動/下降趨勢股票）
# 專注於：科技巨頭、半導體龍頭、穩定成長股
STOCKS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "META",  # 科技巨頭
    "TSM", "AMD", "MU",                        # 半導體
    "UBER", "ORCL",                            # 軟體/服務
]
    "COIN",                                             # 加密
    "RKLB"                                              # 太空
]

WF_TRAIN_DAYS = 252
WF_TEST_DAYS = 63
WF_MIN_RATIO = 0.5
BACKTEST_PERIOD = "2y"


def discover_plugins():
    """發現插件"""
    from core import PluginRegistry
    
    registry = PluginRegistry()
    
    for category in (PROJECT_ROOT / "indicators").iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    for category in (PROJECT_ROOT / "strategies").iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    registry.discover_plugins(str(PROJECT_ROOT / "risk_rules"))
    
    return registry


def load_local_data(symbol: str) -> pd.DataFrame:
    """從本地讀取數據 (CSV 優先)"""
    csv_path = DATA_DIR / f"{symbol}.csv"
    
    if csv_path.exists():
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        print(f"   📄 {symbol}: {len(df)} 天 (本地)")
        return df
    
    # 嘗試 SQLite
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(f"SELECT * FROM stock_{symbol}", conn, index_col='index')
        df.index = pd.to_datetime(df.index)
        print(f"   🗄️ {symbol}: {len(df)} 天 (SQLite)")
        return df
    except:
        pass
    finally:
        conn.close()
    
    print(f"   ❌ {symbol}: 本地無數據")
    return None


def run_walkforward(registry, df, strategy_name):
    """運行 Walk-Forward"""
    from backtest import BacktestEngine
    
    cls = registry.get_strategy(strategy_name)
    if cls is None:
        return None
    
    meta = registry.get_metadata(strategy_name)
    params = meta.parameters if meta else {}
    
    engine = BacktestEngine()
    results = []
    
    i = WF_TRAIN_DAYS
    while i + WF_TEST_DAYS <= len(df):
        train_data = df.iloc[i-WF_TRAIN_DAYS:i]
        test_data = df.iloc[i:i+WF_TEST_DAYS]
        
        train_return = (train_data["Close"].iloc[-1] / train_data["Close"].iloc[0]) - 1
        test_result = engine.run("BACKTEST", cls(**params), test_data, f"{strategy_name}_WF")
        
        results.append({
            "train_return": train_return,
            "test_return": test_result.total_return,
            "test_dd": test_result.max_drawdown,
            "test_wr": test_result.win_rate
        })
        
        i += WF_TEST_DAYS
    
    if not results:
        return None
    
    returns = [r["test_return"] for r in results]
    train_returns = [r["train_return"] for r in results]
    
    avg_train = np.mean(train_returns) if train_returns else 0.15
    avg_test = np.mean(returns) if returns else 0
    wf_ratio = avg_test / avg_train if avg_train > 0 else 0
    
    return {
        "strategy": strategy_name,
        "wf_ratio": wf_ratio,
        "mean_return": avg_test,
        "stability": 1 - (np.std(returns) / (abs(np.mean(returns)) + 0.001))
    }


def run_backtest(registry, df, strategy_name):
    """運行回測"""
    from backtest import BacktestEngine
    
    cls = registry.get_strategy(strategy_name)
    if cls is None:
        return None
    
    meta = registry.get_metadata(strategy_name)
    params = meta.parameters if meta else {}
    
    engine = BacktestEngine()
    result = engine.run("BACKTEST", cls(**params), df, strategy_name)
    
    equity = result.equity_curve
    
    if equity is not None and len(equity) > 1:
        monthly = equity.resample('ME').last().pct_change().dropna()
        monthly_return = monthly.mean()
        monthly_std = monthly.std()
        sharpe = (monthly_return / monthly_std) * np.sqrt(12) if monthly_std > 0 else 0
        max_dd = abs(((equity - equity.expanding().max()) / equity.expanding().max()).min())
    else:
        monthly_return = 0
        sharpe = 0
        max_dd = result.max_drawdown
    
    return {
        "strategy": strategy_name,
        "total_return": result.total_return,
        "annualized": result.annualized_return,
        "monthly": monthly_return,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "win_rate": result.win_rate,
        "trades": result.total_trades
    }


def analyze_stock(symbol: str, strategies: list) -> dict:
    """分析單一股票"""
    print(f"\n📊 {symbol}")
    print("-" * 50)
    
    # 從本地讀取數據
    df = load_local_data(symbol)
    if df is None:
        return {"symbol": symbol, "error": "No data"}
    
    # Walk-Forward
    print("   🔍 Walk-Forward...")
    wf_results = []
    
    for i, strategy_name in enumerate(strategies):
        if i % 5 == 0:
            time.sleep(0.5)  # 輕微延遲
    
    for strategy_name in strategies:
        try:
            wf = run_walkforward(registry, df, strategy_name)
            if wf:
                status = "✅" if wf["wf_ratio"] >= WF_MIN_RATIO else "❌"
                print(f"      {status} {strategy_name}: WF={wf['wf_ratio']:.2f}")
                wf_results.append(wf)
        except Exception as e:
            print(f"      ⚠️ {strategy_name}: {e}")
    
    valid = [r for r in wf_results if r["wf_ratio"] >= WF_MIN_RATIO]
    print(f"\n   ✅ 有效: {len(valid)}/{len(wf_results)}")
    
    if not valid:
        return {"symbol": symbol, "wf_results": wf_results, "bt_results": [], "best": None}
    
    # Backtest
    print("\n   📈 Backtest...")
    bt_results = []
    
    for wf in valid:
        strategy_name = wf["strategy"]
        try:
            bt = run_backtest(registry, df, strategy_name)
            if bt:
                bt_results.append(bt)
                print(f"      📊 {strategy_name}: Sharpe={bt['sharpe']:.2f}, Return={bt['annualized']:.1%}")
        except Exception as e:
            print(f"      ⚠️ {strategy_name}: {e}")
    
    bt_results.sort(key=lambda x: x["sharpe"], reverse=True)
    
    return {
        "symbol": symbol,
        "wf_results": wf_results,
        "bt_results": bt_results,
        "best": bt_results[0] if bt_results else None
    }


def generate_report(all_results: dict) -> str:
    """生成報告"""
    from datetime import datetime
    
    lines = []
    lines.append("=" * 100)
    lines.append("                    TradeMaster v2 - 策略分析報告")
    lines.append(f"                    生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 100)
    lines.append("")
    
    # 收集最佳策略
    all_best = []
    for symbol, data in all_results.items():
        if data.get("best"):
            bt = data["best"]
            all_best.append({
                "symbol": symbol,
                "strategy": bt["strategy"],
                "annualized": bt["annualized"],
                "monthly": bt["monthly"],
                "sharpe": bt["sharpe"],
                "max_dd": bt["max_dd"],
                "win_rate": bt["win_rate"],
                "trades": bt["trades"]
            })
    
    all_best.sort(key=lambda x: x["sharpe"], reverse=True)
    
    # 摘要表格
    lines.append("🏆 最佳策略總覽 (按夏普比率排序)")
    lines.append("-" * 110)
    lines.append(f"{'#':<3} {'股票':<8} {'策略':<30} {'年化':>7} {'月化':>7} {'夏普':>6} {'最大回撤':>8} {'勝率':>6} {'買賣次數':>8}")
    lines.append("-" * 110)
    
    for i, item in enumerate(all_best, 1):
        lines.append(
            f"{i:<3} {item['symbol']:<8} {item['strategy']:<30} "
            f"{item['annualized']:>6.1%} {item['monthly']:>6.2%} "
            f"{item['sharpe']:>6.2f} {item['max_dd']:>7.1%} "
            f"{item['win_rate']:>5.1%} {item['trades']:>7}"
        )
    
    lines.append("")
    lines.append("=" * 100)
    lines.append("                           報告結束")
    lines.append("=" * 100)
    
    return "\n".join(lines)


def main():
    print("\n" + "=" * 80)
    print("TradeMaster v2 - 策略分析")
    print("=" * 80)
    print("\n💡 提示: 先運行 python3 download_data.py --download 下載數據")
    
    global registry
    registry = discover_plugins()
    strategies = [name for name, _ in registry.list_strategies()]
    
    print(f"\n📊 策略數: {len(strategies)}")
    print(f"📈 股票數: {len(STOCKS)}")
    
    all_results = {}
    
    for symbol in STOCKS:
        result = analyze_stock(symbol, strategies)
        all_results[symbol] = result
    
    # 生成報告
    report = generate_report(all_results)
    
    # 保存
    report_file = PROJECT_ROOT / "strategy_analysis_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    
    print("\n" + "=" * 80)
    print(f"✅ 報告已保存: {report_file}")
    print("=" * 80)
    print("\n" + report)
    
    return all_results


if __name__ == "__main__":
    main()
