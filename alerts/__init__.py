# Alert system - Telegram notifications

import logging
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import os

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """警報"""
    title: str
    message: str
    priority: str = "medium"  # low, medium, high
    timestamp: datetime = None
    data: Dict = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.data is None:
            self.data = {}
    
    def to_telegram_markdown(self) -> str:
        """轉為 Telegram Markdown 格式"""
        emoji = {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢"
        }.get(self.priority, "⚪")
        
        return f"""
{emoji} *{self.title}*

{self.message}

📊 時間: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""


def _format_indicator(value, format_str=".1f"):
    """格式化指標值"""
    if isinstance(value, (int, float)):
        return f"{value:{format_str}}"
    return str(value)


class AlertManager:
    """警報管理器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.alerts: List[Alert] = []
        self.notifiers = []
        
        # 初始化通知器
        if self.config.get("telegram_token"):
            self.notifiers.append(TelegramNotifier(
                token=self.config["telegram_token"],
                chat_id=self.config.get("telegram_chat_id")
            ))
        
        if self.config.get("email_smtp"):
            self.notifiers.append(EmailNotifier(
                smtp_server=self.config["email_smtp"]["server"],
                smtp_port=self.config["email_smtp"]["port"],
                username=self.config["email_smtp"]["username"],
                password=self.config["email_smtp"]["password"],
                from_addr=self.config["email_smtp"]["from"]
            ))
    
    def send_trade_signal(self, signal) -> None:
        """發送交易信號"""
        # 格式化指標
        rsi = _format_indicator(signal.indicators.get('rsi') if hasattr(signal, 'indicators') else 'N/A')
        ma20 = _format_indicator(signal.indicators.get('ma20') if hasattr(signal, 'indicators') else 'N/A')
        ma50 = _format_indicator(signal.indicators.get('ma50') if hasattr(signal, 'indicators') else 'N/A')
        
        signal_type = signal.signal_type.value if hasattr(signal.signal_type, 'value') else getattr(signal, 'signal_type', 'N/A')
        
        alert = Alert(
            title=f"交易信號 - {signal.symbol}",
            message=f"""
📈 類型: {signal_type}
💰 價格: ${signal.price:.2f}
📊 信心度: {signal.confidence:.0%}
📋 原因: {signal.reason}

技術指標:
- RSI: {rsi}
- MA20: ${ma20}
- MA50: ${ma50}
""",
            priority="high",
            data=signal.to_dict() if hasattr(signal, 'to_dict') else {}
        )
        
        self._dispatch(alert)
    
    def send_position_update(
        self, 
        symbol: str, 
        action: str,
        details: Dict
    ) -> None:
        """發送持倉更新"""
        alert = Alert(
            title=f"持倉更新 - {symbol}",
            message=f"""
{action}
📊 類型: {details.get('type', 'N/A')}
💰 進場價: ${details.get('entry_price', 0):.2f}
📈 股數: {details.get('quantity', 0)}
🎯 止損: ${details.get('stop_loss', 0):.2f}
🏆 目標: ${details.get('take_profit', 0):.2f}
""",
            priority="medium",
            data=details
        )
        
        self._dispatch(alert)
    
    def send_daily_summary(self, summary: Dict) -> None:
        """發送每日總結"""
        top_signals = summary.get('top_signals', '無')
        if isinstance(top_signals, list):
            top_signals = '\n'.join([f"- {s}" for s in top_signals])
        
        alert = Alert(
            title="每日交易總結",
            message=f"""
📊 當日摘要:

💵 帳戶餘額: ${summary.get('portfolio_value', 0):,.2f}
📈 今日漲跌幅: {summary.get('daily_change_pct', 0):.2f}%

🔔 新信號: {summary.get('new_signals', 0)}
📊 持倉數量: {summary.get('open_positions', 0)}

📋 Top 信號:
{top_signals}
""",
            priority="low"
        )
        
        self._dispatch(alert)
    
    def send_risk_alert(self, rule_name: str, message: str) -> None:
        """發送風控警報"""
        alert = Alert(
            title=f"風控警報 - {rule_name}",
            message=message,
            priority="high"
        )
        
        self._dispatch(alert)
    
    def _dispatch(self, alert: Alert):
        """分發警報"""
        self.alerts.append(alert)
        
        for notifier in self.notifiers:
            try:
                notifier.send(alert)
            except Exception as e:
                logger.error(f"Failed to send alert via {notifier.__class__.__name__}: {e}")
        
        logger.info(f"Alert sent: {alert.title}")


class TelegramNotifier:
    """Telegram 通知器"""
    
    def __init__(self, token: str, chat_id: str = None):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send(self, alert: Alert) -> bool:
        """發送 Telegram 消息"""
        if not self.chat_id:
            logger.warning("Telegram chat_id not configured")
            return False
        
        url = f"{self.base_url}/sendMessage"
        
        data = {
            "chat_id": self.chat_id,
            "text": alert.to_telegram_markdown(),
            "parse_mode": "Markdown"
        }
        
        try:
            response = requests.post(url, json=data, timeout=10)
            
            if response.status_code == 200:
                logger.debug(f"Telegram message sent: {alert.title}")
                return True
            else:
                logger.error(f"Telegram send failed: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False
    
    def set_chat_id(self, chat_id: str):
        """設置 Chat ID"""
        self.chat_id = chat_id
    
    async def get_updates(self) -> List[Dict]:
        """獲取更新"""
        url = f"{self.base_url}/getUpdates"
        
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if data.get("ok"):
                return data.get("result", [])
            return []
            
        except Exception as e:
            logger.error(f"Failed to get Telegram updates: {e}")
            return []


class EmailNotifier:
    """郵件通知器"""
    
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_addr: str
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
    
    def send(self, alert: Alert) -> bool:
        """發送郵件"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.utils import formataddr
            
            msg = MIMEText(alert.message, 'plain', 'utf-8')
            msg['Subject'] = f"[TradeMaster] {alert.title}"
            msg['From'] = formataddr(('TradeMaster', self.from_addr))
            
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.debug(f"Email sent: {alert.title}")
            return True
            
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False


class LogNotifier:
    """日誌通知器（總是啟用）"""
    
    def send(self, alert: Alert):
        """記錄到日誌"""
        level = {
            "high": logging.ERROR,
            "medium": logging.WARNING,
            "low": logging.INFO
        }.get(alert.priority, logging.INFO)
        
        logger.log(level, f"[ALERT] {alert.title}: {alert.message}")
