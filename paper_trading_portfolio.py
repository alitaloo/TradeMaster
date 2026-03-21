#!/usr/bin/env python3
"""
Paper Trading Service - 倉位管理
持倉查詢、同步、餘額、總資產計算
"""
import os
import sys
import socket
import logging
import time
from typing import List, Dict, Optional

# Module-level variable for caching price updates
_last_price_update_time = 0
_PRICE_UPDATE_INTERVAL = 60  # seconds
_cached_balance = None
_last_balance_time = 0
_BALANCE_CACHE_INTERVAL = 60  # seconds

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import PaperPosition
from config.database import get_db_connection
from models import PaperOrder, SystemConfig

logger = logging.getLogger(__name__)


def is_futu_available(host: str = '127.0.0.1', port: int = 11111, timeout: int = 3) -> bool:
    """檢查富途 API 端口是否可用"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


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


def get_current_price(symbol: str, max_age_minutes: int = 30) -> float:
    """
    取得現價
    優先從富途實時報價獲取，若失敗則從 K 線數據獲取
    
    Args:
        symbol: 股票代碼 (如 US.TSLA)
        max_age_minutes: K 線數據最大可接受的陳舊時間（分鐘）
    
    Returns:
        float: 當前價格
    """
    from datetime import datetime, timedelta
    import pytz
    
    # 1. 嘗試從富途實時報價獲取（交易時間內優先）
    # 先檢查端口是否開放，避免長時間等待
    import socket
    
    def is_port_open(host, port, timeout=2):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except:
            return False
    
    # 快速檢查 Futu API 是否可用
    if not is_port_open('127.0.0.1', 11111, timeout=2):
        # 端口不可用，跳過富途，直接用 K 線數據
        pass
    else:
        try:
            import futu as ft
            quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)
            
            # 先訂閱基礎報價，才能獲取實時數據
            quote_ctx.subscribe([symbol], [ft.SubType.QUOTE])
            
            ret, data = quote_ctx.get_stock_quote([symbol])
            quote_ctx.close()
            
            if ret == 0 and data is not None and len(data) > 0:
                last_price = data.iloc[0].get('last_price', 0)
                if last_price and last_price > 0:
                    return float(last_price)
        except Exception as e:
            # 富途 API 不可用，繼續使用 K 線數據
            pass
    
    # 2. 從 K 線數據獲取
    try:
        from config.database import get_db_cursor
        
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT close_price as close, timestamp, updated_at
                FROM kline_cache 
                WHERE symbol = %s 
                    AND interval_val = '5m'
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (symbol,))
            row = cursor.fetchone()
            if row and row['close']:
                price = float(row['close'])
                
                # 檢查數據新鮮度
                if row.get('updated_at'):
                    updated_at = row['updated_at']
                    if isinstance(updated_at, str):
                        updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                    
                    # 計算數據年齡
                    now = datetime.now()
                    if updated_at.tzinfo:
                        now = datetime.now(pytz.UTC)
                    age = now - updated_at
                    age_minutes = age.total_seconds() / 60
                    
                    if age_minutes > max_age_minutes:
                        print(f"⚠️ {symbol} K線數據已 {age_minutes:.0f} 分鐘未更新 (最後: {row.get('timestamp')})")
                
                return price
    except Exception as e:
        print(f"獲取 {symbol} 價格失敗: {e}")
    
    # 3. Fallback: 從持倉記錄中獲取
    pos = PaperPosition.find_by_symbol(symbol)
    if pos and pos.current_price:
        return float(pos.current_price)
    
    # 4. 都讀不到，記錄警告並返回 None
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ {symbol}: 無法獲取價格（kline_cache 和 富途 API 都失敗）")
    return None


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
    
    1. 檢查富途 port 11111 是否可用
    2. 如果可用，調用 position_list_query 獲取富途持倉
    3. 比對本地持倉和富途持倉，如有差異記 warning
    4. 用富途數據更新本地持倉的 current_price
    5. 如果富途不可用，fallback 到現有邏輯
    
    Returns:
        dict: 同步結果
    """
    if not SystemConfig.is_paper_trading():
        return {'success': False, 'error': '模擬交易未啟用'}
    
    # 優先嘗試從富途同步
    if is_futu_available():
        try:
            from futu.trade.open_trade_context import OpenUSTradeContext
            from futu.common.constant import TrdEnv
            
            with OpenUSTradeContext(host='127.0.0.1', port=11111) as trade_ctx:
                ret, data = trade_ctx.position_list_query(trd_env=TrdEnv.SIMULATE)
                
                if ret == 0 and data is not None and len(data) > 0:
                    local_positions = {pos.symbol: pos for pos in PaperPosition.find_all()}
                    synced = 0
                    
                    for _, row in data.iterrows():
                        symbol = row.get('code', '')
                        if not symbol:
                            continue
                        
                        # 獲取持倉數量和現價
                        qty = float(row.get('qty', 0) or 0)
                        current_price = float(row.get('last_price', 0) or row.get('cost_price', 0) or 0)
                        
                        # 比對本地持倉
                        if symbol in local_positions:
                            local_pos = local_positions[symbol]
                            local_qty = float(local_pos.quantity or 0)
                            
                            # 檢查數量差異
                            if abs(local_qty - qty) > 0.01:
                                logger.warning(f"⚠️ 持倉數量不一致: {symbol} 本地={local_qty} 富途={qty}")
                            
                            # 用富途的現價更新本地持倉
                            if current_price > 0:
                                local_pos.current_price = current_price
                                local_pos.calculate_pnl(current_price)
                                local_pos.save()
                                synced += 1
                        else:
                            # 富途有新持倉，本地沒有，記錄 warning
                            logger.warning(f"⚠️ 富途有新持倉: {symbol} {qty}股 @ ${current_price}")
                    
                    # 更新本地有但富途沒有的持倉（用富途返回的現價）
                    for symbol, local_pos in local_positions.items():
                        if symbol not in data['code'].values:
                            # 嘗試從富途獲取現價
                            try:
                                from futu.quote.open_quote_context import OpenQuoteContext
                                import futu as ft
                                with OpenQuoteContext(host='127.0.0.1', port=11111) as quote_ctx:
                                    quote_ctx.subscribe([symbol], [ft.SubType.QUOTE])
                                    ret, quote_data = quote_ctx.get_stock_quote([symbol])
                                    if ret == 0 and quote_data is not None and len(quote_data) > 0:
                                        current_price = float(quote_data.iloc[0].get('last_price', 0) or 0)
                                        if current_price > 0:
                                            local_pos.current_price = current_price
                                            local_pos.calculate_pnl(current_price)
                                            local_pos.save()
                            except ImportError:
                                # futu module 可能沒有完全 import
                                pass
                            except Exception as e:
                                logger.warning(f"⚠️ 更新 {symbol} 現價失敗: {e}")
                    
                    return {
                        'success': True,
                        'synced_count': synced,
                        'source': 'futu',
                        'positions': [pos.to_dict() for pos in PaperPosition.find_all()]
                    }
        except Exception as e:
            logger.warning(f"富途 API 同步失敗: {e}，fallback 到本地計算")
    
    # Fallback: 從本地數據和 K 線更新
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
        'source': 'local',
        'positions': [pos.to_dict() for pos in PaperPosition.find_all()]
    }


