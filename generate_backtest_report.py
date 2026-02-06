#!/usr/bin/env python3
"""
TradeMaster v2 - 快速回測報告生成器
功能：對所有股票執行回測，生成 Markdown 報告

報告命名規範：
- {YYYYMMDD}_backtest_{HHMM}.md

範例：20260206_backtest_0945.md

使用方法：
- 基本回測（快速）：python3 generate_backtest_report.py
- 完整回測+Walk-Forward：python3 generate_backtest_report.py --full
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

# 添加專案根目錄
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest import BacktestEngine, print_backtest_result
from core import PluginRegistry
from data import DataEngine


# 股票清單 - 測試版本（2 檔股票）
STOCKS = ["AAPL", "TSLA"]


def get_available_strategies():
    """獲取所有可用策略"""
    registry = PluginRegistry()
    
    # 發現策略插件
    strategies_path = PROJECT_DIR / "strategies"
    for category in strategies_path.iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    strategies = []
    for name, meta in registry.list_strategies():
        strategies.append({
            "name": name,
            "category": meta.category,
            "parameters": meta.parameters
        })
    
    return strategies


def extract_strategy_params(meta_parameters: dict) -> dict:
    """從參數定義中提取預設值"""
    params = {}
    for key, value in meta_parameters.items():
        if isinstance(value, dict) and 'default' in value:
            params[key] = value['default']
        elif isinstance(value, dict):
            params[key] = value.get('type', None)
        else:
            params[key] = value
    return params


def run_backtest_for_strategy_stock(strategy_cls, params, symbol, data, strategy_name):
    """為單一股票執行回測"""
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.001,
        kelly_fraction=0.5
    )
    
    try:
        strategy = strategy_cls(**params)
        result = engine.run(symbol, strategy, data, strategy_name)
        return result
    except Exception as e:
        print(f"   ⚠️ 回測失敗: {e}")
        return None


def run_walkforward_for_strategy_stock(strategy_cls, params, symbol, data, strategy_name):
    """為單一股票執行 Walk-Forward 分析"""
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.001,
        kelly_fraction=0.5
    )
    
    wf_engine = WalkForwardBacktest(
        engine=engine,
        train_window=252,  # 1年訓練
        test_window=63      # 3個月測試
    )
    
    try:
        strategy = strategy_cls(**params)
        result = wf_engine.run(symbol, strategy, data, strategy_name)
        return result
    except Exception as e:
        print(f"   ⚠️ Walk-Forward 失敗: {e}")
        return None


def generate_markdown_report(results: dict, strategies: list, filename: str, engine, full_mode: bool = False):
    """生成 Markdown 格式報告"""
    
    mode_note = "（快速版）" if not full_mode else "（完整版）"
    
    report = f"""# TradeMaster v2 - 回測報告{mode_note}

## 📋 報告資訊

| 項目 | 值 |
|------|-----|
| 報告名稱 | {filename} |
| 生成時間 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
| 股票數量 | {len(STOCKS)} |
| 策略數量 | {len(strategies)} |
| 起始資金 | $100,000 |
| 半凱利係數 | 0.5 |

---

## 📊 策略總覽

| # | 策略名稱 | 類別 |
|---|---------|------|
"""
    
    for i, s in enumerate(strategies, 1):
        report += f"| {i} | {s['name']} | {s['category']} |\n"
    
    report += """
---

## 🎯 最佳策略推薦（按夏普比率排序）

"""
    
    # 找出最佳策略
    all_results = []
    for symbol in results:
        for strategy_name, data in results[symbol].items():
            if data and data.get('backtest'):
                all_results.append({
                    'symbol': symbol,
                    'strategy': strategy_name,
                    'sharpe': data['backtest'].get('sharpe', 0),
                    'return': data['backtest'].get('total_return', 0),
                    'max_dd': data['backtest'].get('max_drawdown', 0),
                    'win_rate': data['backtest'].get('win_rate', 0),
                    'kelly': data['backtest'].get('kelly_position', 0)
                })
    
    if all_results:
        all_results.sort(key=lambda x: x['sharpe'], reverse=True)
        
        report += "| 排名 | 股票 | 策略 | 夏普比率 | 總報酬 | 最大回撤 | 勝率 | 凱利倉位 |\n"
        report += "|------|------|------|---------|--------|---------|------|---------|\n"
        
        for i, r in enumerate(all_results[:20], 1):
            report += f"| {i} | {r['symbol']} | {r['strategy']} | {r['sharpe']:.2f} | {r['return']:.2%} | {r['max_dd']:.2%} | {r['win_rate']:.2%} | {r['kelly']:.1%} |\n"
    
    report += """
