#!/usr/bin/env python3
"""
Fox Agent 分析腳本
調用 Fox Agent 對每支股票獨立分析，寫入數據庫

流程：
1. 讀取持倉 config 表
2. 每支股票獨立調用 Agent 分析
3. 解析 JSON 返回
4. 寫入 signals 表
"""

import requests
import json
import logging
import os
import sys
import mysql.connector
import time
from datetime import datetime

os.environ.setdefault('NO_PROXY', 'localhost,127.0.0.1')

# MySQL 配置 - 從統一配置導入
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from config.database import MYSQL_CONFIG as DB_CONFIG
except ImportError:
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'alita',
        'password': 'alitamysql',
        'database': 'trademaster'
    }

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

API_BASE = 'http://localhost:8080/api/v1'


def api_get(endpoint):
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"API GET 失敗: {url} - {e}")
        return {}


def get_positions():
    """獲取持倉"""
    result = api_get('/positions')
    if result.get('status') == 'ok':
        return result.get('positions', [])
    return []


def get_config():
    """獲取配置"""
    result = api_get('/config')
    if result.get('status') == 'ok':
        return result.get('config', {})
    return {}


def get_current_price(symbol: str) -> float:
    """獲取股票當前價格"""
    try:
        result = api_get(f'/kline/{symbol}?timeframe=1d&limit=1')
        if result.get('status') == 'ok':
            data = result.get('data', [])
            if data:
                return float(data[-1].get('close', 0))
    except:
        pass
    return 0.0


def analyze_with_agent(position: dict, config: dict) -> dict:
    """
    調用 Fox Agent 分析單支股票
    """
    symbol = position.get('symbol', 'UNKNOWN')
    quantity = position.get('quantity', 0)
    avg_price = position.get('avg_price', 0)
    current_price = get_current_price(symbol)
    if current_price == 0:
        current_price = avg_price
    
    # 計算損益
    if avg_price > 0 and current_price > 0:
        pnl_pct = ((current_price - avg_price) / avg_price) * 100
    else:
        pnl_pct = 0
    
    total_capital = config.get('total_capital', 50000)
    
    # 構建 prompt
    prompt = f"""你是 Fox Analyst Agent，專業金融分析師。

## 持倉數據
- 股票: {symbol}
- 數量: {quantity} 股
- 成本均價: ${avg_price:.2f}
- 目前價格: ${current_price:.2f}
- 損益: {pnl_pct:.1f}%
- 總資金: ${total_capital}

## 任務
請分析這個持倉，考慮：
1. 技術指標信號
2. 市場整體狀況
3. 風險管理

返回 JSON 格式決策：
{{
  "symbol": "{symbol}",
  "action": "BUY/SELL/HOLD",
  "quantity": 股數,
  "price": 價格,
  "confidence": 0.0-1.0,
  "reason": "原因說明"
}}

只返回 JSON。"""

    try:
        # 調用 sessions_spawn
        response = requests.post(
            "http://localhost:50020/api/sessions",
            json={
                "agentId": "main",
                "task": prompt,
                "model": "minimax/MiniMax-M2.5",
                "timeoutSeconds": 60
            },
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            session_key = result.get('sessionKey')
            
            if session_key:
                # 等待 Agent 完成 (最多 30 秒)
                for i in range(30):
                    time.sleep(1)
                    history_resp = requests.get(
                        f"http://localhost:50020/api/sessions/{session_key}/history",
                        timeout=10
                    )
                    
                    if history_resp.status_code == 200:
                        history = history_resp.json()
                        messages = history.get('messages', [])
                        
                        # 找最後一條 assistant 消息
                        for msg in reversed(messages):
                            if msg.get('role') == 'assistant':
                                content_list = msg.get('content', [])
                                for c in content_list:
                                    if c.get('type') == 'text':
                                        text = c.get('text', '')
                                        # 解析 JSON
                                        try:
                                            start = text.find('{')
                                            end = text.rfind('}') + 1
                                            if start >= 0 and end > start:
                                                json_str = text[start:end]
                                                return json.loads(json_str)
                                        except:
                                            pass
                
                logger.warning(f"   ⚠️ Agent 超時未返回結果")
        
    except Exception as e:
        logger.error(f"   ❌ Agent 調用失敗: {e}")
    
    # 如果失敗，返回默認 HOLD
    return {
        "symbol": symbol,
        "action": "HOLD",
        "quantity": 0,
        "price": current_price,
        "confidence": 0.5,
        "reason": "Agent 分析失敗，維持觀望"
    }


def write_signal_to_db(symbol: str, action: str, quantity: int, price: float, 
                       confidence: float, reason: str) -> bool:
    """寫入信號到數據庫"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # HOLD 信號標記為 IGNORED，不進行處理
        status = 'IGNORED' if action == 'HOLD' else 'PENDING'
        
        cursor.execute("""
            INSERT INTO signals 
            (symbol, signal_type, price, quantity, confidence, status, strategy_type, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            symbol, action, price, quantity, confidence, status, 'fox_agent',
            json.dumps({
                'reason': reason,
                'created_at': datetime.now().isoformat()
            })
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ 信號寫入成功: {symbol} {action} {quantity}股 @ ${price:.2f}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 寫入失敗: {e}")
        return False


def main():
    logger.info("=" * 60)
    logger.info("🦊 Fox Agent 分析開始")
    logger.info("=" * 60)
    
    # 1. 讀取配置
    config = get_config()
    logger.info(f"📊 總資金: ${config.get('total_capital', 50000)}")
    
    # 2. 讀取持倉
    positions = get_positions()
    if not positions:
        logger.warning("⚠️ 沒有持倉，跳過")
        return
    
    logger.info(f"📊 找到 {len(positions)} 個持倉")
    
    # 3. 每支股票調用 Agent 分析
    signal_count = 0
    for pos in positions:
        symbol = pos.get('symbol')
        logger.info(f"\n🔄 分析 {symbol}...")
        
        # 調用 Agent
        result = analyze_with_agent(pos, config)
        
        logger.info(f"   📊 {result.get('symbol')}: {result.get('action')} "
                   f"{result.get('quantity')}股 @ ${result.get('price'):.2f} "
                   f"(信心度: {result.get('confidence')})")
        logger.info(f"      原因: {result.get('reason')}")
        
        # 寫入數據庫
        action = result.get('action', 'HOLD')
        quantity = result.get('quantity', 0)
        
        if action in ['BUY', 'SELL'] and quantity > 0:
            success = write_signal_to_db(
                result.get('symbol'),
                action,
                quantity,
                result.get('price', 0),
                result.get('confidence', 0.5),
                result.get('reason', '')
            )
            if success:
                signal_count += 1
        else:
            logger.info(f"   ⏭️ HOLD，不寫入")
    
    logger.info("=" * 60)
    logger.info(f"✅ Fox Agent 分析完成")
    logger.info(f"   總持倉數: {len(positions)}")
    logger.info(f"   產生信號數: {signal_count}")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
