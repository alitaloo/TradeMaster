#!/usr/bin/env python3
"""
Config API Blueprint
系統配置接口 (可用資金等) - MySQL
"""

from flask import Blueprint, jsonify, request
from api.db import get_db_connection

config_bp = Blueprint('config', __name__, url_prefix='/api/v1/config')

# 風控參數默認值（與 constants.py 保持一致）
DEFAULT_RISK_CONFIG = {
    'risk.max_single_amount_pct': '0.10',
    'risk.max_total_position_pct': '0.90',
    'risk.max_position_per_stock_pct': '0.25',
    'risk.max_leverage': '3.0',
    'risk.min_confidence': '0.60',
    'risk.max_stocks': '10',
    'risk.stop_loss_pct': '0.05',
    'risk.take_profit_pct': '0.10',
}


def init_risk_config():
    """初始化風控配置到數據庫（如果不存在）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for key, value in DEFAULT_RISK_CONFIG.items():
            cursor.execute('''
                INSERT IGNORE INTO system_config (config_key, config_value, description, updated_at)
                VALUES (%s, %s, %s, NOW())
            ''', (key, value, f'Auto-initialized risk config: {key}'))
        conn.commit()


@config_bp.route('/risk/init', methods=['POST'])
def init_risk_config_api():
    """初始化風控配置 API"""
    init_risk_config()
    return jsonify({
        "status": "ok",
        "message": "Risk config initialized"
    })


@config_bp.route('', methods=['GET'])
def get_config():
    """獲取所有配置"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, value, description FROM config")
        rows = cursor.fetchall()

    config = {}
    for row in rows:
        config[row['name']] = row['value']

    return jsonify({
        "status": "ok",
        "config": config
    })


@config_bp.route('/<key>', methods=['GET'])
def get_config_item(key):
    """獲取單個配置"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, value, description FROM config WHERE name = %s", (key,))
        row = cursor.fetchone()

    if not row:
        return jsonify({"status": "error", "message": "Config not found"}), 404

    return jsonify({
        "status": "ok",
        "config": row
    })


@config_bp.route('/<key>', methods=['PUT'])
def set_config(key):
    """設置配置"""
    data = request.json

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO config (name, value, description, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE value = %s, updated_at = NOW()
        ''', (key, data.get('value'), data.get('description', ''), data.get('value')))

        conn.commit()

    return jsonify({
        "status": "ok",
        "message": f"Config {key} updated"
    })


# ========== 風控配置 API ==========

@config_bp.route('/risk', methods=['GET'])
def get_risk_config():
    """獲取所有風控配置"""
    # 確保風控配置已初始化
    init_risk_config()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT config_key, config_value FROM system_config WHERE config_key LIKE 'risk.%'")
        rows = cursor.fetchall()

    # 轉換為 key: value 格式，去掉 'risk.' 前綴
    config = {}
    for row in rows:
        key = row['config_key'].replace('risk.', '', 1)
        # 嘗試轉換為數字
        try:
            if '.' in row['config_value']:
                config[key] = float(row['config_value'])
            else:
                config[key] = int(row['config_value'])
        except (ValueError, TypeError):
            config[key] = row['config_value']

    return jsonify({
        "status": "ok",
        "config": config
    })


@config_bp.route('/risk', methods=['PUT'])
def update_risk_config():
    """批量更新風控配置"""
    data = request.json
    
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor()
        updated_keys = []
        
        for key, value in data.items():
            db_key = f'risk.{key}'
            # 轉換為字符串存儲
            str_value = str(value)
            cursor.execute('''
                INSERT INTO system_config (config_key, config_value, updated_at)
                VALUES (%s, %s, NOW())
                ON DUPLICATE KEY UPDATE config_value = %s, updated_at = NOW()
            ''', (db_key, str_value, str_value))
            updated_keys.append(key)
        
        conn.commit()

    return jsonify({
        "status": "ok",
        "message": f"Risk config updated: {', '.join(updated_keys)}",
        "updated": updated_keys
    })
