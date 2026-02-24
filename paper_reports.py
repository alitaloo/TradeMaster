#!/usr/bin/env python3
"""
Paper Trading Reports - 報告與監控
每日推送到 Successor Bot、模擬報告、命中率追蹤、回測對比
"""
import os
import sys
from typing import Dict, List
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    PaperDailySummary, PaperSignalStats, PaperPerformance,
    PaperPosition, PaperOrder, SystemConfig
)
from config.database import get_db_cursor


# ========== 5.1 每日推送到 Successor Bot ==========

def push_paper_daily_summary() -> Dict:
    """
    每日推送到 Successor Bot
    
    Returns:
        dict: 推送結果
    """
    from paper_trading_portfolio import get_paper_total_assets, update_position_prices
    
    # 更新持倉價格
    update_position_prices()
    
    # 計算總資產
    assets = get_paper_total_assets()
    
    # 統計當日成交
    today = date.today()
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT 
                COUNT(*) as trade_count,
                SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                SUM(CASE WHEN signal_type = 'SELL' THEN 1 ELSE 0 END) as sell_count
            FROM signals 
            WHERE status IN ('SENT', 'PROCESSING', 'EXECUTED') 
            AND DATE(created_at) = %s
        """, (today,))
        row = cursor.fetchone()
        trade_count = row['trade_count'] or 0
        buy_count = row['buy_count'] or 0
        sell_count = row['sell_count'] or 0
    
    # 組合成推播訊息
    message = f"""📊 **模擬交易每日報告** - {today}

💰 **總資產**: ${assets['total']:,.2f}
💵 現金: ${assets['cash']:,.2f}
📈 持倉市值: ${assets['market_value']:,.2f}

📈 **損益**:
   未實現: ${assets['unrealized_pnl']:,.2f} ({assets.get('unrealized_pnl_pct', 0):.2f}%)
   已實現: ${assets['realized_pnl']:,.2f}

📊 **交易統計**:
   總成交: {trade_count}
   買入: {buy_count}
   賣出: {sell_count}
   
持倉: {assets['position_count']} 檔
"""
    
    # TODO: 推送到 Successor Bot
    # 這裡應該呼叫 Successor Bot API
    
    return {
        'success': True,
        'message': message,
        'assets': assets,
        'trade_count': trade_count
    }


# ========== 5.2 模擬報告 (寫入 MySQL) ==========

def generate_paper_report() -> Dict:
    """
    生成模擬報告並寫入 MySQL
    
    Returns:
        dict: 報告結果
    """
    from paper_trading_portfolio import get_paper_total_assets, update_position_prices
    
    today = date.today()
    
    # 更新持倉價格
    update_position_prices()
    
    # 計算總資產
    assets = get_paper_total_assets()
    
    # 統計總成交
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN order_type = 'BUY' THEN 1 ELSE 0 END) as buy_trades,
                SUM(CASE WHEN order_type = 'SELL' THEN 1 ELSE 0 END) as sell_trades,
                SUM(filled_quantity) as total_shares,
                SUM(filled_quantity * filled_price) as total_value
            FROM paper_orders 
            WHERE status = 'filled'
        """)
        row = cursor.fetchone()
        total_trades = row['total_trades'] or 0
        buy_trades = row['buy_trades'] or 0
        sell_trades = row['sell_trades'] or 0
        total_shares = row['total_shares'] or 0
        total_value = float(row['total_value'] or 0)
    
    # 寫入 paper_daily_summary
    summary = PaperDailySummary(
        date=today,
        total_value=assets['total'],
        cash=assets['cash'],
        market_value=assets['market_value'],
        unrealized_pnl=assets['unrealized_pnl'],
        realized_pnl=assets['realized_pnl'],
        daily_pnl=assets['unrealized_pnl'],
        trade_count=total_trades,
        buy_count=buy_trades,
        sell_count=sell_trades
    )
    summary.save()
    
    # 生成 Markdown 報告
    report = f"""# 模擬交易報告 - {today}

## 總資產
- 現金: ${assets['cash']:,.2f}
- 持倉市值: ${assets['market_value']:,.2f}
- 總資產: ${assets['total']:,.2f}

## 損益
- 未實現損益: ${assets['unrealized_pnl']:,.2f} ({assets.get('unrealized_pnl_pct', 0):.2f}%)
- 已實現損益: ${assets['realized_pnl']:,.2f}

## 交易統計
- 總成交筆數: {total_trades}
- 買入筆數: {buy_trades}
- 賣出筆數: {sell_trades}
- 總股數: {total_shares}
- 總成交金額: ${total_value:,.2f}

## 持倉
"""
    # 添加持倉列表
    positions = PaperPosition.find_all()
    for pos in positions:
        report += f"- {pos.symbol}: {pos.quantity}股 @ ${pos.current_price} (成本: ${pos.average_cost})\n"
    
    return {
        'success': True,
        'date': today.isoformat(),
        'summary': summary.to_dict(),
        'report': report
    }


