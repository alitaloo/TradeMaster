#!/usr/bin/env python3
"""
Successor Push Script
Successor 信號推送腳本 - 查詢待推送信號，生成格式化消息，推送到 Telegram
自動判斷冬令時/夏令時

用法:
    python successor_push.py [--dry-run]

API Base: http://localhost:8080/api/v1
Telegram: Z (chatId: 7506814516)
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import argparse
import os
import subprocess

# 導入市場時間判斷模組
try:
    from market_hours import should_update_kline, is_dst_us
    HAS_MARKET_HOURS = True
except ImportError:
    HAS_MARKET_HOURS = False

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# API 配置
API_BASE = 'http://localhost:8080/api/v1'

# Telegram 配置
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = '7506814516'  # Z

# 信號模板
SIGNAL_TEMPLATE = """📈 {symbol} {direction} {action}
💰 ${price} | 📊 {quantity}股 | 💵 ${total}
🏷️ 信心度：{confidence}% | 🎯 止損：-{stop_loss}%
✅ 風控通過 | 📰 新聞無異常

⏰ {time} GMT+8"""


def api_get(endpoint: str, params: dict = None) -> dict:
    """發送 GET 請求"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"   requests 失敗，嘗試 curl: {e}")
        # Fallback to curl
        try:
            cmd = ['curl', '-s']
            if params:
                # Build query string manually
                query = '&'.join([f"{k}={v}" for k, v in params.items()])
                full_url = f"{url}?{query}"
                cmd.append(full_url)
            else:
                cmd.append(url)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except Exception as curl_err:
            logger.error(f"curl fallback 也失敗: {curl_err}")
        return {'status': 'error', 'message': str(e)}


