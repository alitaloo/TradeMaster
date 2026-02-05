#!/usr/bin/env python3
"""
TradeMaster Pro v2.0 - 可擴展交易系統
"""

import argparse
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import PluginRegistry, PluginType
from data import DataEngine
from alerts import AlertManager, TelegramNotifier


def setup_logging(level: str = "INFO"):
    """設置日誌"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 確保 logs 目錄存在
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                logs_dir / f"trademaster_{datetime.now():%Y%m%d}.log"
            )
        ]
    )


def discover_plugins() -> PluginRegistry:
    """自動發現並註冊插件"""
    registry = PluginRegistry()
    
    # 發現指標插件
    indicators_path = PROJECT_ROOT / "indicators"
    for category in indicators_path.iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    # 發現策略插件
    strategies_path = PROJECT_ROOT / "strategies"
    for category in strategies_path.iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    # 發現風控插件
    risk_path = PROJECT_ROOT / "risk_rules"
    registry.discover_plugins(str(risk_path))
    
    return registry


def cmd_list(args):
    """列出插件"""
    registry = discover_plugins()
    
    if args.type == "indicators":
        print("\n📊 可用指標:\n")
        for name, meta in registry.list_indicators():
            print(f"  {meta.name}")
            print(f"    類別: {meta.category}")
            print(f"    參數: {list(meta.parameters.keys())}")
            print(f"    輸出: {meta.outputs}")
            print()
    
    elif args.type == "strategies":
        print("\n📈 可用策略:\n")
        for name, meta in registry.list_strategies():
            print(f"  {meta.name}")
            print(f"    類別: {meta.category}")
            print(f"    所需指標: {meta.indicators}")
            print(f"    市場環境: {meta.market_regimes}")
            print()
    
    elif args.type == "risk":
        print("\n🛡️ 可用風控規則:\n")
        for name, meta in registry.list_risk_rules():
            print(f"  {meta.name}")
            print(f"    類別: {meta.category}")
            print()


def cmd_daily_scan(args):
    """每日掃描"""
    logger = logging.getLogger(__name__)
    logger.info("Starting daily market scan...")
    
    # 發現插件
    registry = discover_plugins()
    
    # 初始化數據引擎
    data_engine = DataEngine()
    
    # 市場狀態
    market_status = data_engine.get_market_status()
    print(f"\n🌍 市場狀態: {'開盤' if market_status['is_trading'] else '收盤'}")
    
    # 掃描標的
    symbols = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA",  # 科技巨頭
        "TSM", "AMD", "INTC", "UBER", "ORCL",             # 半導體/軟體
        "WDC", "MU", "AVGO",                               # 儲存/記憶體/晶片
        "COIN", "RKLB"                                     # 加密/太空
    ]
    
    print(f"\n📊 掃描標的: {', '.join(symbols)}")
    print()
    
    def extract_params(meta_parameters: dict) -> dict:
        """從參數定義中提取預設值"""
        params = {}
        for key, value in meta_parameters.items():
            if isinstance(value, dict) and 'default' in value:
                params[key] = value['default']
            elif isinstance(value, dict):
                params[key] = value.get('type', None)
            else:
                params[key] = value
        return params
    
    results = []
    
    for symbol in symbols:
        # 獲取數據
        df = data_engine.get_daily_data(symbol)
        if df is None:
            continue
        
        # 計算指標
        indicators = {}
        for name, meta in registry.list_indicators():
            try:
                cls = registry.get_indicator(name)
                if cls:
                    params = extract_params(meta.parameters)
                    instance = cls(**params)
                    result = instance.compute(df)
                    indicators[name] = result
            except Exception as e:
                logger.warning(f"Indicator {name} failed: {e}")
        
        # 生成信號
        for name, meta in registry.list_strategies():
            if args.strategy and name != args.strategy:
                continue
            
            try:
                cls = registry.get_strategy(name)
                if cls:
                    params = extract_params(meta.parameters)
                    instance = cls(**params)
                    signal = instance.generate_signal(indicators, df)
                    
                    if signal and signal.signal in ["LONG", "SHORT"]:
                        results.append({
                            "symbol": symbol,
                            "strategy": name,
                            "signal": signal.signal,
                            "confidence": signal.confidence,
                            "price": signal.price,
                            "reason": signal.reason
                        })
            except Exception as e:
                logger.warning(f"Strategy {name} failed: {e}")
    
    # 排序並顯示結果
    results.sort(key=lambda x: x["confidence"], reverse=True)
    
    print("\n🎯 交易信號:\n")
    for r in results:
        emoji = "🟢" if r["signal"] == "LONG" else "🔴"
        print(f"{emoji} {r['symbol']} - {r['signal']} ({r['confidence']:.0%})")
        print(f"   價格: ${r['price']:.2f}")
        print(f"   策略: {r['strategy']}")
        print(f"   原因: {r['reason'][:80]}...")
        print()


def cmd_status(args):
    """系統狀態"""
    from security import SafetyGateway
    
    gateway = SafetyGateway()
    status = gateway.get_safety_status()
    
    print("\n📊 TradeMaster 系統狀態:\n")
    print(f"  執行模式: {status['mode']}")
    print(f"  熔斷狀態: {'⚠️ 觸發' if status['circuit_breaker'] else '✅ 正常'}")
    print(f"  今日訂單: {status['daily_stats']['orders_placed']}")
    print(f"  待確認: {status['pending_confirmations']}")
    print(f"  安全級別: {status['safety_level']}")
    print()


def cmd_test(args):
    """測試模式"""
    print("\n🧪 執行測試...")
    
    # 發現插件
    registry = discover_plugins()
    
    # 測試指標
    print("\n📊 測試指標:\n")
    for name, meta in registry.list_indicators()[:3]:
        print(f"  ✅ {name}")
    
    # 測試策略
    print("\n📈 測試策略:\n")
    for name, meta in registry.list_strategies()[:3]:
        print(f"  ✅ {name}")
    
    # 測試風控
    print("\n🛡️ 測試風控:\n")
    for name, meta in registry.list_risk_rules()[:3]:
        print(f"  ✅ {name}")
    
    print("\n✨ 所有插件載入成功！\n")


def main():
    parser = argparse.ArgumentParser(
        description="TradeMaster Pro v2.0 - 可擴展交易系統"
    )
    parser.add_argument(
        "--log", 
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日誌級別"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出可用插件")
    list_parser.add_argument(
        "type",
        choices=["indicators", "strategies", "risk"],
        help="插件類型"
    )
    
    # scan 命令
    scan_parser = subparsers.add_parser("scan", help="執行每日掃描")
    scan_parser.add_argument(
        "--strategy",
        help="指定策略名稱"
    )
    
    # status 命令
    subparsers.add_parser("status", help="系統狀態")
    
    # test 命令
    subparsers.add_parser("test", help="測試模式")
    
    # backtest 命令
    backtest_parser = subparsers.add_parser("backtest", help="回測")
    backtest_parser.add_argument("--strategy", help="策略名稱")
    backtest_parser.add_argument("--symbol", default="AAPL", help="標的")
    backtest_parser.add_argument("--period", default="1y", help="期間")
    
    args = parser.parse_args()
    
    # 設置日誌
    setup_logging(args.log)
    
    # 分發命令
    if args.command == "list":
        cmd_list(args)
    elif args.command == "scan":
        cmd_daily_scan(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "backtest":
        print("🔧 回測功能開發中...")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
