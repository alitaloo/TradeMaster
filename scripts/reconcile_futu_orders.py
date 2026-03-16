#!/usr/bin/env python3
"""
富途模擬交易訂單對帳腳本

用富途訂單數據重建本地 paper_orders 和 paper_positions。
"""
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import mysql.connector
from mysql.connector import Error as MySQLError
from futu import OpenUSTradeContext, TrdEnv
from futu.common.constant import OrderStatus
import pandas as pd

# 配置
FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'alita',
    'password': 'alitamysql',
    'database': 'trademaster',
    'charset': 'utf8mb4'
}
TIME_WINDOW_MINUTES = 30  # 放寬時間窗口到 30 分鐘


def get_mysql_connection():
    return mysql.connector.connect(**MYSQL_CONFIG)


def get_futu_orders() -> List[Dict]:
    """從富途 API 獲取所有已成交訂單"""
    ctx = OpenUSTradeContext(host=FUTU_HOST, port=FUTU_PORT)
    orders = []
    
    try:
        # 獲取 FILLED_ALL 和 FILLED_PART 狀態的訂單
        status_list = [OrderStatus.FILLED_ALL, OrderStatus.FILLED_PART]
        ret, data = ctx.history_order_list_query(
            status_filter_list=status_list,
            start='',
            end='',
            trd_env=TrdEnv.SIMULATE
        )
        
        if ret != 0:
            print(f"❌ 富途 API 錯誤: {data}")
            return []
        
        if data is not None and not data.empty:
            for _, row in data.iterrows():
                orders.append({
                    'futu_order_id': str(row['order_id']),
                    'symbol': row['code'],
                    'order_type': row['trd_side'],  # BUY or SELL
                    'quantity': int(row['qty']),
                    'price': float(row['price']) if row['price'] else 0.0,
                    'filled_quantity': int(row['dealt_qty']),
                    'filled_price': float(row['dealt_avg_price']) if row['dealt_avg_price'] else 0.0,
                    'order_status': row['order_status'],
                    'create_time': row['create_time'],
                    'updated_time': row['updated_time'],
                })
        
        print(f"✅ 從富途獲取 {len(orders)} 筆已成交訂單")
        
    except Exception as e:
        print(f"❌ 連接富途失敗: {e}")
    finally:
        ctx.close()
    
    return orders