def get_paper_balance() -> float:
    """
    查詢模擬帳戶現金餘額
    
    優先從富途 API 獲取真實現金餘額，如果失敗則 fallback 到本地計算
    
    Returns:
        float: 現金餘額
    """
    if not SystemConfig.is_paper_trading():
        return 0.0
    
    # 快取：60 秒內直接返回上次結果
    global _cached_balance, _last_balance_time
    current_time = time.time()
    if _cached_balance is not None and current_time - _last_balance_time < _BALANCE_CACHE_INTERVAL:
        return _cached_balance
    
    trading_mode = SystemConfig.get_trading_mode()
    
    # 優先從 system_config 讀快取現金（由 sync_positions_from_futu.py 定時更新）
    try:
        from config.database import get_db_cursor
        with get_db_cursor() as c:
            c.execute("SELECT config_value FROM system_config WHERE config_key='paper.cash_balance'")
            row = c.fetchone()
            if row and row['config_value']:
                cash = float(row['config_value'])
                logger.debug(f"現金餘額來自 DB cache: ${cash:.2f}")
                _cached_balance = max(0, cash)
                _last_balance_time = time.time()
                return _cached_balance
    except Exception:
        pass

    # Fallback: 本地計算
    cash = _calculate_local_cash()
    logger.info(f"✅ 現金餘額計算成功: ${cash:.2f} (source: local)")
    _cached_balance = max(0, cash)
    _last_balance_time = time.time()
    return _cached_balance


