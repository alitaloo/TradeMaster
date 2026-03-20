#!/usr/bin/env python3
"""
Strategies API - 策略管理端點
只加載 Python 策略模塊的策略，不包含預定義的簡單策略
"""

import os
import glob
import ast
from flask import Blueprint, jsonify, request
from typing import Dict, List

strategies_bp = Blueprint('strategies', __name__, url_prefix='/api/v1/strategies')

# 策略目錄
STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'strategies')


def load_strategy_states():
    """從 DB 載入所有策略狀態"""
    from config.database import get_db_cursor
    states = {}
    try:
        with get_db_cursor() as c:
            c.execute("SELECT config_key, config_value FROM system_config WHERE config_key LIKE 'strategy.%.enabled'")
            for row in c.fetchall():
                strategy_id = row['config_key'].replace('strategy.', '').replace('.enabled', '')
                states[strategy_id] = {'enabled': row['config_value'] == 'true'}
    except Exception as e:
        print(f"Warning: Failed to load strategy states from DB: {e}")
    return states


def extract_strategy_info(file_path: str) -> List[Dict]:
    """從 Python 文件中提取策略信息"""
    strategies = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                has_base = any(
                    isinstance(base, ast.Name) and base.id == 'BaseStrategy'
                    for base in node.bases
                )
                
                if has_base:
                    name = node.name
                    
                    # 從 docstring 提取描述
                    description = ""
                    if node.body and isinstance(node.body[0], ast.Expr):
                        if isinstance(node.body[0].value, ast.Constant):
                            val = node.body[0].value.value
                            description = val if isinstance(val, str) else ""
                    
                    # 提取參數
                    params = {}
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            defaults = item.args.defaults
                            args = item.args.args
                            
                            for i, default in enumerate(defaults):
                                arg_name = args[-(len(defaults) - i)].arg
                                
                                if isinstance(default, ast.Constant):
                                    value = default.value
                                elif isinstance(default, ast.Tuple):
                                    value = tuple(v.value if isinstance(v, ast.Constant) else v.n for v in default.elts)
                                else:
                                    value = None
                                
                                if value is not None:
                                    params[arg_name] = value
                    
                    # 生成策略 ID
                    strategy_id = name.lower().replace(' ', '_')
                    
                    # 生成參數描述
                    params_str = ""
                    if 'rsi_period' in params:
                        rsi_p = params.get('rsi_period', 14)
                        oversold = params.get('oversold', 35)
                        overbought = params.get('overbought', 70)
                        params_str = f"RSI({rsi_p}/{oversold}/{overbought})"
                    elif 'fast_period' in params and 'slow_period' in params:
                        params_str = f"SMA({params.get('fast_period', 50)}/{params.get('slow_period', 200)})"
                    elif 'period' in params:
                        params_str = f"Period={params.get('period', 20)}"
                    
                    if 'stop_loss' in params and 'take_profit' in params:
                        params_str += f" SL={params.get('stop_loss', 0.05):.0%} TP={params.get('take_profit', 0.10):.0%}"
                    
                    # 基於策略類型估算報酬和夏普
                    name_lower = name.lower()
                    if 'momentum' in name_lower or 'breakout' in name_lower or 'dual' in name_lower:
                        default_return = 35.2
                        default_sharpe = 2.1
                    elif 'mean_reversion' in name_lower or 'reversal' in name_lower:
                        default_return = 28.5
                        default_sharpe = 1.8
                    elif 'trend' in name_lower:
                        default_return = 22.0
                        default_sharpe = 1.5
                    elif 'volatility' in name_lower:
                        default_return = 25.0
                        default_sharpe = 1.9
                    elif 'quality' in name_lower:
                        default_return = 40.0
                        default_sharpe = 2.5
                    elif 'advanced' in name_lower:
                        default_return = 45.0
                        default_sharpe = 2.8
                    else:
                        default_return = 15.0
                        default_sharpe = 1.0
                    
                    strategies.append({
                        "id": strategy_id,
                        "name": name.replace('_', ' '),
                        "description": description or f"{name} 策略",
                        "params": params_str or "預設參數",
                        "return": default_return,
                        "sharpe": default_sharpe,
                        "enabled": True,
                        "is_loaded": True,
                        "file": os.path.basename(file_path)
                    })
    
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
    
    return strategies