def get_local_orders() -> List[Dict]:
    """從本地數據庫獲取所有訂單"""
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM paper_orders ORDER BY created_at ASC")
        orders = cursor.fetchall()
        print(f"✅ 從本地獲取 {len(orders)} 筆訂單")
        return orders
    except MySQLError as e:
        print(f"❌ 查詢本地訂單失敗: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_local_positions() -> Dict[str, Dict]:
    """從本地數據庫獲取持倉"""
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    
    positions = {}
    try:
        cursor.execute("SELECT * FROM paper_positions")
        for row in cursor.fetchall():
            positions[row['symbol']] = {
                'quantity': row['quantity'],
                'average_cost': float(row['average_cost']) if row['average_cost'] else 0.0,
                'market_value': float(row['market_value']) if row['market_value'] else 0.0,
            }
        print(f"✅ 從本地獲取 {len(positions)} 個持倉")
    except MySQLError as e:
        print(f"❌ 查詢本地持倉失敗: {e}")
    finally:
        cursor.close()
        conn.close()
    
    return positions


def parse_datetime(time_str: str) -> Optional[datetime]:
    """解析時間字符串"""
    if not time_str:
        return None
    try:
        # 嘗試多種格式
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
            try:
                return datetime.strptime(str(time_str), fmt)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def build_local_order_index(local_orders: List[Dict]) -> Dict:
    """為本地訂單建立索引，便於快速查找"""
    index = {
        'by_futu_id': {},      # futu_order_id -> order
        'by_symbol_qty': [],   # (symbol, order_type, filled_quantity) -> orders
    }
    
    for order in local_orders:
        # 按 futu_order_id 索引
        if order.get('futu_order_id'):
            index['by_futu_id'][order['futu_order_id']] = order
        
        # 按 symbol + order_type + filled_quantity 索引
        key = (order['symbol'], order['order_type'], int(order.get('filled_quantity') or 0))
        index['by_symbol_qty'].append((key, order))
    
    return index


def match_order(futu_order: Dict, local_index: Dict) -> Optional[Dict]:
    """匹配富途訂單和本地訂單
    
    匹配策略（按優先級）：
    1. futu_order_id 完全匹配
    2. symbol + order_type + filled_quantity 精確匹配（不限時間）
    3. symbol + order_type + filled_quantity + 時間窗口（±30分鐘）
    """
    
    # 策略1: 按 futu_order_id 匹配
    futu_id = futu_order.get('futu_order_id')
    if futu_id and futu_id in local_index['by_futu_id']:
        matched = local_index['by_futu_id'][futu_id]
        print(f"   [MATCH by futu_id] {futu_order['symbol']} {futu_order['order_type']} x{futu_order['filled_quantity']}")
        return matched
    
    # 策略2: 按 symbol + order_type + filled_quantity 精確匹配
    key = (futu_order['symbol'], futu_order['order_type'], futu_order['filled_quantity'])
    for k, local in local_index['by_symbol_qty']:
        if k == key:
            print(f"   [MATCH by qty] {futu_order['symbol']} {futu_order['order_type']} x{futu_order['filled_quantity']}")
            return local
    
    # 策略3: 放寬匹配 - 只看 symbol + order_type，數量接近（±10%）
    for k, local in local_index['by_symbol_qty']:
        if k[0] == futu_order['symbol'] and k[1] == futu_order['order_type']:
            local_qty = k[2]
            futu_qty = futu_order['filled_quantity']
            if local_qty > 0 and abs(local_qty - futu_qty) / local_qty <= 0.1:
                # 檢查時間
                local_time = parse_datetime(str(local.get('created_at')))
                futu_time = parse_datetime(futu_order['create_time'])
                if local_time and futu_time:
                    time_diff = abs((futu_time - local_time).total_seconds())
                    if time_diff <= TIME_WINDOW_MINUTES * 60:
                        print(f"   [MATCH by approx qty+time] {futu_order['symbol']} {futu_order['order_type']} x{futu_order['filled_quantity']} (local x{local_qty})")
                        return local
    
    return None


def reconcile_orders(futu_orders: List[Dict], local_orders: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """對帳訂單，返回 (漏記的訂單, 狀態錯誤的訂單)"""
    
    # 建立本地訂單索引
    local_index = build_local_order_index(local_orders)
    
    # 標記本地訂單為"已匹配"
    matched_local_ids = set()
    missing_orders = []
    status_error_orders = []
    
    print(f"\n🔍 匹配過程:")
    for futu in futu_orders:
        matched = match_order(futu, local_index)
        
        if matched:
            # 找到匹配，檢查狀態是否正確
            matched_local_ids.add(matched['id'])
            if matched['status'] != 'filled':
                status_error_orders.append({
                    'local': matched,
                    'futu': futu,
                })
        else:
            # 富途有但本地沒有
            missing_orders.append(futu)
    
    print(f"\n📊 對帳結果:")
    print(f"  - 富途已成交訂單: {len(futu_orders)}")
    print(f"  - 本地已有記錄: {len(matched_local_ids)}")
    print(f"  - 漏記的訂單: {len(missing_orders)}")
    print(f"  - 狀態錯誤的訂單: {len(status_error_orders)}")
    
    return missing_orders, status_error_orders


def insert_missing_orders(missing_orders: List[Dict]) -> int:
    """插入漏記的訂單"""
    if not missing_orders:
        return 0
    
    conn = get_mysql_connection()
    cursor = conn.cursor()
    
    inserted = 0
    try:
        for order in missing_orders:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            create_time = order['create_time']
            filled_at = order['updated_time'] or order['create_time']
            
            cursor.execute("""
                INSERT INTO paper_orders 
                (symbol, order_type, quantity, price, status, futu_order_id, 
                 filled_quantity, filled_price, filled_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                order['symbol'],
                order['order_type'],
                order['quantity'],
                order['price'],
                'filled',
                order['futu_order_id'],
                order['filled_quantity'],
                order['filled_price'],
                filled_at,
                create_time,
                now
            ))
            inserted += 1
        
        conn.commit()
        print(f"\n✅ 成功插入 {inserted} 筆漏記訂單")
        
    except MySQLError as e:
        conn.rollback()
        print(f"❌ 插入訂單失敗: {e}")
    finally:
        cursor.close()
        conn.close()
    
    return inserted


def fix_status_errors(status_error_orders: List[Dict]) -> int:
    """修復狀態錯誤的訂單"""
    if not status_error_orders:
        return 0
    
    conn = get_mysql_connection()
    cursor = conn.cursor()
    
    fixed = 0
    try:
        for item in status_error_orders:
            local = item['local']
            futu = item['futu']
            
            cursor.execute("""
                UPDATE paper_orders 
                SET status = 'filled',
                    filled_quantity = %s,
                    filled_price = %s,
                    filled_at = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                futu['filled_quantity'],
                futu['filled_price'],
                futu['updated_time'] or futu['create_time'],
                local['id']
            ))
            fixed += 1
        
        conn.commit()
        print(f"✅ 成功修復 {fixed} 筆狀態錯誤訂單")
        
    except MySQLError as e:
        conn.rollback()
        print(f"❌ 修復訂單失敗: {e}")
    finally:
        cursor.close()
        conn.close()
    
    return fixed


def rebuild_positions() -> Dict:
    """從 paper_orders 重建持倉"""
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    
    positions = {}
    realized_pnl = {}
    
    try:
        # 獲取所有 filled 訂單
        cursor.execute("""
            SELECT * FROM paper_orders 
            WHERE status = 'filled' AND COALESCE(filled_quantity, 0) > 0
            ORDER BY COALESCE(filled_at, created_at) ASC, id ASC
        """)
        
        for row in cursor.fetchall():
            symbol = row['symbol']
            side = row['order_type']
            qty = int(row['filled_quantity'])
            price = float(row['filled_price'])
            
            if symbol not in positions:
                positions[symbol] = {'quantity': 0, 'total_cost': 0.0}
                realized_pnl[symbol] = 0.0
            
            if side == 'BUY':
                positions[symbol]['quantity'] += qty
                positions[symbol]['total_cost'] += qty * price
            elif side == 'SELL':
                # 計算已實現損益
                if positions[symbol]['quantity'] > 0:
                    avg_cost = positions[symbol]['total_cost'] / positions[symbol]['quantity']
                    realized_pnl[symbol] += (price - avg_cost) * qty
                positions[symbol]['quantity'] -= qty
                if positions[symbol]['quantity'] > 0:
                    positions[symbol]['total_cost'] = positions[symbol]['quantity'] * (positions[symbol]['total_cost'] / (positions[symbol]['quantity'] + qty) if positions[symbol]['quantity'] + qty > 0 else 0)
                else:
                    positions[symbol]['total_cost'] = 0
        
        # 更新持倉表
        cursor.execute("DELETE FROM paper_positions")
        
        for symbol, data in positions.items():
            if data['quantity'] <= 0:
                continue
            
            avg_cost = data['total_cost'] / data['quantity'] if data['quantity'] > 0 else 0
            
            # 嘗試獲取 current_price（這裡簡單處理，實際應該從行情 API 獲取）
            cursor.execute("SELECT current_price FROM paper_positions WHERE symbol = %s", (symbol,))
            result = cursor.fetchone()
            current_price = float(result['current_price']) if result and result['current_price'] else avg_cost
            
            market_value = data['quantity'] * current_price
            unrealized_pnl = (current_price - avg_cost) * data['quantity']
            unrealized_pnl_pct = ((current_price / avg_cost) - 1) * 100 if avg_cost > 0 else 0
            
            cursor.execute("""
                INSERT INTO paper_positions 
                (symbol, quantity, average_cost, current_price, market_value, 
                 unrealized_pnl, unrealized_pnl_pct, realized_pnl)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol,
                data['quantity'],
                round(avg_cost, 4),
                round(current_price, 4),
                round(market_value, 2),
                round(unrealized_pnl, 2),
                round(unrealized_pnl_pct, 4),
                round(realized_pnl.get(symbol, 0), 2)
            ))
        
        conn.commit()
        print(f"✅ 成功重建 {len([s for s in positions.values() if s['quantity'] > 0])} 個持倉")
        
        return positions
        
    except MySQLError as e:
        conn.rollback()
        print(f"❌ 重建持倉失敗: {e}")
        return {}
    finally:
        cursor.close()
        conn.close()


def calculate_cash_from_orders() -> float:
    """從訂單計算現金餘額"""
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    
    total_buy = 0.0
    total_sell = 0.0
    
    try:
        # 假設初始資金為 1000000
        initial_balance = 1000000.0
        
        cursor.execute("""
            SELECT order_type, SUM(filled_quantity * filled_price) as total
            FROM paper_orders 
            WHERE status = 'filled' AND COALESCE(filled_quantity, 0) > 0
            GROUP BY order_type
        """)
        
        for row in cursor.fetchall():
            if row['order_type'] == 'BUY':
                total_buy = float(row['total']) if row['total'] else 0.0
            elif row['order_type'] == 'SELL':
                total_sell = float(row['total']) if row['total'] else 0.0
        
        cash = initial_balance - total_buy + total_sell
        return cash
        
    except MySQLError as e:
        print(f"❌ 計算現金失敗: {e}")
        return 0.0
    finally:
        cursor.close()
        conn.close()


def print_comparison(before_positions: Dict, after_positions: Dict, 
                    before_cash: float, after_cash: float,
                    before_order_count: int, after_order_count: int):
    """打印修正前後的對比"""
    print("\n" + "="*60)
    print("📊 對帳結果對比")
    print("="*60)
    
    print(f"\n📝 訂單數量:")
    print(f"   修正前: {before_order_count}")
    print(f"   修正後: {after_order_count}")
    
    print(f"\n💵 現金餘額:")
    print(f"   修正前: ${before_cash:,.2f}")
    print(f"   修正後: ${after_cash:,.2f}")
    
    print(f"\n📈 持倉變化:")
    all_symbols = set(before_positions.keys()) | set(after_positions.keys())
    for symbol in sorted(all_symbols):
        before_qty = before_positions.get(symbol, {}).get('quantity', 0)
        after_qty = after_positions.get(symbol, {}).get('quantity', 0)
        if before_qty != after_qty:
            print(f"   {symbol}: {before_qty} → {after_qty} ({after_qty - before_qty:+d})")
    
    # 檢查現金差異
    if before_cash != 0:
        cash_diff_pct = abs(after_cash - before_cash) / abs(before_cash) * 100
    else:
        cash_diff_pct = 0
    if cash_diff_pct > 5:
        print(f"\n⚠️ 警告: 現金差異 {cash_diff_pct:.2f}% 超過 5%")
    else:
        print(f"\n✅ 現金差異 {cash_diff_pct:.2f}% 在 5% 以內")


def main():
    print("="*60)
    print("🔄 富途模擬交易訂單對帳")
    print("="*60)
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 獲取數據
    print("\n📥 第一步：獲取數據...")
    futu_orders = get_futu_orders()
    local_orders = get_local_orders()
    before_positions = get_local_positions()
    before_cash = calculate_cash_from_orders()
    before_order_count = len(local_orders)
    
    print(f"\n📊 修正前狀態:")
    print(f"   訂單數: {before_order_count}")
    print(f"   持倉數: {len(before_positions)}")
    print(f"   現金餘額: ${before_cash:,.2f}")
    
    # 對帳
    print("\n🔍 第二步：對帳...")
    missing_orders, status_error_orders = reconcile_orders(futu_orders, local_orders)
    
    # 修復
    print("\n🔧 第三步：修復數據...")
    if missing_orders:
        print("\n漏記的訂單:")
        for order in missing_orders:
            print(f"   {order['symbol']} {order['order_type']} x{order['filled_quantity']} @ ${order['filled_price']} ({order['create_time']})")
    
    inserted = insert_missing_orders(missing_orders)
    fixed = fix_status_errors(status_error_orders)
    
    # 重建持倉
    print("\n🏗️ 第四步：重建持倉...")
    after_positions = rebuild_positions()
    
    # 驗證
    print("\n✅ 第五步：驗證...")
    after_orders = get_local_orders()
    after_cash = calculate_cash_from_orders()
    after_order_count = len(after_orders)
    
    print_comparison(
        before_positions, after_positions,
        before_cash, after_cash,
        before_order_count, after_order_count
    )
    
    print("\n" + "="*60)
    print("✨ 對帳完成!")
    print(f"   新增訂單: {inserted}")
    print(f"   修復訂單: {fixed}")
    print("="*60)


if __name__ == '__main__':
    main()
