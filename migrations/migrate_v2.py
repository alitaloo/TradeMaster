#!/usr/bin/env python3
"""
TradeMaster v2 數據庫遷移腳本
執行時間: 2026-02-13

使用方法:
    python3 migrations/migrate_v2.py
    python3 migrations/migrate_v2.py --rollback
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

# 項目根目錄
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "trademaster.db"
MIGRATIONS_DIR = Path(__file__).parent


def get_connection():
    """獲取數據庫連接"""
    return sqlite3.connect(DB_PATH)


def execute_sql_file(cursor, sql_file):
    """執行 SQL 文件"""
    sql_file_path = MIGRATIONS_DIR / sql_file
    
    if not sql_file_path.exists():
        print(f"  ⚠️ 文件不存在: {sql_file}")
        return False
    
    with open(sql_file_path, 'r') as f:
        sql_content = f.read()
    
    # 分割語句（按 ; 分割）
    statements = [s.strip() for s in sql_content.split(';') if s.strip()]
    
    for statement in statements:
        try:
            cursor.execute(statement)
        except sqlite3.Error as e:
            print(f"  ❌ 執行失敗: {e}")
            return False
    
    return True


def migrate():
    """執行遷移"""
    print("=" * 60)
    print("📦 TradeMaster v2 數據庫遷移")
    print("=" * 60)
    
    # 確保數據庫目錄存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 創建遷移記錄表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version VARCHAR(20) NOT NULL,
            description TEXT,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 檢查已執行的遷移
    cursor.execute("SELECT version FROM schema_migrations")
    applied = set(row[0] for row in cursor.fetchall())
    print(f"\n📋 已執行的遷移: {applied or '無'}")
    
    # 需要執行的遷移文件
    migrations = [
        ('001', '001_signals.sql', '信號表'),
        ('002', '002_positions.sql', '持倉表'),
        ('003', '003_orders.sql', '訂單表'),
        ('004', '004_news_notifications_risk.sql', '新聞/推送/風控日誌表'),
    ]
    
    success_count = 0
    
    for version, filename, description in migrations:
        if version in applied:
            print(f"\n⏭️  跳過 {version}: {description} (已執行)")
            continue
        
        print(f"\n📄 執行 {version}: {description}...")
        
        if execute_sql_file(cursor, filename):
            cursor.execute(
                "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                (version, description)
            )
            conn.commit()
            print(f"  ✅ 成功")
            success_count += 1
        else:
            print(f"  ❌ 失敗")
            conn.rollback()
            break
    
    conn.close()
    
    print("\n" + "=" * 60)
    if success_count == len(migrations):
        print(f"✅ 遷移完成！成功執行 {success_count}/{len(migrations)} 個遷移")
    else:
        print(f"⚠️ 遷移部分完成 ({success_count}/{len(migrations)})")
    print("=" * 60)
    
    return success_count == len(migrations)


def rollback():
    """回滾遷移（簡化版 - 僅刪除新表）"""
    print("=" * 60)
    print("🔙 回滾遷移")
    print("=" * 60)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    tables_to_drop = [
        'risk_logs',
        'notifications', 
        'news',
        'orders',
        'positions',
        'signals',
    ]
    
    for table in tables_to_drop:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"  ✅ 刪除表: {table}")
        except sqlite3.Error as e:
            print(f"  ❌ 刪除失敗 {table}: {e}")
    
    # 清理遷移記錄
    cursor.execute("DELETE FROM schema_migrations")
    conn.commit()
    conn.close()
    
    print("\n✅ 回滾完成")


def status():
    """查看遷移狀態"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 檢查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = set(row[0] for row in cursor.fetchall())
    
    # 檢查遷移記錄
    cursor.execute("SELECT version, description, applied_at FROM schema_migrations ORDER BY version")
    migrations = cursor.fetchall()
    
    print("\n📊 數據庫狀態")
    print("-" * 40)
    print(f"數據庫: {DB_PATH}")
    print(f"\n📋 已執行的遷移:")
    
    if migrations:
        for version, desc, applied_at in migrations:
            print(f"  ✅ {version}: {desc} ({applied_at})")
    else:
        print("  無")
    
    print(f"\n📦 數據表:")
    for table in sorted(tables):
        print(f"  - {table}")
    
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--rollback":
            rollback()
        elif sys.argv[1] == "--status":
            status()
        else:
            print("用法:")
            print("  python3 migrate_v2.py        # 執行遷移")
            print("  python3 migrate_v2.py --rollback  # 回滾")
            print("  python3 migrate_v2.py --status  # 查看狀態")
    else:
        migrate()