# ========== 5.3 命中率追蹤 (寫入 MySQL) ==========

def track_signal_hit_rate() -> Dict:
    """
    追蹤信號命中率並寫入 MySQL
    
    Returns:
        dict: 追蹤結果
    """
    today = date.today()
    
    # 統計每檔股票的信號與成交
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT 
                s.symbol,
                s.signal_type,
                COUNT(s.id) as signal_count,
                COUNT(DISTINCT po.id) as filled_count
            FROM signals s
            LEFT JOIN paper_orders po ON po.source_signal_id = s.id AND po.status = 'filled'
            WHERE DATE(s.created_at) = %s
            GROUP BY s.symbol, s.signal_type
        """, (today,))
        rows = cursor.fetchall()
    
    results = []
    for row in rows:
        signal_count = row['signal_count'] or 0
        filled_count = row['filled_count'] or 0
        hit_rate = (filled_count / signal_count * 100) if signal_count > 0 else 0
        
        # 寫入 paper_signal_stats
        stats = PaperSignalStats(
            date=today,
            symbol=row['symbol'],
            signal_type=row['signal_type'],
            signal_count=signal_count,
            filled_count=filled_count,
            hit_rate=hit_rate
        )
        stats.save()
        
        results.append({
            'symbol': row['symbol'],
            'signal_type': row['signal_type'],
            'signal_count': signal_count,
            'filled_count': filled_count,
            'hit_rate': hit_rate
        })
    
    # 計算總體命中率
    total_signals = sum(r['signal_count'] for r in results)
    total_filled = sum(r['filled_count'] for r in results)
    overall_hit_rate = (total_filled / total_signals * 100) if total_signals > 0 else 0
    
    return {
        'success': True,
        'date': today.isoformat(),
        'total_signals': total_signals,
        'total_filled': total_filled,
        'overall_hit_rate': overall_hit_rate,
        'details': results
    }


# ========== 5.4 回測對比 (寫入 MySQL) ==========

def compare_backtest_simulation() -> Dict:
    """
    對比回測與模擬交易表現
    
    Returns:
        dict: 對比結果
    """
    today = date.today()
    
    # 取得模擬報酬率
    from paper_trading_portfolio import get_paper_total_assets
    assets = get_paper_total_assets()
    
    initial_balance = SystemConfig.get_initial_balance()
    simulation_return = ((assets['total'] - initial_balance) / initial_balance * 100) if initial_balance > 0 else 0
    
    # 取得回測報酬率 (從最新的 backtest 結果)
    backtest_return = 0.0
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT return_pct FROM strategy_results 
            ORDER BY created_at DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            backtest_return = float(row['return_pct'] or 0)
    
    # 計算差異
    diff = simulation_return - backtest_return
    
    # 寫入 paper_performance
    performance = PaperPerformance(
        date=today,
        backtest_return=backtest_return,
        simulation_return=simulation_return,
        diff=diff,
        note=f"初始資金: ${initial_balance:,}, 模擬總資產: ${assets['total']:,}"
    )
    performance.save()
    
    return {
        'success': True,
        'date': today.isoformat(),
        'backtest_return': backtest_return,
        'simulation_return': simulation_return,
        'diff': diff,
        'initial_balance': initial_balance,
        'current_assets': assets['total']
    }


if __name__ == '__main__':
    print('=== 報告與監控測試 ===')
    
    # 測試每日推送
    print('\\n1. 每日推送到 Successor Bot')
    result = push_paper_daily_summary()
    print(f'結果: {result["success"]}')
    
    # 測試模擬報告
    print('\\n2. 模擬報告')
    result = generate_paper_report()
    print(f'結果: {result["success"]}')
    
    # 測試命中率追蹤
    print('\\n3. 命中率追蹤')
    result = track_signal_hit_rate()
    print(f'總體命中率: {result["overall_hit_rate"]:.2f}%')
    
    # 測試回測對比
    print('\\n4. 回測對比')
    result = compare_backtest_simulation()
    print(f'回測報酬: {result["backtest_return"]:.2f}%')
    print(f'模擬報酬: {result["simulation_return"]:.2f}%')
    print(f'差異: {result["diff"]:.2f}%')