def load_strategies_from_files() -> List[Dict]:
    """從策略文件加載所有策略"""
    strategies = []
    
    # 只加載策略模塊目錄
    strategy_files = glob.glob(os.path.join(STRATEGIES_DIR, '**/*.py'), recursive=True)
    
    for file_path in strategy_files:
        if '__pycache__' in file_path:
            continue
        file_strategies = extract_strategy_info(file_path)
        strategies.extend(file_strategies)
    
    return strategies


def load_strategies():
    """加載所有策略（只從策略模塊）"""
    strategies = []
    
    # 從策略文件加載
    file_strategies = load_strategies_from_files()
    strategies.extend(file_strategies)
    
    return strategies


# 內存中的策略狀態
strategy_states = {}

# 動態創建的策略
custom_strategies = {}


@strategies_bp.route('', methods=['GET'])
def get_strategies():
    """獲取所有策略"""
    # 從 DB 載入策略狀態
    global strategy_states
    strategy_states.update(load_strategy_states())
    
    strategies = load_strategies()
    
    # 嘗試從 stock_strategies 表獲取真實數據
    indicator_stats = {}
    try:
        from config.database import get_db_cursor
        with get_db_cursor() as c:
            c.execute("""
                SELECT indicator,
                       AVG(CAST(return_pct AS DECIMAL(10,4))) as avg_return,
                       AVG(CAST(sharpe AS DECIMAL(10,4))) as avg_sharpe,
                       AVG(CAST(win_rate AS DECIMAL(10,4))) as avg_win_rate,
                       COUNT(*) as data_points
                FROM stock_strategies
                GROUP BY indicator
            """)
            for row in c.fetchall():
                indicator_stats[row['indicator']] = {
                    'avg_return': float(row['avg_return']) if row['avg_return'] else None,
                    'avg_sharpe': float(row['avg_sharpe']) if row['avg_sharpe'] else None,
                    'avg_win_rate': float(row['avg_win_rate']) if row['avg_win_rate'] else None,
                    'data_points': row['data_points']
                }
    except Exception as e:
        print(f"Warning: Failed to load indicator stats from DB: {e}")
    
    # 合併狀態並標記數據來源
    for s in strategies:
        s_id = s.get('id')
        if s_id in strategy_states:
            s['enabled'] = strategy_states[s_id]['enabled']
        
        # 嘗試匹配 indicator
        # 根據策略名稱和 stock_strategies 的 indicator 進行匹配
        matched = False
        for indicator_name, stats in indicator_stats.items():
            # 簡單匹配：策略名稱包含 indicator 名稱的部分
            s_name_lower = s.get('name', '').lower().replace(' ', '')
            indicator_lower = indicator_name.lower().replace('_', '')
            if indicator_lower in s_name_lower or s_name_lower in indicator_lower:
                if stats['avg_return'] is not None:
                    s['return'] = round(stats['avg_return'], 2)
                    s['sharpe'] = round(stats['avg_sharpe'], 2) if stats['avg_sharpe'] else s.get('sharpe', 0)
                    s['win_rate'] = round(stats['avg_win_rate'] * 100, 2) if stats['avg_win_rate'] else None
                    s['data_source'] = 'real'
                    s['data_points'] = stats['data_points']
                    matched = True
                    break
        
        # 如果沒有匹配到真實數據，標記為估算
        if not matched:
            s['data_source'] = 'estimated'
    
    # 添加自定義策略
    for cid, cs in custom_strategies.items():
        cs_copy = cs.copy()
        cs_copy['data_source'] = 'custom'
        strategies.append(cs_copy)
        if cid in strategy_states:
            cs_copy['enabled'] = strategy_states[cid]['enabled']
    
    return jsonify({
        "status": "ok",
        "count": len(strategies),
        "strategies": strategies
    })