---

## 📈 各股票詳細結果

"""
    
    for symbol in STOCKS:
        if symbol not in results:
            continue
            
        report += f"### {symbol}\n\n"
        
        # 找出此股票的最佳策略
        symbol_results = []
        for strategy_name, data in results[symbol].items():
            if data and data.get('backtest'):
                symbol_results.append({
                    'strategy': strategy_name,
                    'sharpe': data['backtest'].get('sharpe', 0),
                    'return': data['backtest'].get('total_return', 0),
                    'max_dd': data['backtest'].get('max_drawdown', 0),
                    'win_rate': data['backtest'].get('win_rate', 0),
                    'kelly': data['backtest'].get('kelly_position', 0),
                    'trades': data['backtest'].get('total_trades', 0)
                })
        
        if not symbol_results:
            report += "* 無回測數據*\n\n"
            continue
        
        # 最佳策略
        symbol_results.sort(key=lambda x: x['sharpe'], reverse=True)
        best = symbol_results[0]
        
        report += f"**最佳策略：** {best['strategy']}\n\n"
        report += f"| 指標 | 值 |\n"
        report += f"|------|-----|\n"
        report += f"| 夏普比率 | {best['sharpe']:.2f} |\n"
        report += f"| 總報酬 | {best['return']:.2%} |\n"
        report += f"| 最大回撤 | {best['max_dd']:.2%} |\n"
        report += f"| 勝率 | {best['win_rate']:.2%} |\n"
        report += f"| 交易次數 | {best['trades']} |\n"
        report += f"| 凱利倉位 | {best['kelly']:.1%} |\n"
        
        # 所有策略對比表
        report += f"\n**所有策略對比：**\n\n"
        report += f"| 策略 | 夏普 | 報酬 | 最大回撤 | 勝率 | 交易次數 |\n"
        report += f"|------|------|------|---------|------|---------|\n"
        
        for sr in symbol_results:
            report += f"| {sr['strategy']} | {sr['sharpe']:.2f} | {sr['return']:.2%} | {sr['max_dd']:.2%} | {sr['win_rate']:.2%} | {sr['trades']} |\n"
        
        report += "\n---\n\n"
    
    # 風險評估摘要
    report += """
## 🛡️ 風險評估摘要

### 高風險策略（最大回撤 > 20%）
"""
    
    high_risk = [r for r in all_results if r['max_dd'] > 0.20]
    if high_risk:
        report += "| 股票 | 策略 | 最大回撤 | 報酬 |\n"
        report += "|------|------|---------|------|\n"
        for r in high_risk:
            report += f"| {r['symbol']} | {r['strategy']} | {r['max_dd']:.2%} | {r['return']:.2%} |\n"
    else:
        report += "* 無高風險策略 *\n"
    
    report += """
### 低夏普策略（夏普 < 0.5）
"""
    
    low_sharpe = [r for r in all_results if r['sharpe'] < 0.5]
    if low_sharpe:
        report += "| 股票 | 策略 | 夏普比率 | 報酬 |\n"
        report += "|------|------|---------|------|\n"
        for r in low_sharpe[:10]:
            report += f"| {r['symbol']} | {r['strategy']} | {r['sharpe']:.2f} | {r['return']:.2%} |\n"
    else:
        report += "* 無低夏普策略 *\n"
    
    # 結論
    # 策略有效性過濾
    print("\n🔍 過濾策略...")
    filter_result = engine.filter_strategies(results)
    print(f"   分析: {filter_result['summary']['total_analyzed']} 個策略-股票組合")
    print(f"   通過: {filter_result['summary']['passed']} 個")
    print(f"   失敗: {filter_result['summary']['failed']} 個")
    print(f"   通過率: {filter_result['summary']['pass_rate']:.1%}")

    # 過濾後的有效策略
    valid_results = list(filter_result['valid'].values())
    valid_results.sort(key=lambda x: x.get('sharpe', 0), reverse=True)
    
    report += """
---

## ✅ 策略有效性過濾結果

| 指標 | 值 |
|------|-----|
| 總分析數 | {total} |
| 通過數 | {passed} |
| 失敗數 | {failed} |
| 通過率 | {rate:.1%} |
| 最小交易樣本 | {min_trades} 筆 |
| 夏普門檻 | >= {sharpe:.1f} |

### 通過過濾的策略（按夏普排序）：

