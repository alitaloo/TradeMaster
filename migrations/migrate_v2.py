#!/usr/bin/env python3
"""
TradeMaster v2 數據庫遷移腳本 (MySQL 版本)
更新: 2026-03-06 - 從 SQLite 遷移至 MySQL

使用方法:
    python3 migrations/migrate_v2.py
    python3 migrations/migrate_v2.py --rollback
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# 項目根目錄
PROJECT_ROOT = Path(__file__).parent.parent
MIGRATIONS_DIR = Path(__file__).parent

# 導入 MySQL 配置
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from config.database import MYSQL_CONFIG
    import mysql.connector
except ImportError:
    print("❌ 無法導入 config.database，請確認 MySQL 配置")
    sys.exit(1)


def get_connection():
    """獲取 MySQL 數據庫連接"""
    return mysql.connector.connect(**MYSQL_CONFIG)


def execute_sql_file(cursor, sql_file):
    """執行 SQL 文件"""
    sql_file_path = MIGRATIONS_DIR / sql_file

    if not sql_file_path.exists():
        print(f"  ⚠️ 文件不存在: {sql_file}")
        return False

    with open(sql_file_path, 'r') as f:
        sql_content = f.read()

    # 過濾掉注釋行，分割語句
    statements = []
    for stmt in sql_content.split(';'):
        stmt = stmt.strip()
        # 跳過純注釋或空語句
        lines = [l for l in stmt.splitlines() if l.strip() and not l.strip().startswith('--')]
        if lines:
            statements.append(stmt)

    for statement in statements:
        try:
            cursor.execute(statement)
        except mysql.connector.Error as e:
            # 忽略 "已存在" 類錯誤 (1050: table exists, 1061: duplicate key)
            if e.errno in (1050, 1061, 1060):
                pass
            else:
                print(f"  ❌ 執行失敗: {e}\n  SQL: {statement[:80]}...")
                return False

    return True


def migrate():
    """執行遷移"""
    print("=" * 60)
    print("📦 TradeMaster v2 數據庫遷移 (MySQL)")
    print("=" * 60)
    print(f"  Host: {MYSQL_CONFIG['host']}")
    print(f"  Database: {MYSQL_CONFIG['database']}")

    conn = get_connection()
    cursor = conn.cursor()

    # 創建遷移記錄表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            version VARCHAR(20) NOT NULL,
            description TEXT,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    # 檢查已執行的遷移
    cursor.execute("SELECT version FROM schema_migrations")
    applied = set(row[0] for row in cursor.fetchall())
    print(f"\n📋 已執行的遷移: {applied or '無'}")

    # 需要執行的遷移文件
    migrations = [
        ("001", "001_signals.sql", "信號表"),
        ("002", "002_positions.sql", "持倉表"),
        ("003", "003_orders.sql", "訂單表"),
        ("004", "004_news_notifications_risk.sql", "新聞/通知/風控表"),
        ("005", "005_api_keys_kline_cache.sql", "API Keys / K線快取表"),
        ("006", "006_futu_sim_lifecycle.sql", "Futu SIM lifecycle schema"),
        ("007", "007_exit_candidates.sql", "Lifecycle exit candidates"),
        ("008", "008_exit_action_proposals.sql", "Lifecycle exit action proposals (dry-run)"),
        ("009", "009_exit_submit_safety_pack.sql", "Pre-live submit safety pack"),
        ("010", "010_exit_submit_safety_pack_v2.sql", "Pre-live submit safety pack follow-up"),
    ]

    print("\n🔄 執行遷移...")
    success_count = 0

    for version, sql_file, description in migrations:
        if version in applied:
            print(f"  ✓ {version}: {description} (已執行)")
            continue

        print(f"  🔧 {version}: {description}...")

        if execute_sql_file(cursor, sql_file):
            cursor.execute(
                "INSERT INTO schema_migrations (version, description) VALUES (%s, %s)",
                (version, description)
            )
            conn.commit()
            print(f"     ✅ 完成")
            success_count += 1
        else:
            print(f"     ❌ 失敗，中止遷移")
            conn.rollback()
            conn.close()
            sys.exit(1)

    conn.close()

    print("\n" + "=" * 60)
    print(f"✅ 遷移完成！執行了 {success_count} 個新遷移")
    print(f"   數據庫: {MYSQL_CONFIG['host']}/{MYSQL_CONFIG['database']}")
    print("=" * 60)


def rollback():
    """回滾最後一個遷移（僅記錄層面）"""
    print("⚠️ MySQL 版本暫不支援自動回滾，請手動執行 DROP TABLE")
    print("  如需回滾，請聯絡 DBA 手動處理")


if __name__ == "__main__":
    if "--rollback" in sys.argv:
        rollback()
    else:
        migrate()