@strategies_bp.route('', methods=['POST'])
def create_strategy():
    """創建新策略"""
    data = request.json
    
    if not data:
        return jsonify({
            "status": "error",
            "message": "Request body is required"
        }), 400
    
    required_fields = ['name', 'rsi_period', 'oversold', 'overbought']
    for field in required_fields:
        if field not in data:
            return jsonify({
                "status": "error",
                "message": f"Missing required field: {field}"
            }), 400
    
    import uuid
    strategy_id = f"custom_{uuid.uuid4().hex[:8]}"
    
    strategy = {
        "id": strategy_id,
        "name": data['name'],
        "rsi_period": data['rsi_period'],
        "oversold": data['oversold'],
        "overbought": data['overbought'],
        "stop_loss": data.get('stop_loss', 0.05),
        "take_profit": data.get('take_profit', 0.10),
        "enabled": data.get('enabled', True),
        "params": f"RSI({data['rsi_period']}/{data['oversold']}/{data['overbought']}) SL={data.get('stop_loss', 0.05):.0%} TP={data.get('take_profit', 0.10):.0%}",
        "return": 0.0,
        "sharpe": 0.0,
        "description": data.get('description', '自定義 RSI 策略'),
        "is_custom": True
    }
    
    custom_strategies[strategy_id] = strategy
    strategy_states[strategy_id] = {'enabled': strategy['enabled']}
    
    return jsonify({
        "status": "ok",
        "message": "Strategy created successfully",
        "strategy": strategy
    }), 201


@strategies_bp.route('/<strategy_id>', methods=['PUT'])
def update_strategy(strategy_id):
    """更新策略"""
    data = request.json
    
    if not data:
        return jsonify({
            "status": "error",
            "message": "Request body is required"
        }), 400
    
    strategies = load_strategies()
    existing = next((s for s in strategies if s.get('id') == strategy_id), None)
    
    if not existing and strategy_id not in custom_strategies:
        return jsonify({
            "status": "error",
            "message": "Strategy not found"
        }), 404
    
    if strategy_id in custom_strategies:
        strategy = custom_strategies[strategy_id]
        allowed_fields = ['name', 'rsi_period', 'oversold', 'overbought', 'stop_loss', 'take_profit', 'enabled', 'description']
        for field in allowed_fields:
            if field in data:
                strategy[field] = data[field]
        strategy['params'] = f"RSI({strategy['rsi_period']}/{strategy['oversold']}/{strategy['overbought']}) SL={strategy['stop_loss']:.0%} TP={strategy['take_profit']:.0%}"
        if 'enabled' in data:
            # 持久化到 DB
            from config.database import get_db_cursor
            try:
                with get_db_cursor() as c:
                    c.execute("""
                        INSERT INTO system_config (config_key, config_value)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE config_value = %s
                    """, (f'strategy.{strategy_id}.enabled', str(data['enabled']).lower(), str(data['enabled']).lower()))
            except Exception as e:
                return jsonify({
                    "status": "error",
                    "message": f"Failed to persist strategy state: {str(e)}"
                }), 500
            strategy_states[strategy_id] = {'enabled': data['enabled']}
    else:
        if 'enabled' in data:
            # 持久化到 DB
            from config.database import get_db_cursor
            try:
                with get_db_cursor() as c:
                    c.execute("""
                        INSERT INTO system_config (config_key, config_value)
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE config_value = %s
                    """, (f'strategy.{strategy_id}.enabled', str(data['enabled']).lower(), str(data['enabled']).lower()))
            except Exception as e:
                return jsonify({
                    "status": "error",
                    "message": f"Failed to persist strategy state: {str(e)}"
                }), 500
            strategy_states[strategy_id] = {'enabled': data['enabled']}
    
    return jsonify({
        "status": "ok",
        "message": "Strategy updated successfully",
        "strategy_id": strategy_id
    })


@strategies_bp.route('/<strategy_id>', methods=['DELETE'])
def delete_strategy(strategy_id):
    """刪除策略"""
    if strategy_id not in custom_strategies:
        return jsonify({
            "status": "error",
            "message": "Can only delete custom strategies"
        }), 403
    
    del custom_strategies[strategy_id]
    if strategy_id in strategy_states:
        del strategy_states[strategy_id]
    
    return jsonify({
        "status": "ok",
        "message": "Strategy deleted successfully"
    })


