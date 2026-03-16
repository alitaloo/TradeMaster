# -*- coding: utf-8 -*-
"""
Daily News Digest - 每日新聞摘要系統

功能:
- 從 RSS 獲取科技、金融新聞（中英文來源）
- 翻譯國外新聞為中文
- 識別重點新聞
- 生成中文摘要
- 發送到 Telegram
- 去重檢查 (基於 link 欄位)
- 關鍵字過濾 (財經/科技關鍵字)
"""

import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

import feedparser
import requests
from datetime import datetime
from typing import List, Dict, Set
import re
import json
import os

# Telegram 配置
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '7506814516')


# 翻譯函數 (使用 LLM API)
def translate_to_chinese(text: str) -> str:
    """翻譯文本為中文（翻譯交由 cron agent 處理，此函數直接返回原文）"""
    return text  # cron agent（MiniMax）負責翻譯，腳本只負責抓取原文


class NewsFetcher:
    """新聞獲取器"""
    
    # 新聞來源配置 (中英文混合) - 5-8個來源
    RSS_FEEDS = {
        "tech": [
            # 中文來源
            "https://buzzorange.com/techorange/feed/",
            # 英文來源 (需要翻譯)
            "https://techcrunch.com/feed/",
            "https://www.theverge.com/rss/index.xml",
            "https://feeds.bbci.co.uk/news/technology/rss.xml",
            "https://www.wired.com/feed/rss"
        ],
        "finance": [
            # 中文來源
            "https://www.cnyes.com/rss/",
            # 英文來源 (需要翻譯)
            "https://feeds.bbci.co.uk/news/business/rss.xml",
            "https://feeds.bloomberg.com/markets/news.rss"
        ]
    }
    
    # 需要翻譯的來源
    ENGLISH_SOURCES = ["TechCrunch", "The Verge", "BBC", "Reuters", "Bloomberg"]
    
    # 關鍵詞權重
    IMPORTANCE_KEYWORDS = {
        "critical": [
            "breaking", "major", "crash", "bankrupt", "layoffs",
            "acquisition", "merger", "ipo", "lawsuit", "scandal"
        ],
        "important": [
            "launch", "announce", "revenue", "earnings", "quarterly",
            "AI", "artificial intelligence", "semiconductor", "chip",
            "nvidia", "openai", "microsoft", "apple", "google", "tesla"
        ]
    }
    
    # 過濾關鍵字 (財經/科技)
    FILTER_KEYWORDS = [
        # 科技關鍵字
        "AI", "artificial intelligence", "machine learning", "deep learning",
        "semiconductor", "chip", "GPU", "CPU", "Nvidia", "AMD", "Intel",
        "Apple", "Google", "Microsoft", "Meta", "Tesla", "OpenAI", "ChatGPT",
        "startup", "funding", " Series A", " Series B", "IPO", "acquisition",
        "cloud", "AWS", "Azure", "Google Cloud", "5G", "6G", "iPhone",
        "Android", "smartphone", "robot", "autonomous", "self-driving",
        # 金融關鍵字
        "stock", "market", "trading", "forex", "crypto", "bitcoin", "ETF",
        "Fed", "Federal Reserve", "interest rate", "inflation", "GDP",
        "revenue", "earnings", "quarterly", "profit", "loss", "dividend",
        "bond", "yield", "S&P", "NASDAQ", "Dow Jones", "Hang Seng", "TAIEX",
        "bank", "investment", "fund", "hedge fund", "portfolio"
    ]
    
    def __init__(self):
        self.seen_links: Set[str] = set()
        self._load_seen_links()
    
    def _load_seen_links(self):
        """從文件載入已讀取的連結"""
        try:
            cache_file = "/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/scripts/.news_cache.json"
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    self.seen_links = set(data.get('links', []))
        except Exception as e:
            print(f"[WARN] 無法載入快取: {e}")
    
    # .news_cache.json 上限 (避免無限增長)
    NEWS_CACHE_MAX_LINKS = 2000

    def _save_seen_links(self):
        """儲存已讀取的連結 (自動截斷至上限)"""
        try:
            cache_file = "/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/scripts/.news_cache.json"
            links = list(self.seen_links)
            # 超過上限時只保留最新的 N 條
            if len(links) > self.NEWS_CACHE_MAX_LINKS:
                links = links[-self.NEWS_CACHE_MAX_LINKS:]
                self.seen_links = set(links)
            data = {'links': links}
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"[WARN] 無法儲存快取: {e}")
    
    def _is_relevant(self, title: str, summary: str) -> bool:
        """檢查文章是否符合關鍵字過濾"""
        text = (title + " " + summary).lower()
        for keyword in self.FILTER_KEYWORDS:
            if keyword.lower() in text:
                return True
        return False
    
    def _deduplicate(self, articles: List[Dict]) -> List[Dict]:
        """基於 link 欄位去重"""
        unique_articles = []
        new_links = set()
        
        for article in articles:
            link = article.get('link', '')
            if link and link not in self.seen_links:
                unique_articles.append(article)
                new_links.add(link)
        
        # 更新已讀取的連結
        if new_links:
            self.seen_links.update(new_links)
            self._save_seen_links()
        
        return unique_articles
    
    def fetch_feed(self, url: str, limit: int = 10) -> List[Dict]:
        """獲取 RSS 內容"""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=10, verify=False)
            response.raise_for_status()
            
            feed = feedparser.parse(response.text)
            articles = []
            
            for entry in feed.entries[:limit]:
                title = entry.get("title", "").strip()
                summary = self._clean_summary(entry.get("summary", ""))
                
                # 關鍵字過濾
                if not self._is_relevant(title, summary):
                    continue
                
                articles.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "summary": summary,
                    "published": entry.get("published", ""),
                    "source": self._extract_source(url),
                    "is_english": self._is_english_source(url)
                })
            
            # 去重檢查 (基於 link 欄位)
            articles = self._deduplicate(articles)
            
            return articles
        except Exception as e:
            print(f"[ERROR] Failed to fetch {url}: {e}")
            return []
    
    def _is_english_source(self, url: str) -> bool:
        """判斷是否為英文來源"""
        english_domains = ["techcrunch", "theverge", "reuters", "bloomberg", "bbc"]
        return any(domain in url.lower() for domain in english_domains)
    
    def _clean_summary(self, summary: str) -> str:
        """清理摘要文本"""
        clean = re.sub(r'<[^>]+>', '', summary)
        clean = ' '.join(clean.split())
        return clean[:200] if len(clean) > 200 else clean
    
    def _extract_source(self, url: str) -> str:
        """提取來源名稱"""
        if "buzzorange" in url or "techorange" in url:
            return "科技報橘"
        elif "inside" in url:
            return "INSIDE"
        elif "bnext" in url:
            return "數位時代"
        elif "cnyes" in url:
            return "鉅亨網"
        elif "techcrunch" in url:
            return "TechCrunch"
        elif "theverge" in url:
            return "The Verge"
        elif "wired" in url:
            return "Wired"
        elif "reuters" in url:
            return "Reuters"
        elif "bloomberg" in url:
            return "Bloomberg"
        elif "bbc" in url:
            return "BBC"
        else:
            return "News"
    
    def fetch_all(self, category: str, limit: int = 10) -> List[Dict]:
        """獲取某類別所有新聞"""
        articles = []
        urls = self.RSS_FEEDS.get(category, [])
        
        for url in urls:
            articles.extend(self.fetch_feed(url, limit))
        
        articles = self._rank_articles(articles)
        return articles
    
    def _rank_articles(self, articles: List[Dict]) -> List[Dict]:
        """為文章評分"""
        for article in articles:
            score = 0
            text = (article["title"] + " " + article["summary"]).lower()
            
            for kw in self.IMPORTANCE_KEYWORDS["critical"]:
                if kw in text:
                    score += 10
            
            for kw in self.IMPORTANCE_KEYWORDS["important"]:
                if kw in text:
                    score += 3
            
            article["score"] = score
        
        return sorted(articles, key=lambda x: x.get("score", 0), reverse=True)