""".format(
        total=filter_result['summary']['total_analyzed'],
        passed=filter_result['summary']['passed'],
        failed=filter_result['summary']['failed'],
        rate=filter_result['summary']['pass_rate'],
        min_trades=engine.MIN_TRADES_THRESHOLD,
        sharpe=engine.MIN_SHARPE_THRESHOLD
    )

    if valid_results:
        report += "| 排名 | 股票 | 策略 | 夏普 | 報酬 | 最大回撤 | 勝率 | 交易次數 |\n"
        report += "|------|------|------|------|------|---------|------|---------|\n"
        for i, r in enumerate(valid_results[:15], 1):
            report += f"| {i} | {r['symbol']} | {r['strategy']} | {r.get('sharpe', 0):.2f} | {r.get('total_return', 0):.2%} | {r.get('max_drawdown', 0):.2%} | {r.get('win_rate', 0):.2%} | {r.get('total_trades', 0)} |\n"
    else:
        report += "* 無策略通過有效性過濾 *\n"

    # Monte Carlo 模擬摘要（如果有執行）
    if 'monte_carlo' in locals():
        mc_result = monte_carlo.run(symbol, strategy, data, strategy_name)
        report += f"""

---

## 🎲 Monte Carlo 模擬結果

| 指標 | 基準 | 平均 | 5% 分位 | 95% 分位 |
|------|------|------|---------|---------|
| 報酬 | {mc_result['base_return']:.2%} | {mc_result['return_mean']:.2%} | {mc_result['return_5pct']:.2%} | {mc_result['return_95pct']:.2%} |
| 最大回撤 | {mc_result['base_max_dd']:.2%} | {mc_result['dd_mean']:.2%} | {mc_result['dd_5pct']:.2%} | - |

**獲利機率:** {mc_result['probability_of_profit']:.1%}

"""
    
    if all_results:
        # 找出夏普 > 0.8 且最大回撤 < 15% 的策略
        recommended = [r for r in all_results if r['sharpe'] > 0.8 and r['max_dd'] < 0.15]
        
        if recommended:
            recommended.sort(key=lambda x: (x['sharpe'], -x['max_dd']))
            report += "| 股票 | 策略 | 夏普 | 最大回撤 | 報酬 |\n"
            report += "|------|------|------|---------|------|\n"
            for r in recommended[:10]:
                report += f"| {r['symbol']} | {r['strategy']} | {r['sharpe']:.2f} | {r['max_dd']:.2%} | {r['return']:.2%} |\n"
        else:
            report += "* 無符合高夏普、低回撤標準的策略 *\n"
    
    report += f"""
---

