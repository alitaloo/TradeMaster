#!/usr/bin/env python3
"""
Config API Blueprint
系統配置接口 (可用資金等) - MySQL
"""

from flask import Blueprint, jsonify, request
from api.db import get_connection

config_bp = Blueprint('config', __name__, url_prefix='/api/v1/config')


@config_bp.route('', methods=['GET'])
def get_config():
    """獲取所有配置"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, value, description FROM config")
    rows = cursor.fetchall()
    conn.close()
    
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
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, value, description FROM config WHERE name = %s", (key,))
    row = cursor.fetchone()
    conn.close()
    
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
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO config (name, value, description, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE value = %s, updated_at = NOW()
    ''', (key, data.get('value'), data.get('description', ''), data.get('value')))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "message": f"Config {key} updated"
    })