class NewsDigest:
    """新聞摘要生成器"""
    
    def __init__(self):
        self.fetcher = NewsFetcher()
    
    def _translate_if_needed(self, article: Dict) -> Dict:
        """必要時翻譯文章"""
        if article.get("is_english"):
            article["title_cn"] = translate_to_chinese(article["title"])
            article["summary_cn"] = translate_to_chinese(article["summary"])
        else:
            article["title_cn"] = article["title"]
            article["summary_cn"] = article["summary"]
        return article
    
    def generate_daily_digest(self, articles_per_category: int = 5) -> str:
        """生成每日中文摘要"""
        tech_news = self.fetcher.fetch_all("tech", articles_per_category)
        finance_news = self.fetcher.fetch_all("finance", articles_per_category)
        
        # 翻譯英文新聞
        for news in tech_news:
            self._translate_if_needed(news)
        for news in finance_news:
            self._translate_if_needed(news)
        
        date_str = datetime.now().strftime("%Y/%m/%d")
        
        digest = f"""📰 **今日重點摘要 - {date_str}**

"""
        
        # 科技頭條
        digest += "**🤖 科技頭條**\n\n"
        for i, news in enumerate(tech_news[:3], 1):
            title = news.get("title_cn", news["title"])
            summary = news.get("summary_cn", news["summary"])
            digest += f"{i}. {title}\n"
            if summary:
                digest += f"   {summary}\n"
            digest += f"   📰 {news['source']}\n\n"
        
        # 金融頭條
        digest += "**💹 金融頭條**\n\n"
        for i, news in enumerate(finance_news[:3], 1):
            title = news.get("title_cn", news["title"])
            summary = news.get("summary_cn", news["summary"])
            digest += f"{i}. {title}\n"
            if summary:
                digest += f"   {summary}\n"
            digest += f"   📰 {news['source']}\n\n"
        
        digest += f"""---
⏰ 生成時間: {datetime.now().strftime('%H:%M')} | #每日摘要
"""
        
        return digest
    
    def generate_brief_digest(self, articles_per_category: int = 3) -> str:
        """生成簡潔摘要 (手機閱讀)"""
        tech_news = self.fetcher.fetch_all("tech", articles_per_category)
        finance_news = self.fetcher.fetch_all("finance", articles_per_category)
        
        for news in tech_news:
            self._translate_if_needed(news)
        for news in finance_news:
            self._translate_if_needed(news)
        
        date_str = datetime.now().strftime("%m/%d")
        
        digest = f"""📰 **今日重點 - {date_str}**

**🤖 科技 ({len(tech_news)}條)**
"""
        
        for news in tech_news:
            title = news.get("title_cn", news["title"])[:50]
            digest += f"• {title}...\n"
        
        digest += f"""
**💹 金融 ({len(finance_news)}條)**
"""
        
        for news in finance_news:
            title = news.get("title_cn", news["title"])[:50]
            digest += f"• {title}...\n"
        
        digest += """
---
💡 回覆「科技」或「金融」獲取詳細摘要
"""
        
        return digest