@strategies_bp.route('/<strategy_id>', methods=['GET'])
def get_strategy(strategy_id):
    """獲取特定策略"""
    strategies = load_strategies()
    strategy = next((s for s in strategies if s.get('id') == strategy_id), None)
    
    if not strategy:
        return jsonify({
            "status": "error",
            "message": "Strategy not found"
        }), 404
    
    return jsonify({
        "status": "ok",
        "strategy": strategy
    })


@strategies_bp.route('/<strategy_id>/toggle', methods=['PUT', 'POST'])
def toggle_strategy(strategy_id):
    """切換策略狀態"""
    data = request.json or {}
    enabled = data.get('enabled', True)
    
    # 先確認策略存在（不要用 strategy_states 判斷）
    strategies = load_strategies()
    strategy = next((s for s in strategies if s.get('id') == strategy_id), None)
    
    if not strategy:
        # 檢查是否為自定義策略
        if strategy_id not in custom_strategies:
            return jsonify({
                "status": "error",
                "message": "Strategy not found"
            }), 404
    
    # 存到 system_config
    from config.database import get_db_cursor
    try:
        with get_db_cursor() as c:
            c.execute("""
                INSERT INTO system_config (config_key, config_value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE config_value = %s
            """, (f'strategy.{strategy_id}.enabled', str(enabled).lower(), str(enabled).lower()))
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to persist strategy state: {str(e)}"
        }), 500
    
    # 同步記憶體
    strategy_states[strategy_id] = {'enabled': enabled}
    
    return jsonify({
        "status": "ok",
        "strategy_id": strategy_id,
        "enabled": enabled
    })


@strategies_bp.route('/enabled', methods=['GET'])
def get_enabled_strategies():
    """獲取已啟用的策略"""
    # 從 DB 載入策略狀態
    global strategy_states
    strategy_states.update(load_strategy_states())
    
    strategies = load_strategies()
    enabled = [s for s in strategies if strategy_states.get(s.get('id'), {}).get('enabled', True)]
    
    return jsonify({
        "status": "ok",
        "count": len(enabled),
        "strategies": enabled
    })


@strategies_bp.route('/top', methods=['GET'])
def get_top_strategies():
    """獲取表現最好的策略"""
    # 從 DB 載入策略狀態
    global strategy_states
    strategy_states.update(load_strategy_states())
    
    strategies = load_strategies()
    
    # 嘗試從 stock_strategies 表獲取真實數據
    indicator_stats = {}
    try:
        from config.database import get_db_cursor
        with get_db_cursor() as c:
            c.execute("""
                SELECT indicator,
                       AVG(CAST(return_pct AS DECIMAL(10,4))) as avg_return,
                       AVG(CAST(sharpe AS DECIMAL(10,4))) as avg_sharpe,
                       AVG(CAST(win_rate AS DECIMAL(10,4))) as avg_win_rate,
                       COUNT(*) as data_points
                FROM stock_strategies
                GROUP BY indicator
            """)
            for row in c.fetchall():
                indicator_stats[row['indicator']] = {
                    'avg_return': float(row['avg_return']) if row['avg_return'] else None,
                    'avg_sharpe': float(row['avg_sharpe']) if row['avg_sharpe'] else None,
                    'avg_win_rate': float(row['avg_win_rate']) if row['avg_win_rate'] else None,
                    'data_points': row['data_points']
                }
    except Exception as e:
        print(f"Warning: Failed to load indicator stats from DB: {e}")
    
    # 應用真實數據
    for s in strategies:
        matched = False
        for indicator_name, stats in indicator_stats.items():
            s_name_lower = s.get('name', '').lower().replace(' ', '')
            indicator_lower = indicator_name.lower().replace('_', '')
            if indicator_lower in s_name_lower or s_name_lower in indicator_lower:
                if stats['avg_return'] is not None:
                    s['return'] = round(stats['avg_return'], 2)
                    s['sharpe'] = round(stats['avg_sharpe'], 2) if stats['avg_sharpe'] else s.get('sharpe', 0)
                    s['data_source'] = 'real'
                    matched = True
                    break
        if not matched:
            s['data_source'] = 'estimated'
    
    top = sorted(strategies, key=lambda x: x.get('sharpe', 0), reverse=True)[:5]
    
    return jsonify({
        "status": "ok",
        "top_strategies": top
    })
