#!/usr/bin/env python3
"""
Paper Trading Service - 倉位管理
持倉查詢、同步、餘額、總資產計算
"""
import os
import sys
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import PaperPosition, PaperOrder, SystemConfig


def get_paper_positions() -> List[Dict]:
    """
    查詢所有模擬持倉
    
    Returns:
        list: 持倉列表
    """
    positions = PaperPosition.find_all()
    return [pos.to_dict() for pos in positions]


def get_paper_position(symbol: str) -> Optional[Dict]:
    """
    查詢單一股票持倉
    
    Args:
        symbol: 股票代碼
    
    Returns:
        dict: 持倉資訊
    """
    pos = PaperPosition.find_by_symbol(symbol)
    return pos.to_dict() if pos else None


def get_current_price(symbol: str) -> float:
    """
    取得現價
    TODO: 從富途 API 取得實際價格
    """
    # 模擬: 從持倉記錄中獲取或隨機
    pos = PaperPosition.find_by_symbol(symbol)
    if pos and pos.current_price:
        return float(pos.current_price)
    
    # 預設價格
    return 100.0


def update_position_prices() -> List[Dict]:
    """
    更新所有持倉的現價與市值
    
    Returns:
        list: 更新後的持倉列表
    """
    positions = PaperPosition.find_all()
    results = []
    
    for pos in positions:
        # 取得現價
        current_price = get_current_price(pos.symbol)
        
        # 計算市值與損益
        pos.calculate_pnl(current_price)
        pos.save()
        
        results.append(pos.to_dict())
    
    return results


def sync_paper_positions() -> Dict:
    """
    同步持倉 (從富途 API 同步到本地)
    
    TODO: 實際調用富途 API position_list
    
    Returns:
        dict: 同步結果
    """
    if not SystemConfig.is_paper_trading():
        return {'success': False, 'error': '模擬交易未啟用'}
    
    trading_mode = SystemConfig.get_trading_mode()
    
    try:
        # TODO: 實際調用富途 API
        # positions = call_futu_api('position_list', trading_mode=trading_mode)
        
        # 模擬: 從本地數據
        local_positions = PaperPosition.find_all()
        
        synced = 0
        for pos in local_positions:
            # 更新現價
            current_price = get_current_price(pos.symbol)
            pos.calculate_pnl(current_price)
            pos.save()
            synced += 1
        
        return {
            'success': True,
            'synced_count': synced,
            'positions': [pos.to_dict() for pos in PaperPosition.find_all()]
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def get_paper_balance() -> float:
    """
    查詢模擬帳戶現金餘額
    
    TODO: 從富途 API 取得實際餘額
    
    Returns:
        float: 現金餘額
    """
    if not SystemConfig.is_paper_trading():
        return 0.0
    
    trading_mode = SystemConfig.get_trading_mode()
    
    try:
        # TODO: 實際調用富途 API
        # result = call_futu_api('account_info', trading_mode=trading_mode)
        # return result['cash']
        
        # 模擬: 初始資金 - 已用資金
        initial = SystemConfig.get_initial_balance()
        
        # 計算已用資金 (持倉市值)
        positions = PaperPosition.find_all()
        used = sum(float(p.market_value or 0) for p in positions)
        
        # 計算已實現損益
        realized_pnl = sum(float(p.realized_pnl or 0) for p in positions)
        
        # 現金 = 初始 + 已實現損益 - 已用
        cash = initial + realized_pnl - used
        
        return max(0, cash)
        
    except Exception:
        return 0.0


def get_paper_total_assets() -> Dict:
    """
    計算總資產
    
    Returns:
        dict: 總資產資訊
    """
    if not SystemConfig.is_paper_trading():
        return {
            'cash': 0,
            'market_value': 0,
            'total': 0,
            'unrealized_pnl': 0,
            'realized_pnl': 0
        }
    
    # 現金
    cash = get_paper_balance()
    
    # 更新持倉價格
    update_position_prices()
    
    # 持倉
    positions = PaperPosition.find_all()
    
    # 持倉市值
    market_value = sum(float(p.market_value or 0) for p in positions)
    
    # 未實現損益
    unrealized_pnl = sum(float(p.unrealized_pnl or 0) for p in positions)
    
    # 已實現損益
    realized_pnl = sum(float(p.realized_pnl or 0) for p in positions)
    
    # 總資產
    total = cash + market_value
    
    return {
        'cash': round(cash, 2),
        'market_value': round(market_value, 2),
        'total': round(total, 2),
        'unrealized_pnl': round(unrealized_pnl, 2),
        'unrealized_pnl_pct': round((unrealized_pnl / total * 100) if total > 0 else 0, 2),
        'realized_pnl': round(realized_pnl, 2),
        'position_count': len(positions)
    }


if __name__ == '__main__':
    print('=== 倉位管理測試 ===')
    
    # 測試總資產
    assets = get_paper_total_assets()
    print(f'總資產: {assets}')
    
    # 測試持倉
    positions = get_paper_positions()
    print(f'持倉數量: {len(positions)}')
    for pos in positions:
        print(f'  {pos["symbol"]}: {pos["quantity"]} @ {pos["current_price"]}')
    
    # 測試現金
    cash = get_paper_balance()
    print(f'現金: {cash}')