def _calculate_local_cash() -> float:
    """
    本地計算現金餘額
    
    現金 = 初始資金 - 淨買入花費 + 賣出收入
    
    Returns:
        float: 現金餘額
    """
    initial = SystemConfig.get_initial_balance()
    
    # 從數據庫計算實際買賣
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # 計算買入總花費
        cursor.execute("""
            SELECT COALESCE(SUM(filled_quantity * filled_price), 0) as total_buy
            FROM paper_orders 
            WHERE order_type = 'BUY' AND status = 'filled'
        """)
        total_buy = float(cursor.fetchone()['total_buy'] or 0)
        
        # 計算賣出總收入
        cursor.execute("""
            SELECT COALESCE(SUM(filled_quantity * filled_price), 0) as total_sell
            FROM paper_orders 
            WHERE order_type = 'SELL' AND status = 'filled'
        """)
        total_sell = float(cursor.fetchone()['total_sell'] or 0)
    
    # 現金 = 初始資金 - 買入花費 + 賣出收入
    cash = initial - total_buy + total_sell
    
    return cash


def _safe_pct(numerator: float, denominator: float) -> float:
    """安全計算百分比，避免除以 0。"""
    return round((numerator / denominator * 100) if denominator > 0 else 0, 2)


def get_paper_total_assets() -> Dict:
    """
    計算總資產

    欄位定義：
    - unrealized_pnl: 未實現損益金額
    - unrealized_pnl_pct_total_assets: 未實現損益 / 當前總資產 * 100
    - unrealized_pnl_pct_initial_balance: 未實現損益 / 初始資金 * 100
    - unrealized_pnl_pct_position_cost: 未實現損益 / 持倉總成本 * 100

    相容性：
    - 保留舊欄位 unrealized_pnl_pct，值等同 unrealized_pnl_pct_total_assets
    - 舊欄位僅供相容，不建議新程式繼續使用
    
    Returns:
        dict: 總資產資訊
    """
    if not SystemConfig.is_paper_trading():
        return {
            'cash': 0,
            'market_value': 0,
            'total': 0,
            'initial_balance': 0,
            'total_position_cost': 0,
            'unrealized_pnl': 0,
            'unrealized_pnl_pct_total_assets': 0,
            'unrealized_pnl_pct_initial_balance': 0,
            'unrealized_pnl_pct_position_cost': 0,
            'unrealized_pnl_pct': 0,
            'realized_pnl': 0,
            'position_count': 0
        }
    
    initial_balance = float(SystemConfig.get_initial_balance() or 0)

    # 現金
    cash = get_paper_balance()
    
    # 更新持倉價格（背景非阻塞：不卡 API 回應）
    global _last_price_update_time
    current_time = time.time()
    if current_time - _last_price_update_time >= _PRICE_UPDATE_INTERVAL:
        _last_price_update_time = current_time  # 先標記，防止重複觸發
        import threading
        threading.Thread(target=update_position_prices, daemon=True).start()
    
    # 持倉
    positions = PaperPosition.find_all()
    
    # 持倉市值
    market_value = sum(float(p.market_value or 0) for p in positions)

    # 持倉總成本
    total_position_cost = sum(float(p.average_cost or 0) * float(p.quantity or 0) for p in positions)
    
    # 未實現損益
    unrealized_pnl = sum(float(p.unrealized_pnl or 0) for p in positions)
    
    # 已實現損益
    realized_pnl = sum(float(p.realized_pnl or 0) for p in positions)
    
    # 總資產
    total = cash + market_value

    unrealized_pnl_pct_total_assets = _safe_pct(unrealized_pnl, total)
    unrealized_pnl_pct_initial_balance = _safe_pct(unrealized_pnl, initial_balance)
    unrealized_pnl_pct_position_cost = _safe_pct(unrealized_pnl, total_position_cost)
    
    # 整體盈虧 (vs 初始資金)
    overall_pnl = round(total - initial_balance, 2)
    overall_pnl_pct = round((total - initial_balance) / initial_balance * 100, 2) if initial_balance > 0 else 0
    
    return {
        'cash': round(cash, 2),
        'market_value': round(market_value, 2),
        'total': round(total, 2),
        'initial_balance': round(initial_balance, 2),
        'total_position_cost': round(total_position_cost, 2),
        'unrealized_pnl': round(unrealized_pnl, 2),
        'unrealized_pnl_pct_total_assets': unrealized_pnl_pct_total_assets,
        'unrealized_pnl_pct_initial_balance': unrealized_pnl_pct_initial_balance,
        'unrealized_pnl_pct_position_cost': unrealized_pnl_pct_position_cost,
        # Deprecated alias: historically this meant unrealized_pnl / total_assets * 100.
        'unrealized_pnl_pct': unrealized_pnl_pct_total_assets,
        'realized_pnl': round(realized_pnl, 2),
        'position_count': len(positions),
        # 整體盈虧 (vs 初始資金)
        'overall_pnl': overall_pnl,
        'overall_pnl_pct': overall_pnl_pct
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
