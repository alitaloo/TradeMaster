#!/usr/bin/env python3
"""
Backtests API - 回測結果端點
"""

import os
import glob
import csv
import uuid
import threading
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from config.database import get_db_cursor

backtests_bp = Blueprint('backtests', __name__, url_prefix='/api/v1/backtests')

# 回測結果目錄
BACKTEST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'backtest_results')


def load_backtest_results():
    """加載所有回測結果"""
    results = []
    csv_files = glob.glob(os.path.join(BACKTEST_DIR, '*.csv'))
    
    for file_path in csv_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row['file'] = os.path.basename(file_path)
                    # 轉換數值類型
                    for key in ['return', 'sharpe', 'max_dd', 'total_trades']:
                        if key in row:
                            try:
                                row[key] = float(row[key])
                            except:
                                pass
                    results.append(row)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    return results


def parse_md_report(file_path):
    """解析 MD 格式的回測報告"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 簡單解析
            return {
                "file": os.path.basename(file_path),
                "content": content[:1000],  # 截取前1000字符
                "parsed": True
            }
    except Exception as e:
        return {"file": os.path.basename(file_path), "error": str(e)}


@backtests_bp.route('', methods=['GET'])
def get_backtests():
    """獲取所有回測結果"""
    results = load_backtest_results()
    
    # 可選過濾
    strategy = request.args.get('strategy')
    symbol = request.args.get('symbol')
    
    if strategy:
        results = [r for r in results if strategy.lower() in r.get('strategy', '').lower()]
    if symbol:
        results = [r for r in results if r.get('symbol', '').upper() == symbol.upper()]
    
    return jsonify({
        "status": "ok",
        "count": len(results),
        "backtests": results
    })


@backtests_bp.route('/strategy/<strategy_name>', methods=['GET'])
def get_backtests_by_strategy(strategy_name):
    """獲取特定策略的回測結果"""
    results = load_backtest_results()
    strategy_results = [r for r in results if strategy_name.lower() in r.get('strategy', '').lower()]
    
    return jsonify({
        "status": "ok",
        "strategy": strategy_name,
        "count": len(strategy_results),
        "backtests": strategy_results
    })


@backtests_bp.route('/symbol/<symbol>', methods=['GET'])
def get_backtests_by_symbol(symbol):
    """獲取特定股票的回測結果"""
    results = load_backtest_results()
    symbol_results = [r for r in results if r.get('symbol', '').upper() == symbol.upper()]
    
    return jsonify({
        "status": "ok",
        "symbol": symbol.upper(),
        "count": len(symbol_results),
        "backtests": symbol_results
    })


@backtests_bp.route('/top', methods=['GET'])
def get_top_backtests():
    """獲取表現最好的回測結果"""
    results = load_backtest_results()
    
    # 按報酬排序
    top_by_return = sorted(results, key=lambda x: x.get('return', 0), reverse=True)[:5]
    # 按夏普排序
    top_by_sharpe = sorted(results, key=lambda x: x.get('sharpe', 0), reverse=True)[:5]
    
    return jsonify({
        "status": "ok",
        "top_by_return": top_by_return,
        "top_by_sharpe": top_by_sharpe
    })


@backtests_bp.route('/statistics', methods=['GET'])
def get_backtests_statistics():
    """獲取回測統計"""
    results = load_backtest_results()
    
    if not results:
        return jsonify({
            "status": "ok",
            "total_backtests": 0,
            "avg_return": 0,
            "avg_sharpe": 0,
            "strategies": [],
            "symbols": []
        })
    
    strategies = list(set(r.get('strategy') for r in results))
    symbols = list(set(r.get('symbol') for r in results))
    
    returns = [r.get('return', 0) for r in results]
    sharpes = [r.get('sharpe', 0) for r in results]
    
    return jsonify({
        "status": "ok",
        "total_backtests": len(results),
        "avg_return": sum(returns) / len(returns) if returns else 0,
        "avg_sharpe": sum(sharpes) / len(sharpes) if sharpes else 0,
        "strategies": sorted(strategies),
        "symbols": sorted(symbols)
    })


# ============== 新增：前端觸發回測 API ==============

def get_data(symbol: str, timeframe: str, days: int = 365):
    """從 kline_cache 獲取數據"""
    from config.database import get_db_cursor
    import pandas as pd
    
    # 根據週期調整天數
    if timeframe == '5m':
        days = 30
    elif timeframe == '1h':
        days = 400
    else:
        days = 365
    
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    with get_db_cursor() as c:
        c.execute("""
            SELECT timestamp, open_price, high_price, low_price, close_price, volume
            FROM kline_cache
            WHERE symbol = %s AND interval_val = %s
            AND timestamp >= %s
            ORDER BY timestamp ASC
        """, (symbol, timeframe, cutoff))
        rows = c.fetchall()
    
    if not rows:
        return None
    
    # 處理字典格式的結果
    if rows and isinstance(rows[0], dict):
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            'timestamp': 'timestamp',
            'open_price': 'open',
            'high_price': 'high',
            'low_price': 'low',
            'close_price': 'close',
            'volume': 'volume'
        })
    else:
        df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    return df


def calculate_indicators():
    """指標計算函數"""
    import pandas as pd
    import numpy as np
    
    def calculate_rsi(df, period=14):
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def calculate_macd(df, fast=12, slow=26, signal=9):
        ema_fast = df['close'].ewm(span=fast).mean()
        ema_slow = df['close'].ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        return macd, signal_line, macd - signal_line
    
    def calculate_sma(df, period):
        return df['close'].rolling(window=period).mean()
    
    def calculate_ema(df, period):
        return df['close'].ewm(span=period).mean()
    
    def calculate_bollinger(df, period=20, std_dev=2):
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        return sma + (std * std_dev), sma, sma - (std * std_dev)
    
    return {
        'calculate_rsi': calculate_rsi,
        'calculate_macd': calculate_macd,
        'calculate_sma': calculate_sma,
        'calculate_ema': calculate_ema,
        'calculate_bollinger': calculate_bollinger
    }


def run_backtest_for_indicator(df, indicator, params, symbol, timeframe):
    """對單一指標進行回測"""
    import pandas as pd
    import numpy as np
    
    if df is None or len(df) < 50:
        return None
    
    df = df.copy()
    ind_funcs = calculate_indicators()
    
    # 根據指標生成信號
    if indicator == 'RSI':
        df['rsi'] = ind_funcs['calculate_rsi'](df, params.get('period', 14))
        df['signal'] = 0
        df.loc[df['rsi'] < params.get('oversold', 30), 'signal'] = 1
        df.loc[df['rsi'] > params.get('overbought', 70), 'signal'] = -1
        
    elif indicator == 'RSI_7':
        df['rsi'] = ind_funcs['calculate_rsi'](df, params.get('period', 7))
        df['signal'] = 0
        df.loc[df['rsi'] < params.get('oversold', 25), 'signal'] = 1
        df.loc[df['rsi'] > params.get('overbought', 75), 'signal'] = -1
        
    elif indicator == 'MACD':
        macd, signal_line, hist = ind_funcs['calculate_macd'](df, params.get('fast', 12), params.get('slow', 26), params.get('signal', 9))
        df['signal'] = 0
        df.loc[hist > 0, 'signal'] = 1
        df.loc[hist < 0, 'signal'] = -1
        
    elif indicator == 'SMA_Cross':
        df['sma_fast'] = ind_funcs['calculate_sma'](df, params.get('fast', 10))
        df['sma_slow'] = ind_funcs['calculate_sma'](df, params.get('slow', 50))
        df['signal'] = 0
        df.loc[df['sma_fast'] > df['sma_slow'], 'signal'] = 1
        df.loc[df['sma_fast'] < df['sma_slow'], 'signal'] = -1
        
    elif indicator == 'EMA_Cross':
        df['ema_fast'] = ind_funcs['calculate_ema'](df, params.get('fast', 12))
        df['ema_slow'] = ind_funcs['calculate_ema'](df, params.get('slow', 26))
        df['signal'] = 0
        df.loc[df['ema_fast'] > df['ema_slow'], 'signal'] = 1
        df.loc[df['ema_fast'] < df['ema_slow'], 'signal'] = -1
        
    elif indicator == 'Bollinger':
        upper, middle, lower = ind_funcs['calculate_bollinger'](df, params.get('period', 20), params.get('std', 2))
        df['signal'] = 0
        df.loc[df['close'] < lower, 'signal'] = 1
        df.loc[df['close'] > upper, 'signal'] = -1
        
    elif indicator == 'VolumeMA_Crossover':
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['signal'] = 0
        df.loc[df['volume'] > df['volume_ma'] * 1.5, 'signal'] = 1
        df.loc[df['volume'] < df['volume_ma'] * 0.5, 'signal'] = -1
        
    elif indicator == 'VolumePrice_Confirm':
        df['price_change'] = df['close'].pct_change()
        df['volume_change'] = df['volume'].pct_change()
        df['signal'] = 0
        df.loc[(df['price_change'] > 0) & (df['volume_change'] > 0), 'signal'] = 1
        df.loc[(df['price_change'] < 0) & (df['volume_change'] > 0), 'signal'] = -1
        
    elif indicator == 'VWAP_Reversion':
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
        df['signal'] = 0
        df.loc[df['close'] < df['vwap'] * 0.98, 'signal'] = 1
        df.loc[df['close'] > df['vwap'] * 1.02, 'signal'] = -1
        
    else:
        return None
    
    # 回測
    position = 0
    trades = []
    capital = 100000
    shares = 0
    entry_price = 0
    
    for i in range(1, len(df)):
        if pd.isna(df['signal'].iloc[i]):
            continue
        if df['signal'].iloc[i] == 1 and position == 0:
            shares = capital / df['close'].iloc[i]
            position = 1
            entry_price = df['close'].iloc[i]
        elif df['signal'].iloc[i] == -1 and position == 1:
            pnl = (df['close'].iloc[i] - entry_price) / entry_price
            trades.append(pnl)
            capital = shares * df['close'].iloc[i]
            position = 0
            shares = 0
    
    if len(trades) == 0:
        return {'trades': 0, 'total_return': 0, 'win_rate': 0, 'sharpe': 0, 'max_dd': 0, 'symbol': symbol, 'timeframe': timeframe, 'indicator': indicator}
    
    total_return = (capital - 100000) / 100000
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    win_rate = len(wins) / len(trades) if trades else 0
    
    # 最大回撤
    cumulative = [1]
    for t in trades:
        cumulative.append(cumulative[-1] * (1 + t))
    max_dd = 0
    peak = 1
    for c in cumulative:
        if c > peak:
            peak = c
        dd = (peak - c) / peak
        if dd > max_dd:
            max_dd = dd
    
    # 夏普比率
    if np.std(trades) > 0:
        sharpe = (np.mean(trades) / np.std(trades)) * np.sqrt(252)
    else:
        sharpe = 0
    
    # 分數 = 夏普 * 10 + 報酬 * 100
    score = sharpe * 10 + total_return * 100
    
    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'indicator': indicator,
        'total_return': total_return,
        'win_rate': win_rate,
        'trades': len(trades),
        'sharpe': sharpe,
        'max_dd': max_dd,
        'score': score
    }


# 指標默認參數
INDICATOR_PARAMS = {
    'RSI': {'period': 14, 'oversold': 30, 'overbought': 70},
    'RSI_7': {'period': 7, 'oversold': 25, 'overbought': 75},
    'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
    'SMA_Cross': {'fast': 10, 'slow': 50},
    'EMA_Cross': {'fast': 12, 'slow': 26},
    'Bollinger': {'period': 20, 'std': 2},
    'VolumeMA_Crossover': {'volume_ma_period': 20},
    'VolumePrice_Confirm': {},
    'VWAP_Reversion': {},
}


def run_backtest_task(run_id, symbols, timeframes, indicators):
    """背景執行回測"""
    total = len(symbols) * len(timeframes) * len(indicators)
    completed = 0
    results = []
    
    with get_db_cursor() as c:
        c.execute("UPDATE backtest_runs SET total=%s, started_at=NOW() WHERE batch_id=%s", (total, run_id))
    
    for symbol in symbols:
        for tf in timeframes:
            df = get_data(symbol, tf)
            if df is None or len(df) < 50:
                completed += len(indicators)
                with get_db_cursor() as c:
                    c.execute("UPDATE backtest_runs SET completed=%s, status='running' WHERE batch_id=%s",
                              (completed, run_id))
                continue
            
            for indicator in indicators:
                try:
                    params = INDICATOR_PARAMS.get(indicator, {})
                    result = run_backtest_for_indicator(df, indicator, params, symbol, tf)
                    if result:
                        results.append(result)
                except Exception as e:
                    print(f"Error running backtest for {symbol}/{tf}/{indicator}: {e}")
                
                completed += 1
                with get_db_cursor() as c:
                    c.execute("UPDATE backtest_runs SET completed=%s, status='running' WHERE batch_id=%s",
                              (completed, run_id))
    
    # 完成：寫入結果 + 更新狀態
    with get_db_cursor() as c:
        for r in results:
            c.execute("""
                INSERT INTO stock_strategies (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades, score, batch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE sharpe=%s, return_pct=%s, win_rate=%s, trades=%s, batch_id=%s, updated_at=NOW()
            """, (r['symbol'], r['timeframe'], r['indicator'], '{}',
                  r.get('sharpe', 0), r.get('total_return', 0),
                  r.get('win_rate', 0), r.get('trades', 0), r.get('score', 0), run_id,
                  r.get('sharpe', 0), r.get('total_return', 0), r.get('win_rate', 0), r.get('trades', 0), run_id))
        
        c.execute("UPDATE backtest_runs SET status='completed', completed=%s WHERE batch_id=%s",
                  (total, run_id))


@backtests_bp.route('/run', methods=['POST'])
def trigger_backtest():
    """觸發回測 - POST /api/v1/backtests/run"""
    data = request.get_json() or {}
    
    symbols = data.get('symbols', [])
    timeframes = data.get('timeframes', ['1d'])
    indicators = data.get('indicators', ['RSI'])
    
    if not symbols:
        return jsonify({"status": "error", "message": "symbols is required"}), 400
    
    # 生成 run_id
    run_id = str(uuid.uuid4())
    total = len(symbols) * len(timeframes) * len(indicators)
    
    # 插入記錄
    with get_db_cursor() as c:
        c.execute("""
            INSERT INTO backtest_runs (batch_id, total, completed, status, notes)
            VALUES (%s, %s, 0, 'running', %s)
        """, (run_id, total, f"symbols={symbols}, timeframes={timeframes}, indicators={indicators}"))
    
    # 啟動背景執行緒
    thread = threading.Thread(target=run_backtest_task, args=(run_id, symbols, timeframes, indicators))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "ok",
        "run_id": run_id,
        "status": "running",
        "total": total
    })


@backtests_bp.route('/runs/<run_id>', methods=['GET'])
def get_backtest_status(run_id):
    """查詢回測進度 - GET /api/v1/backtests/runs/{run_id}"""
    with get_db_cursor() as c:
        c.execute("""
            SELECT batch_id, total, completed, status, started_at, created_at
            FROM backtest_runs
            WHERE batch_id = %s
        """, (run_id,))
        row = c.fetchone()
    
    if not row:
        return jsonify({"status": "error", "message": "Run not found"}), 404
    
    total = row['total'] or 0
    completed = row['completed'] or 0
    progress_pct = (completed / total * 100) if total > 0 else 0
    
    # 計算經過時間
    elapsed_seconds = 0
    if row['started_at']:
        elapsed_seconds = (datetime.now() - row['started_at']).total_seconds()
    
    return jsonify({
        "run_id": row['batch_id'],
        "status": row['status'] or 'pending',
        "total": total,
        "completed": completed,
        "progress_pct": round(progress_pct, 1),
        "elapsed_seconds": int(elapsed_seconds)
    })


@backtests_bp.route('/indicators', methods=['GET'])
def get_available_indicators():
    """取得可用的回測指標清單"""
    indicators = [
        {'value': 'RSI', 'label': 'RSI', 'desc': 'RSI(14) 超買超賣'},
        {'value': 'RSI_7', 'label': 'RSI-7', 'desc': 'RSI(7) 短週期版'},
        {'value': 'MACD', 'label': 'MACD', 'desc': 'MACD(12/26/9) 趨勢跟蹤'},
        {'value': 'SMA_Cross', 'label': 'SMA Cross', 'desc': 'SMA(10/50) 均線交叉'},
        {'value': 'EMA_Cross', 'label': 'EMA Cross', 'desc': 'EMA(12/26) 指數均線交叉'},
        {'value': 'Bollinger', 'label': 'Bollinger Bands', 'desc': '布林帶(20,2) 均值回歸'},
        {'value': 'VolumeMA_Crossover', 'label': 'Volume MA Crossover', 'desc': '成交量MA交叉'},
        {'value': 'VolumePrice_Confirm', 'label': 'Volume Price Confirm', 'desc': '量價確認'},
        {'value': 'VWAP_Reversion', 'label': 'VWAP Reversion', 'desc': 'VWAP均值回歸'},
    ]
    return jsonify({'status': 'ok', 'indicators': indicators, 'count': len(indicators)})


@backtests_bp.route('/runs/<run_id>/results', methods=['GET'])
def get_run_results(run_id):
    """取得回測結果 - GET /api/v1/backtests/runs/{run_id}/results"""
    with get_db_cursor() as c:
        c.execute("""
            SELECT symbol, timeframe, indicator, sharpe, return_pct, win_rate, trades, score, active, updated_at
            FROM stock_strategies
            WHERE batch_id = %s
            ORDER BY sharpe DESC
        """, (run_id,))
        rows = c.fetchall()
    
    results = []
    for r in rows:
        results.append({
            'symbol': r['symbol'],
            'timeframe': r['timeframe'],
            'indicator': r['indicator'],
            'sharpe': float(r['sharpe'] or 0),
            'return_pct': float(r['return_pct'] or 0),
            'win_rate': float(r['win_rate'] or 0),
            'trades': int(r['trades'] or 0),
            'score': float(r['score'] or 0),
            'active': bool(r['active']),
        })
    
    return jsonify({'status': 'ok', 'run_id': run_id, 'count': len(results), 'results': results})


# 用於標記 Fox 重載的全局變量
_fox_cache_loaded = False

@backtests_bp.route('/apply', methods=['POST'])
def apply_backtest_result():
    """啟用回測結果到信號系統 - POST /api/v1/backtests/apply"""
    global _fox_cache_loaded
    
    data = request.get_json() or {}
    
    symbol = data.get('symbol')
    timeframe = data.get('timeframe')
    indicator = data.get('indicator')
    
    if not symbol or not timeframe or not indicator:
        return jsonify({"status": "error", "message": "symbol, timeframe, indicator are required"}), 400
    
    # 更新 stock_strategies 表，設 active=1
    with get_db_cursor() as c:
        c.execute("""
            UPDATE stock_strategies
            SET active = 1, updated_at = NOW()
            WHERE symbol = %s AND timeframe = %s AND indicator = %s
        """, (symbol, timeframe, indicator))
        
        if c.rowcount == 0:
            return jsonify({"status": "error", "message": "Strategy not found"}), 404
    
    # 標記 Fox 重載
    _fox_cache_loaded = False
    
    # 嘗試通知 Fox 重載
    try:
        from scripts import fox_analysis_v2
        if hasattr(fox_analysis_v2, '_cache_loaded'):
            fox_analysis_v2._cache_loaded = False
    except Exception as e:
        print(f"Warning: Could not reload Fox cache: {e}")
    
    return jsonify({
        "status": "ok",
        "message": f"Strategy {symbol}/{timeframe}/{indicator} activated",
        "fox_cache_reloaded": False
    })