def api_put(endpoint: str, data: dict) -> dict:
    """發送 PUT 請求"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.put(url, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"   requests PUT 失敗，嘗試 curl: {e}")
        # Fallback to curl
        try:
            cmd = ['curl', '-s', '-X', 'PUT', '-H', 'Content-Type: application/json', 
                   '-d', json.dumps(data), url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as curl_err:
            logger.error(f"curl PUT fallback 也失敗: {curl_err}")
        return {'status': 'error', 'message': str(e)}


def get_pending_signals() -> List[Dict]:
    """獲取待推送信號"""
    logger.info("📡 獲取待推送信號...")
    result = api_get('/signals', {'status': 'PENDING', 'limit': 20})
    
    if result.get('status') == 'ok':
        signals = result.get('signals', [])
        logger.info(f"   找到 {len(signals)} 個待推送信號")
        return signals
    else:
        logger.warning(f"   獲取信號失敗: {result.get('message')}")
        return []


def format_signal_message(signal: Dict) -> str:
    """
    格式化信號消息
    
    根據模板格式:
    📈 {股票} {方向} {買入/賣出}
    💰 ${價格} | 📊 {股數}股 | 💵 ${總額}
    🏷️ 信心度：{信心度}% | 🎯 止損：-{X}%
    ✅ 風控通過 | 📰 新聞無異常
    
    ⏰ {時間} GMT+8
    """
    symbol = signal.get('symbol', 'N/A')
    signal_type = signal.get('signal_type', 'HOLD')
    # 解析信號數值 - API 返回的是字符串
    try:
        price = float(signal.get('price', 0)) if signal.get('price') else 0.0
    except (ValueError, TypeError):
        price = 0.0
    
    try:
        quantity = int(signal.get('quantity', 0)) if signal.get('quantity') else 0
    except (ValueError, TypeError):
        quantity = 0
    
    try:
        confidence = float(signal.get('confidence', 0)) if signal.get('confidence') else 0.0
    except (ValueError, TypeError):
        confidence = 0.0
    
    try:
        stop_loss = float(signal.get('stop_loss', 5)) if signal.get('stop_loss') else 5.0
    except (ValueError, TypeError):
        stop_loss = 5.0
    
    # 方向映射
    direction_map = {
        'BUY': '📈 漲',
        'SELL': '📉 跌',
        'HOLD': '⏸️ 平'
    }
    direction = direction_map.get(signal_type, '❓')
    
    # 動作映射
    action_map = {
        'BUY': '買入',
        'SELL': '賣出',
        'HOLD': '觀望'
    }
    action = action_map.get(signal_type, '未知')
    
    # 計算總額
    total = price * quantity if price and quantity else 0.0
    
    # 風控狀態
    metadata = signal.get('metadata', {})
    # metadata 可能是 JSON 字符串，需要解析
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except:
            metadata = {}
    
    risk_score = signal.get('risk_score', 1)
    market_ok = metadata.get('market_ok', True) if isinstance(metadata, dict) else True
    news_ok = metadata.get('news_ok', True) if isinstance(metadata, dict) else True
    
    risk_status = "✅ 風控通過" if risk_score == 1 and market_ok and news_ok else "⚠️ 風控注意"
    news_status = "📰 新聞無異常" if news_ok else "⚠️ 新聞異常"
    
    # 時間
    created_at = signal.get('created_at')
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            # 轉換為 GMT+8
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            time_str = created_at
    else:
        time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    message = SIGNAL_TEMPLATE.format(
        symbol=symbol,
        direction=direction,
        action=action,
        price=f"{price:.2f}",
        quantity=quantity,
        total=f"{(price * quantity):.2f}",
        confidence=int(confidence * 100),
        stop_loss=f"{stop_loss:.1f}",
        time=time_str
    )
    
    # 添加風控狀態行
    message = message.replace(
        "✅ 風控通過 | 📰 新聞無異常",
        f"{risk_status} | {news_status}"
    )
    
    return message


def send_telegram_message(message: str, chat_id: str = None) -> bool:
    """
    發送 Telegram 消息
    
    使用 OpenClaw 的 message 工具
    """
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    
    logger.info(f"📤 發送 Telegram 消息到 {chat_id}...")
    
    # 嘗試使用 message 工具
    try:
        from tools import message
        response = message(
            action='send',
            target=chat_id,
            message=message
        )
        logger.info(f"   ✅ 消息發送成功")
        return True
    except Exception as e:
        logger.warning(f"   ⚠️ message 工具不可用: {e}")
        
        # 備用方案: 直接使用 requests 調用 Telegram API
        if TELEGRAM_BOT_TOKEN:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                data = {
                    'chat_id': chat_id,
                    'text': message,
                    'parse_mode': 'Markdown'
                }
                resp = requests.post(url, json=data, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"   ✅ 消息發送成功 (Telegram API)")
                    return True
                else:
                    logger.error(f"   ❌ Telegram API 失敗: {resp.text}")
                    return False
            except Exception as api_error:
                logger.error(f"   ❌ Telegram API 請求失敗: {api_error}")
                return False
        else:
            logger.warning("   ⚠️ 沒有配置 TELEGRAM_BOT_TOKEN，僅打印消息")
            print("\n" + "=" * 50)
            print("📱 Telegram 消息 (模擬發送):")
            print("=" * 50)
            print(message)
            print("=" * 50 + "\n")
            return True  # 模擬模式視為成功


def update_signal_status(signal_id: int, status: str = 'SENT') -> bool:
    """更新信號狀態"""
    result = api_put(f'/signals/{signal_id}', {'status': status})
    
    if result.get('status') == 'ok':
        logger.info(f"   ✅ 信號 {signal_id} 狀態更新為 {status}")
        return True
    else:
        logger.error(f"   ❌ 信號狀態更新失敗: {result.get('message')}")
        return False


def push_signals(dry_run: bool = False) -> List[Dict]:
    """
    執行信號推送 (自動去重)
    """
    # 這裡不安靜輸出，避免每次 Cron 都觸發通知
    # 只有當有 BUY/SELL 信號時才會觸發
    
    # 1. 獲取待推送信號
    signals = get_pending_signals()
    
    if not signals:
        logger.info("⚠️ 沒有待推送信號")
        return []
    
    # 2. 過濾掉 IGNORED 狀態的信號 (只推送 PENDING 的 BUY/SELL)
    signals_to_push = [s for s in signals if s.get('status') != 'IGNORED']
    ignored_count = len(signals) - len(signals_to_push)
    
    if ignored_count > 0:
        logger.info(f"   ℹ️ 過濾掉 {ignored_count} 個 IGNORED 信號 (不推送)")
    
    if not signals_to_push:
        logger.info("⚠️ 沒有需要推送的 BUY/SELL 信號")
        return []
    
    # 3. 去重：檢查是否已推送過相同的信號
    from datetime import datetime, timedelta, timedelta
    import json
    
    pushed_file = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/signals/pushed_signals.json'
    already_pushed = []
    
    try:
        with open(pushed_file, 'r') as f:
            already_pushed = json.load(f)
    except:
        pass
    
    # 清理超過 24 小時的記錄
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    already_pushed = [p for p in already_pushed if p.get('time', '') > cutoff]
    
    # 過濾掉已推送的信號
    final_signals = []
    for sig in signals_to_push:
        sig_key = f"{sig.get('symbol')}_{sig.get('signal_type')}"
        if sig_key not in [p.get('key', '') for p in already_pushed]:
            final_signals.append(sig)
        else:
            logger.info(f"   ⏭️ 跳過 {sig.get('symbol')} {sig.get('signal_type')} (已推送過)")
    
    if not final_signals:
        logger.info("⚠️ 所有信號都已推送過，跳過")
        return []
    
    signals_to_push = final_signals
    
    # 4. 遍歷並推送信號
    pushed_signals = []
    
    for signal in signals_to_push:
        signal_id = signal.get('id')
        symbol = signal.get('symbol')
        
        logger.info(f"\n🔔 處理信號 #{signal_id}: {symbol}")
        
        # 格式化消息
        message = format_signal_message(signal)
        logger.info(f"   消息內容:")
        for line in message.split('\n'):
            logger.info(f"      {line}")
        
        if dry_run:
            logger.info(f"   [Dry Run] 模擬推送信號")
            pushed_signals.append({
                'signal_id': signal_id,
                'symbol': symbol,
                'status': 'SENT (dry-run)'
            })
        else:
            # 發送到 Telegram
            success = send_telegram_message(message)
            
            if success:
                # 更新狀態為 SENT
                if update_signal_status(signal_id, 'SENT'):
                    pushed_signals.append({
                        'signal_id': signal_id,
                        'symbol': symbol,
                        'status': 'SENT'
                    })
                else:
                    pushed_signals.append({
                        'signal_id': signal_id,
                        'symbol': symbol,
                        'status': 'SEND_OK_BUT_UPDATE_FAILED'
                    })
            else:
                logger.error(f"   ❌ 推送失敗")
                pushed_signals.append({
                    'signal_id': signal_id,
                    'symbol': symbol,
                    'status': 'FAILED'
                })
    
    # 總結
    logger.info("\n" + "=" * 60)
    logger.info("📊 Successor Push 完成")
    logger.info(f"   總待推送: {len(signals)}")
    logger.info(f"   推送成功: {len(pushed_signals)}")
    
    success_count = sum(1 for s in pushed_signals if s['status'] == 'SENT')
    logger.info(f"   成功: {success_count}")
    logger.info("=" * 60)
    
    # 保存已推送記錄 (去重用)
    if not dry_run and pushed_signals:
        from datetime import datetime, timedelta
        import json
        
        pushed_file = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/signals/pushed_signals.json'
        
        try:
            with open(pushed_file, 'r') as f:
                already_pushed = json.load(f)
        except:
            already_pushed = []
        
        # 添加新推送記錄
        now = datetime.now()
        for sig in signals_to_push:
            already_pushed.append({
                'key': f"{sig.get('symbol')}_{sig.get('signal_type')}",
                'symbol': sig.get('symbol'),
                'signal_type': sig.get('signal_type'),
                'time': now.isoformat()
            })
        
        # 清理超過 24 小時的記錄
        cutoff = (now - timedelta(hours=24)).isoformat()
        already_pushed = [p for p in already_pushed if p.get('time', '') > cutoff]
        
        with open(pushed_file, 'w') as f:
            json.dump(already_pushed, f)
        
        logger.info(f"   💾 已保存推送記錄 (去重用)")
    
    return pushed_signals


def main():
    parser = argparse.ArgumentParser(description='Successor Signal Push Script')
    parser.add_argument('--dry-run', action='store_true', help='模擬運行，不實際推送')
    parser.add_argument('--force', action='store_true', help='強制執行，忽略交易時段檢查')
    args = parser.parse_args()
    
    # 檢查是否在交易時段 (自動判斷冬令時/夏令時)
    if HAS_MARKET_HOURS and not args.force:
        dst_status = "夏令時" if is_dst_us() else "冬令時"
        logger.info(f"📅 當前模式: {dst_status}")
        
        if not should_update_kline():
            logger.info("⏸️ 非交易時段，跳過推送")
            return
        logger.info("✅ 交易時段，開始推送...")
    
    push_signals(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