def get_daily_digest() -> str:
    """獲取每日摘要"""
    digest = NewsDigest()
    return digest.generate_daily_digest()


def send_to_telegram(message: str, chat_id: str = None) -> bool:
    """發送訊息到 Telegram"""
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    
    try:
        # 使用 OpenClaw message 工具
        from tools import message
        result = message(
            action='send',
            target=chat_id,
            message=message
        )
        print(f"✅ Telegram 訊息已發送")
        return True
    except Exception as e:
        print(f"[ERROR] Telegram 發送失敗: {e}")
        # 備用方案: 直接用 API
        return _send_telegram_api(message, chat_id)


def _send_telegram_api(message: str, chat_id: str) -> bool:
    """使用 Telegram Bot API 發送"""
    if not TELEGRAM_BOT_TOKEN:
        print("[WARN] 沒有設定 TELEGRAM_BOT_TOKEN")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            print(f"✅ Telegram API 訊息已發送")
            return True
        else:
            print(f"[ERROR] Telegram API 錯誤: {response.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] Telegram API 失敗: {e}")
        return False


def run_hourly_digest():
    """定時執行新聞摘要 (每小時)"""
    print(f"⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M')}] 開始抓取新聞...")
    
    digest = NewsDigest()
    message = digest.generate_daily_digest()
    
    if message:
        send_to_telegram(message)
        print(f"✅ 新聞摘要已發送")
    else:
        print(f"⚠️ 無新新聞")


# 測試執行
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--hourly":
        # 定時模式 (每小時執行)
        run_hourly_digest()
    else:
        # 測試模式
        print("=" * 50)
        print("測試新聞摘要系統 (中英混合)")
        print("=" * 50)
        
        try:
            digest = get_daily_digest()
            print(digest)
            print("\n✅ 測試成功!")
            print("\n---")
            print("💡 使用 --hourly 參數執行定時模式:")
            print("   python3 news_digest.py --hourly")
        except Exception as e:
            print(f"\n❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
