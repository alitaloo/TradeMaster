#!/usr/bin/env python3
"""
Orders API Blueprint
訂單管理的 CRUD 接口
"""

from flask import Blueprint, jsonify, request
from pymysql.cursors import DictCursor
from api.db import get_db_connection
import uuid
from datetime import datetime, timezone, timedelta

_TZ_TAIPEI = timezone(timedelta(hours=8))

orders_bp = Blueprint('orders', __name__, url_prefix='/api/v1/orders')


def row_to_dict(row):
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


@orders_bp.route('', methods=['GET'])
def get_orders():
    """獲取訂單列表"""
    status = request.args.get('status')
    symbol = request.args.get('symbol')
    limit = int(request.args.get('limit', 100))

    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        # 使用 paper_orders 表
        query = "SELECT * FROM paper_orders WHERE 1=1"
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)

        if symbol:
            query += " AND symbol = %s"
            params.append(symbol.upper())

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

    orders = [row_to_dict(row) for row in rows]

    return jsonify({
        "status": "ok",
        "count": len(orders),
        "orders": orders
    })


@orders_bp.route('/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """獲取單個訂單"""
    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)
        cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        row = cursor.fetchone()

    if not row:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    return jsonify({
        "status": "ok",
        "order": row_to_dict(row)
    })


@orders_bp.route('', methods=['POST'])
def create_order():
    """創建新訂單"""
    data = request.json

    if not data or 'symbol' not in data or 'direction' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    # 生成訂單 ID
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        cursor.execute('''
            INSERT INTO orders (order_id, symbol, direction, order_type, price, quantity, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            order_id,
            data['symbol'].upper(),
            data['direction'],
            data.get('order_type', 'MARKET'),
            data.get('price'),
            data.get('quantity'),
            'PENDING'
        ))

        db_order_id = cursor.lastrowid
        conn.commit()

    return jsonify({
        "status": "ok",
        "message": "Order created",
        "order_id": order_id,
        "db_id": db_order_id
    }), 201


@orders_bp.route('/<int:order_id>', methods=['PUT'])
def update_order(order_id):
    """更新訂單狀態"""
    data = request.json

    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        # 構建更新語句
        updates = []
        params = []

        for field in ['order_type', 'price', 'quantity', 'filled_quantity',
                      'avg_fill_price', 'status']:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])

        if not updates:
            return jsonify({"status": "error", "message": "No fields to update"}), 400

        updates.append("updated_at = %s")
        params.append(datetime.now(_TZ_TAIPEI).isoformat())
        params.append(order_id)

        cursor.execute(
            f"UPDATE orders SET {', '.join(updates)} WHERE id = %s",
            params
        )

        conn.commit()
        affected = cursor.rowcount

    if affected == 0:
        return jsonify({"status": "error", "message": "Order not found"}), 404

    return jsonify({
        "status": "ok",
        "message": "Order updated"
    })


@orders_bp.route('/<int:order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """取消訂單"""
    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        # 檢查訂單狀態
        cursor.execute("SELECT status FROM orders WHERE id = %s", (order_id,))
        row = cursor.fetchone()

        if not row:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        if row['status'] not in ['PENDING', 'PARTIAL']:
            return jsonify({"status": "error", "message": f"Cannot cancel order with status: {row['status']}"}), 400

        cursor.execute('''
            UPDATE orders
            SET status = 'CANCELLED', cancelled_at = %s, updated_at = %s
            WHERE id = %s
        ''', (datetime.now(_TZ_TAIPEI).isoformat(), datetime.now(_TZ_TAIPEI).isoformat(), order_id))

        conn.commit()

    return jsonify({
        "status": "ok",
        "message": "Order cancelled"
    })


@orders_bp.route('/status/<status>', methods=['GET'])
def get_orders_by_status(status):
    """按狀態篩選訂單"""
    limit = int(request.args.get('limit', 100))

    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        cursor.execute('''
            SELECT * FROM orders
            WHERE status = %s
            ORDER BY created_at DESC
            LIMIT %s
        ''', (status.upper(), limit))

        rows = cursor.fetchall()

    orders = [row_to_dict(row) for row in rows]

    return jsonify({
        "status": "ok",
        "count": len(orders),
        "orders": orders
    })
