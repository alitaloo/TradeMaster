#!/usr/bin/env python3
"""
Paper Trading Service - 統一入口
整合下單、倉位、報告等功能
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all modules
from paper_trading import (
    submit_paper_order,
    query_order,
    update_order_status,
    poll_paper_orders,
    handle_buy_fill,
    handle_sell_fill,
    close_position,
    cancel_paper_order
)

from paper_trading_portfolio import (
    get_paper_positions,
    get_paper_position,
    update_position_prices,
    sync_paper_positions,
    get_paper_balance,
    get_paper_total_assets
)

from paper_trading_risk import check_stop_loss_take_profit

from models import SystemConfig, PaperOrder, PaperPosition


def init_paper_trading(enabled: bool = True, trading_mode: int = 1):
    """
    初始化模擬交易配置
    
    Args:
        enabled: 是否啟用
        trading_mode: 交易模式 (0=真實, 1=模擬)
    """
    SystemConfig.set('paper_trading_enabled', 'true' if enabled else 'false')
    SystemConfig.set('paper_trading_mode', str(trading_mode))


def is_enabled() -> bool:
    """檢查是否啟用模擬交易"""
    return SystemConfig.is_paper_trading()


def get_status() -> dict:
    """取得模擬交易狀態"""
    assets = get_paper_total_assets()
    positions = get_paper_positions()
    pending_orders = PaperOrder.find_pending()
    
    return {
        'enabled': is_enabled(),
        'trading_mode': SystemConfig.get_trading_mode(),
        'initial_balance': SystemConfig.get_initial_balance(),
        'total_assets': assets['total'],
        'cash': assets['cash'],
        'market_value': assets['market_value'],
        'total_position_cost': assets['total_position_cost'],
        'unrealized_pnl': assets['unrealized_pnl'],
        'unrealized_pnl_pct_total_assets': assets['unrealized_pnl_pct_total_assets'],
        'unrealized_pnl_pct_initial_balance': assets['unrealized_pnl_pct_initial_balance'],
        'unrealized_pnl_pct_position_cost': assets['unrealized_pnl_pct_position_cost'],
        # Deprecated alias: equals unrealized_pnl_pct_total_assets.
        'unrealized_pnl_pct': assets['unrealized_pnl_pct'],
        'realized_pnl': assets['realized_pnl'],
        'position_count': len(positions),
        'pending_orders': len(pending_orders),
        # 整體盈虧 (vs 初始資金)
        'overall_pnl': assets.get('overall_pnl'),
        'overall_pnl_pct': assets.get('overall_pnl_pct')
    }


def run_daily_settlement() -> dict:
    """
    每日結算
    
    1. 更新持倉價格
    2. 計算損益
    3. 記錄每日 summary
    
    Returns:
        dict: 結算結果
    """
    from models import PaperDailySummary
    from datetime import date, timedelta
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    # 1. 更新持倉價格
    update_position_prices()
    
    # 2. 計算總資產
    assets = get_paper_total_assets()
    
    # 3. 計算 daily_pnl = 今天 total_value - 昨天 total_value
    daily_pnl = assets['total']
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT total_value 
                FROM paper_daily_summary 
                WHERE date = %s 
                LIMIT 1
            """, (yesterday,))
            row = cursor.fetchone()
            if row and row['total_value']:
                yesterday_total = float(row['total_value'])
                daily_pnl = assets['total'] - yesterday_total
    except Exception as e:
        # 如果查詢失敗，使用當作當天的 unrealized_pnl
        print(f"⚠️ 無法獲取昨日總值，使用 unrealized_pnl: {e}")
        daily_pnl = assets['unrealized_pnl']
    
    # 4. 統計成交
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT 
                COUNT(*) as trade_count,
                SUM(CASE WHEN order_type = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                SUM(CASE WHEN order_type = 'SELL' THEN 1 ELSE 0 END) as sell_count,
                SUM(CASE WHEN order_type = 'SELL' AND filled_quantity > 0 THEN filled_quantity * filled_price ELSE 0 END) as realized
            FROM paper_orders 
            WHERE status = 'filled' AND DATE(created_at) = %s
        """, (today,))
        row = cursor.fetchone()
        
        trade_count = row['trade_count'] or 0
        buy_count = row['buy_count'] or 0
        sell_count = row['sell_count'] or 0
        realized = float(row['realized'] or 0)
    
    # 5. 寫入每日 summary
    summary = PaperDailySummary(
        date=today,
        total_value=assets['total'],
        cash=assets['cash'],
        market_value=assets['market_value'],
        unrealized_pnl=assets['unrealized_pnl'],
        realized_pnl=assets['realized_pnl'],
        daily_pnl=daily_pnl,
        trade_count=trade_count,
        buy_count=buy_count,
        sell_count=sell_count
    )
    summary.save()
    
    return {
        'success': True,
        'date': today.isoformat(),
        'total_value': assets['total'],
        'cash': assets['cash'],
        'market_value': assets['market_value'],
        'total_position_cost': assets['total_position_cost'],
        'unrealized_pnl': assets['unrealized_pnl'],
        'unrealized_pnl_pct_total_assets': assets['unrealized_pnl_pct_total_assets'],
        'unrealized_pnl_pct_initial_balance': assets['unrealized_pnl_pct_initial_balance'],
        'unrealized_pnl_pct_position_cost': assets['unrealized_pnl_pct_position_cost'],
        # Deprecated alias: equals unrealized_pnl_pct_total_assets.
        'unrealized_pnl_pct': assets['unrealized_pnl_pct'],
        'realized_pnl': assets['realized_pnl'],
        'trade_count': trade_count,
        'buy_count': buy_count,
        'sell_count': sell_count
    }


# Export all functions
__all__ = [
    'init_paper_trading',
    'is_enabled',
    'get_status',
    'run_daily_settlement',
    'submit_paper_order',
    'query_order',
    'update_order_status',
    'poll_paper_orders',
    'close_position',
    'cancel_paper_order',
    'get_paper_positions',
    'get_paper_position',
    'update_position_prices',
    'sync_paper_positions',
    'get_paper_balance',
    'get_paper_total_assets',
    'check_stop_loss_take_profit',
]

# Import get_db_cursor for run_daily_settlement
from config.database import get_db_cursor