*報告生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
*TradeMaster v2 - 量化交易系統*
"""
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="TradeMaster v2 - 回測報告生成器"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="執行完整回測（含 Walk-Forward 分析，較慢）"
    )
    parser.add_argument(
        "--years",
        type=str,
        default="2024-2025",
        help="數據年份範圍，例如: 2024-2025 (預設), 2023-2024, 2020-2025"
    )
    args = parser.parse_args()
    
    # 解析年份範圍
    try:
        start_year, end_year = map(int, args.years.split('-'))
        start_date = pd.Timestamp(f"{start_year}-01-01")
        end_date = pd.Timestamp(f"{end_year}-12-31")
        date_range_note = f"{start_year}-{end_year}"
    except:
        # 預設使用最近 2 年數據
        end_date = pd.Timestamp.now()
        start_date = end_date - pd.DateOffset(years=2)
        date_range_note = f"{start_date.year}-{end_date.year}"
        print(f"   ⚠️ 使用預設日期範圍: {date_range_note}")
    
    print("=" * 80)
    print("           TradeMaster v2 - 回測報告生成器")
    print(f"           {datetime.now()}")
    print(f"           模式: {'完整版 (含 Walk-Forward)' if args.full else '快速版'}")
    print("=" * 80)
    
    # 生成報告文件名稱
    timestamp = datetime.now()
    report_filename = f"{timestamp.strftime('%Y%m%d')}_backtest_{timestamp.strftime('%H%M')}.md"
    report_path = PROJECT_DIR / "docs" / report_filename
    
    print(f"\n📁 報告將保存至: {report_path}")
    
    # 確保 docs 目錄存在
    (PROJECT_DIR / "docs").mkdir(exist_ok=True)
    
    # 獲取可用策略
    print("\n📊 載入策略...")
    strategies = get_available_strategies()
    print(f"   找到 {len(strategies)} 個策略")
    
    # 初始化數據引擎
    print("\n📈 載入數據...")
    data_engine = DataEngine()
    
    # 初始化回測引擎
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.0015,
        slippage=0.001,
        kelly_fraction=0.25
    )
    
    # 儲存結果
    results = {}

    # 解析函數 - 移到全域
    def parse_backtest_result(result):
        if result is None:
            return None
        return {
            'sharpe': result.sharpe_ratio,
            'total_return': result.total_return,
            'max_drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'kelly_position': result.kelly_position,
            'total_trades': result.total_trades,
            'equity_curve': result.equity_curve,
            'is_statistically_valid': getattr(result, 'is_statistically_valid', False),
            'meets_sharpe_threshold': getattr(result, 'meets_sharpe_threshold', False)
        }
    
    # 統計
    total_tests = len(STOCKS) * len(strategies)
    current = 0
    
    print(f"\n🔍 開始回測 ({total_tests} 個測試)...")
    print("-" * 80)
    
    for symbol in STOCKS:
        print(f"\n📊 {symbol}")
        results[symbol] = {}
        
        # 獲取數據
        data = data_engine.get_daily_data(symbol)
        if data is None:
            print(f"   ⚠️ 無法獲取 {symbol} 數據")
            continue
        
        # 過濾日期範圍
        if start_date is not None and end_date is not None:
            data = data[(data.index >= start_date) & (data.index <= end_date)]
            print(f"   📅 {symbol}: {len(data)} 天 ({date_range_note})")
        else:
            print(f"   📅 {symbol}: {len(data)} 天 (全部)")
        
        for strategy_info in strategies:
            current += 1
            strategy_name = strategy_info['name']
            params = extract_strategy_params(strategy_info['parameters'])
            
            try:
                # 獲取策略類
                registry = PluginRegistry()
                strategies_path = PROJECT_DIR / "strategies"
                for category in strategies_path.iterdir():
                    if category.is_dir():
                        registry.discover_plugins(str(category))
                
                strategy_cls = registry.get_strategy(strategy_name)
                if not strategy_cls:
                    continue
                
                # 創建策略實例
                strategy = strategy_cls(**params)
                
                # 回測
                print(f"   [{current}/{total_tests}] {strategy_name}...", end=" ", flush=True)
                backtest_result = engine.run(symbol, strategy, data, strategy_name)
                
                # 計算夏普比率
                if backtest_result.volatility > 0:
                    sharpe = (backtest_result.annualized_return - 0.02) / backtest_result.volatility
                else:
                    sharpe = 0
                
                # 保存結果（不含 Walk-Forward）
                results[symbol][strategy_name] = {
                    'backtest': {
                        'total_return': backtest_result.total_return,
                        'annualized_return': backtest_result.annualized_return,
                        'max_drawdown': backtest_result.max_drawdown,
                        'volatility': backtest_result.volatility,
                        'sharpe': sharpe,
                        'win_rate': backtest_result.win_rate,
                        'total_trades': backtest_result.total_trades,
                        'kelly_position': backtest_result.kelly_position,
                        'profit_factor': backtest_result.profit_factor,
                        'average_holding_days': backtest_result.average_holding_days
                    }
                }
                
                print(f"✓ 夏普={sharpe:.2f}, 報酬={backtest_result.total_return:.2%}")
                
            except Exception as e:
                print(f"✗ 錯誤: {e}")
                continue
    
    print("\n" + "-" * 80)
    print("✅ 回測完成！")
    
    # 生成報告
    print(f"\n📝 生成報告...")
    report_content = generate_markdown_report(results, strategies, report_filename, engine, full_mode=args.full)
    
    # 保存報告
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    print(f"   報告已保存: {report_path}")
    
    # 打印摘要
    print("\n" + "=" * 80)
    print("📊 回測摘要")
    print("=" * 80)
    
    all_results = []
    for symbol in results:
        for strategy_name, data in results[symbol].items():
            if data and data['backtest']:
                all_results.append({
                    'symbol': symbol,
                    'strategy': strategy_name,
                    'sharpe': data['backtest']['sharpe'],
                    'return': data['backtest']['total_return'],
                    'max_dd': data['backtest']['max_drawdown']
                })
    
    if all_results:
        all_results.sort(key=lambda x: x['sharpe'], reverse=True)
        
        print(f"\n🏆 最佳結果 (Top 10):")
        for i, r in enumerate(all_results[:10], 1):
            print(f"   {i}. {r['symbol']} - {r['strategy']}")
            print(f"      夏普: {r['sharpe']:.2f} | 報酬: {r['return']:.2%} | 最大回撤: {r['max_dd']:.2%}")
    
    print(f"\n📁 完整報告: {report_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
