#!/usr/bin/env python3
"""
Sync Positions from Futu API to paper_positions table

This script:
1. Connects to Futu API (host=127.0.0.1, port=11111, TrdEnv.SIMULATE)
2. Gets all positions via position_list_query
3. Clears paper_positions table
4. Inserts all Futu positions with proper field mapping
5. Prints before/after comparison
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from futu.trade.open_trade_context import OpenUSTradeContext
from futu.common.constant import TrdEnv
from config.database import get_db_cursor


def get_futu_positions():
    """Query positions from Futu API"""
    with OpenUSTradeContext(host='127.0.0.1', port=11111) as trade_ctx:
        ret, data = trade_ctx.position_list_query(trd_env=TrdEnv.SIMULATE)
        
        if ret != 0:
            print(f"❌ Error querying positions: {data}")
            return []
        
        if data is None or len(data) == 0:
            print("ℹ️  No positions in Futu SIM account")
            return []
        
        print(f"✅ Retrieved {len(data)} positions from Futu API")
        print("\n📋 Raw position data columns:", list(data.columns))
        print("\n📋 Raw position data sample:")
        print(data.head())
        
        return data


def clear_paper_positions():
    """Clear all positions from paper_positions table"""
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM paper_positions")
        print(f"✅ Cleared all positions from paper_positions table")


def insert_positions(futu_data):
    """Insert positions from Futu data into paper_positions table"""
    inserted = 0
    
    with get_db_cursor() as cursor:
        for _, row in futu_data.iterrows():
            symbol = row.get('code', '')
            if not symbol:
                continue
            
            qty = float(row.get('qty', 0) or 0)
            
            # Skip positions with 0 quantity (closed positions)
            if qty == 0:
                continue
            
            # 空頭持倉也要同步（記錄為負數），方便對帳
            if qty < 0:
                print(f"  📉 Short position: {symbol} | qty={qty}")
            
            def safe_float(val, default=0):
                try:
                    return float(val) if val is not None and str(val).strip() not in ('', 'N/A', 'nan', 'None') else default
                except (ValueError, TypeError):
                    return default

            cost_price = safe_float(row.get('cost_price'))
            market_val = safe_float(row.get('market_val')) or safe_float(row.get('market_value'))
            pl_val = safe_float(row.get('pl_val')) or safe_float(row.get('unrealized_pl'))
            pl_ratio = safe_float(row.get('pl_ratio')) or safe_float(row.get('unrealized_pl_ratio'))
            nominal_price = safe_float(row.get('nominal_price'))
            
            # Calculate current_price
            if market_val and qty and qty != 0:
                current_price = abs(market_val / qty)
            elif nominal_price:
                current_price = nominal_price
            else:
                current_price = cost_price
            
            # Calculate unrealized_pnl_pct
            unrealized_pnl_pct = pl_ratio * 100 if pl_ratio else 0
            
            # Use REPLACE INTO to handle duplicates (upsert)
            cursor.execute("""
                REPLACE INTO paper_positions 
                (symbol, quantity, average_cost, current_price, market_value, 
                 unrealized_pnl, unrealized_pnl_pct, realized_pnl)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol,
                int(qty),  # Store as-is (positive or negative for shorts)
                cost_price,
                current_price,
                int(qty) * current_price,  # market_value = qty × price (負數 for shorts)
                pl_val,
                unrealized_pnl_pct,
                0  # realized_pnl starts at 0
            ))
            inserted += 1
            direction = "📉 SHORT" if qty < 0 else "✅ LONG"
            print(f"  {direction}: {symbol} | qty={int(qty)} | cost=${cost_price} | current=${current_price} | mv=${market_val} | P&L=${pl_val}")
    
    return inserted


def get_current_positions():
    """Get current positions from database"""
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM paper_positions WHERE quantity != 0")
        return cursor.fetchall()


def main():
    print("=" * 60)
    print("🔄 Sync Positions from Futu API to paper_positions")
    print("=" * 60)
    
    # Step 1: Get current positions (before)
    print("\n📊 Current positions (BEFORE sync):")
    current_positions = get_current_positions()
    if current_positions:
        for pos in current_positions:
            print(f"  {pos['symbol']}: {pos['quantity']} @ ${pos['average_cost']} (mv=${pos['market_value']})")
    else:
        print("  (empty)")
    
    # Step 2: Query Futu positions
    print("\n📡 Querying Futu API...")
    futu_data = get_futu_positions()
    
    if futu_data is None or len(futu_data) == 0:
        print("⚠️  No positions from Futu API, clearing local positions anyway")
        clear_paper_positions()
        print("\n✅ Sync completed (cleared local, no Futu positions)")
        return
    
    # Step 3: Clear paper_positions
    print("\n🗑️  Clearing paper_positions table...")
    clear_paper_positions()
    
    # Step 4: Insert new positions
    print("\n💾 Inserting positions from Futu...")
    inserted = insert_positions(futu_data)
    
    # Step 5: Show final positions
    print("\n📊 Final positions (AFTER sync):")
    final_positions = get_current_positions()
    for pos in final_positions:
        print(f"  {pos['symbol']}: {pos['quantity']} @ ${pos['average_cost']} (mv=${pos['market_value']}, P&L=${pos['unrealized_pnl']})")
    
    # Step 6: 同步現金餘額到 system_config
    try:
        from futu.trade.open_trade_context import OpenUSTradeContext
        from futu.common.constant import TrdEnv
        with OpenUSTradeContext(host='127.0.0.1', port=11111) as trade_ctx:
            ret, acc_data = trade_ctx.accinfo_query(trd_env=TrdEnv.SIMULATE)
            if ret == 0 and acc_data is not None and len(acc_data) > 0:
                cash = float(acc_data.iloc[0].get('cash', 0) or 0)
                with get_db_cursor() as c:
                    c.execute("""
                        INSERT INTO system_config (config_key, config_value, description)
                        VALUES ('paper.cash_balance', %s, 'Futu 模擬帳戶現金（由 sync 更新）')
                        ON DUPLICATE KEY UPDATE config_value=%s, updated_at=NOW()
                    """, (str(cash), str(cash)))
                print(f"  ✅ 現金餘額已寫入 DB: ${cash:,.2f}")
    except Exception as e:
        print(f"  ⚠️ 現金餘額同步失敗: {e}")

    # Summary
    print("\n" + "=" * 60)
    print(f"✅ Sync completed: {inserted} positions inserted")
    print("=" * 60)


if __name__ == '__main__':
    main()
