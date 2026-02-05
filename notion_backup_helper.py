#!/usr/bin/env python3
"""
TradeMaster v2 - Notion 上傳小助手

功能：
1. 讀取所有技術文檔、回測報告、策略報告
2. 生成適合 Notion 匯入的合併 Markdown 文件
3. 可選擇直接打印內容（複製貼上）

使用方法：
    python3 notion_backup_helper.py --docs       # 技術文檔
    python3 notion_backup_helper.py --tests     # 回測報告
    python3 notion_backup_helper.py --strategy  # 策略報告
    python3 notion_backup_helper.py --all       # 全部
"""

import os
from pathlib import Path
from datetime import datetime

# 路徑配置
PROJECT_ROOT = Path(__file__).parent
DOCS_DIR = PROJECT_ROOT / "docs"
TESTS_DIR = PROJECT_ROOT / "tests"

# 文檔列表
DOCS_FILES = [
    "TECHNICAL_SPEC.md",
    "STRATEGY_RESEARCH.md",
    "SYSTEM_OPTIMIZATION.md",
    "SYSTEM_GAPS_ANALYSIS.md",
    "P0_FIXES_REPORT.md",
    "NEW_STRATEGIES_REPORT.md",
    "EXTENSION_GUIDE.md",
]

TESTS_FILES = [
    "FULL_BACKTEST_18STOCKS.md",
    "BACKTEST_REPORT_18STOCKS_7STRATEGIES.md",
    "FULL_BACKTEST_5COMBINATIONS.md",
    "FULL_COMBINATION_ANALYSIS_17STRATEGIES.md",
    "STRATEGY_COMBINATION_ANALYSIS.md",
    "STRATEGY_COMBINATION_REPORT.md",
    "WALK_FORWARD_ANALYSIS.md",
    "TEST_CASES.md",
    "TEST_REPORT.md",
    "FULL_BACKTEST_18STOCKS_2.md",
]

STRATEGY_FILES = [
    "strategy_complete_report.txt",
    "strategy_full_report.txt",
    "strategy_full_wf_report.txt",
    "strategy_analysis_report.txt",
    "strategy_report_20260205.txt",
    "strategy_walkforward_report.txt",
]


def read_file(filepath: Path) -> str:
    """讀取文件內容"""
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return None


def print_header(title: str, emoji: str = "="):
    """打印標題"""
    print(f"\n{emoji * 80}")
    print(f"  {title}")
    print(f"{emoji * 80}\n")


def print_section(title: str, content: str = ""):
    """打印章節"""
    print(f"\n{'=' * 80}")
    print(f"  📄 {title}")
    print(f"{'=' * 80}")
    if content:
        print(content)


def backup_docs():
    """備份技術文檔"""
    print_header("📘 技術文檔備份", "📘")
    
    for filename in DOCS_FILES:
        filepath = DOCS_DIR / filename
        content = read_file(filepath)
        
        if content:
            print_section(filename.replace('.md', ''), content)
        else:
            print(f"⚠️ 找不到: {filename}")
    
    print("\n" + "=" * 80)
    print("  📘 技術文檔備份完成")
    print("=" * 80)


def backup_tests():
    """備份回測報告"""
    print_header("📈 回測報告備份", "📈")
    
    for filename in TESTS_FILES:
        filepath = TESTS_DIR / filename
        content = read_file(filepath)
        
        if content:
            # 只打印前 100 行，避免太長
            lines = content.split('\n')
            if len(lines) > 100:
                print_section(filename.replace('.md', ''), '\n'.join(lines[:100]) + f"\n\n... (共 {len(lines)} 行)")
            else:
                print_section(filename.replace('.md', ''), content)
        else:
            print(f"⚠️ 找不到: {filename}")
    
    print("\n" + "=" * 80)
    print("  📈 回測報告備份完成")
    print("=" * 80)


def backup_strategy():
    """備份策略報告"""
    print_header("📋 策略報告備份", "📋")
    
    for filename in STRATEGY_FILES:
        filepath = PROJECT_ROOT / filename
        content = read_file(filepath)
        
        if content:
            print_section(filename.replace('.txt', ''), content)
        else:
            print(f"⚠️ 找不到: {filename}")
    
    print("\n" + "=" * 80)
    print("  📋 策略報告備份完成")
    print("=" * 80)


def backup_all():
    """備份全部"""
    print_header("🚀 完整備份", "🎯")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"位置: {PROJECT_ROOT}")
    
    backup_docs()
    backup_tests()
    backup_strategy()
    
    print("\n" + "=" * 80)
    print("  ✅ 完整備份完成！")
    print("=" * 80)
    print("\n📝 下一步：")
    print("   1. 打開 Notion")
    print("   2. 創建頁面：TradeMaster v2 技術文檔")
    print("   3. 複製上面的內容貼上")


def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="TradeMaster v2 - Notion 上傳小助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
    python3 notion_backup_helper.py --docs       # 技術文檔
    python3 notion_backup_helper.py --tests     # 回測報告
    python3 notion_backup_helper.py --strategy  # 策略報告
    python3 notion_backup_helper.py --all       # 全部（預設）
        """
    )
    
    parser.add_argument('--docs', action='store_true', help='只備份技術文檔')
    parser.add_argument('--tests', action='store_true', help='只備份回測報告')
    parser.add_argument('--strategy', action='store_true', help='只備份策略報告')
    parser.add_argument('--all', action='store_true', help='備份全部（預設）')
    
    args = parser.parse_args()
    
    # 預設備份全部
    if not any([args.docs, args.tests, args.strategy, args.all]):
        args.all = True
    
    if args.all:
        backup_all()
    elif args.docs:
        backup_docs()
    elif args.tests:
        backup_tests()
    elif args.strategy:
        backup_strategy()


if __name__ == "__main__":
    main()
