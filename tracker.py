"""
存储芯片行业跟踪器
Memory Chip Industry Tracker

每日盘前自动抓取核心指标,生成HTML报告并发送邮件
支持两种模式: daily (每日早报) 或 weekly (周末深度报告)
"""

import os
import sys
import json
import smtplib
import argparse
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import re

import yfinance as yf
import feedparser
import pandas as pd


# ============================================================
# 配置区
# ============================================================

# 跟踪的股票清单
TICKERS = {
    # ── 存储芯片 ──────────────────────────────────────────
    "MU": {"name": "美光 Micron", "category": "存储原厂", "sector": "memory"},
    "005930.KS": {"name": "三星电子 Samsung", "category": "存储原厂", "sector": "memory"},
    "000660.KS": {"name": "SK海力士 SK Hynix", "category": "存储原厂", "sector": "memory"},
    "TSM": {"name": "台积电 TSMC", "category": "代工/封装", "sector": "memory"},
    "ASML": {"name": "阿斯麦 ASML", "category": "半导体设备", "sector": "memory"},
    "AMAT": {"name": "应用材料 Applied Materials", "category": "半导体设备", "sector": "memory"},
    "NVDA": {"name": "英伟达 NVIDIA", "category": "客户端(GPU)", "sector": "memory"},
    "AMD":  {"name": "AMD", "category": "客户端(GPU)", "sector": "memory"},
    "SOXX": {"name": "半导体ETF iShares", "category": "行业指数", "sector": "memory"},
    "SMH":  {"name": "VanEck半导体ETF", "category": "行业指数", "sector": "memory"},

    # ── 商业航天 ──────────────────────────────────────────
    "RKLB": {"name": "火箭实验室 Rocket Lab", "category": "商业航天", "sector": "aerospace"},
    "ASTS": {"name": "AST SpaceMobile", "category": "商业航天", "sector": "aerospace"},
    "LUNR": {"name": "Intuitive Machines", "category": "商业航天", "sector": "aerospace"},
    "PL":   {"name": "Planet Labs", "category": "商业航天", "sector": "aerospace"},
    "UFO":  {"name": "太空ETF Procure", "category": "商业航天ETF", "sector": "aerospace"},

    # ── 电力电网 ──────────────────────────────────────────
    "GEV":  {"name": "GE Vernova", "category": "电力电网", "sector": "grid"},
    "PWR":  {"name": "Quanta Services", "category": "电力电网", "sector": "grid"},
    "AMSC": {"name": "美国超导 AMSC", "category": "电力电网", "sector": "grid"},
    "NEE":  {"name": "NextEra Energy", "category": "电力电网", "sector": "grid"},
    "GRID": {"name": "智能电网ETF First Trust", "category": "电力电网ETF", "sector": "grid"},
}

# 新闻关键词 (用于过滤Google News RSS)
NEWS_KEYWORDS = [
    # 存储芯片
    "HBM memory",
    "Micron earnings",
    "SK Hynix HBM",
    "Samsung HBM4",
    "DRAM price",
    "NAND flash price",
    # 商业航天
    "Rocket Lab launch",
    "commercial space launch",
    "SpaceX Starship",
    "satellite constellation",
    # 电力电网
    "power grid investment",
    "GE Vernova electricity",
    "US grid infrastructure",
    "electricity demand AI",
]

# 邮件配置 (从环境变量读取,GitHub Secrets管理)
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


# ============================================================
# 数据抓取模块
# ============================================================

def fetch_stock_data(ticker: str, period: str = "5d") -> dict:
    """抓取单支股票的关键数据"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)

        if hist.empty or len(hist) < 2:
            return {"error": f"无数据 {ticker}"}

        latest = hist.iloc[-1]
        prev = hist.iloc[-2]

        # 计算涨跌幅
        change_pct = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100

        # 计算5日涨跌幅
        if len(hist) >= 5:
            week_change_pct = ((latest["Close"] - hist.iloc[0]["Close"]) / hist.iloc[0]["Close"]) * 100
        else:
            week_change_pct = change_pct

        # 获取基础信息 (PE等)
        try:
            info = stock.info
            pe_ratio = info.get("forwardPE") or info.get("trailingPE")
            market_cap = info.get("marketCap")
            currency = info.get("currency", "USD")
        except Exception:
            pe_ratio = None
            market_cap = None
            currency = "USD"

        return {
            "ticker": ticker,
            "close": float(latest["Close"]),
            "change_pct": float(change_pct),
            "week_change_pct": float(week_change_pct),
            "volume": int(latest["Volume"]) if not pd.isna(latest["Volume"]) else 0,
            "pe_ratio": pe_ratio,
            "market_cap": market_cap,
            "currency": currency,
            "high_52w": float(hist["High"].max()),
            "low_52w": float(hist["Low"].min()),
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


def fetch_all_stocks() -> dict:
    """批量抓取所有股票数据"""
    results = {}
    for ticker, meta in TICKERS.items():
        print(f"  → 抓取 {ticker} ({meta['name']})")
        data = fetch_stock_data(ticker, period="1mo")
        data.update(meta)
        results[ticker] = data
    return results


def fetch_news() -> list:
    """从Google News RSS抓取相关新闻"""
    all_news = []
    seen_titles = set()

    for keyword in NEWS_KEYWORDS:
        try:
            # Google News RSS URL
            url = f"https://news.google.com/rss/search?q={keyword.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)

            for entry in feed.entries[:3]:  # 每个关键词取前3条
                title = entry.get("title", "").strip()
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    all_news.append({
                        "title": title,
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "source": entry.get("source", {}).get("title", "") if isinstance(entry.get("source"), dict) else "",
                        "keyword": keyword,
                    })
        except Exception as e:
            print(f"    新闻抓取失败 ({keyword}): {e}")

    # 按时间排序,取最新的15条
    return all_news[:15]


# ============================================================
# AI 分析模块
# ============================================================

def generate_ai_analysis(stock_data: dict, news: list, alerts: list, mode: str = "daily") -> dict:
    """调用 DeepSeek API 生成智能分析。无 API key 时返回空字典。"""
    if not DEEPSEEK_API_KEY:
        return {}

    try:
        from openai import OpenAI
    except ImportError:
        print("⚠️ openai 包未安装，跳过 AI 分析")
        return {}

    stock_lines = []
    for ticker, data in stock_data.items():
        if "error" in data:
            continue
        stock_lines.append(
            f"  {data['name']} ({ticker}): 日涨幅 {data['change_pct']:+.1f}%，"
            f"月涨幅 {data['week_change_pct']:+.1f}%"
        )

    news_lines = [f"  - {item['title']}" for item in news[:10]]
    alert_lines = [f"  - {a['text']}" for a in alerts]

    if mode == "weekly":
        prompt = f"""你是一位同时追踪【存储芯片】【商业航天】【电力电网】三大板块的投资分析师。

本周行情数据:
{chr(10).join(stock_lines)}

近期重要新闻:
{chr(10).join(news_lines)}

异动警报:
{chr(10).join(alert_lines)}

请提供以下两部分内容，严格按照格式输出:

【本周观点】
（3-4句话）分板块概括本周核心逻辑，点出三个板块中最重要的一个信号，说明下周需要验证什么。

【动态思考清单】
（5个问题）基于本周具体数据和新闻提问，覆盖三个板块，每个问题必须引用具体数据或事件，不要写通用问题。
1. ...
2. ...
3. ...
4. ...
5. ..."""
    else:
        prompt = f"""你是一位同时追踪【存储芯片】【商业航天】【电力电网】三大板块的投资分析师。

今日行情数据:
{chr(10).join(stock_lines)}

今日相关新闻:
{chr(10).join(news_lines)}

异动警报:
{chr(10).join(alert_lines)}

请用3-4句简洁的中文写出今日观点，覆盖三个板块:
1. 今天各板块最重要的市场动态（结合数据和新闻）
2. 值得特别注意的一个跨板块信号或异常
3. 明日/本周继续关注的一件事

直接输出观点，不要加标题。"""

    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        message = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ DeepSeek API 调用失败: {e}")
        return {}

    if mode == "weekly":
        result = {"insights": "", "checklist": []}
        if "【本周观点】" in text and "【动态思考清单】" in text:
            parts = text.split("【动态思考清单】")
            result["insights"] = parts[0].replace("【本周观点】", "").strip()
            questions = re.findall(r"\d+[.、]\s*(.+)", parts[1])
            result["checklist"] = [q.strip() for q in questions[:5]]
        else:
            result["insights"] = text
        return result
    else:
        return {"insights": text}


def generate_dynamic_checklist(stock_data: dict, news: list) -> list:
    """基于本周实际数据生成动态思考清单（不依赖 AI）。"""
    questions = []

    # 找出周涨跌幅最大的股票
    valid = [(t, d) for t, d in stock_data.items() if "error" not in d]
    if valid:
        top = max(valid, key=lambda x: abs(x[1].get("week_change_pct", 0)))
        name, change = top[1]["name"], top[1].get("week_change_pct", 0)
        direction = "大涨" if change > 0 else "大跌"
        questions.append(
            f"{name} 本周{direction} {change:+.1f}%，背后是基本面变化还是情绪驱动？"
        )

    # 存储原厂 vs 设备股的分化
    mem = [d.get("week_change_pct", 0) for _, d in valid if "存储原厂" in d.get("category", "")]
    equip = [d.get("week_change_pct", 0) for _, d in valid if "设备" in d.get("category", "")]
    if mem and equip:
        diff = (sum(mem) / len(mem)) - (sum(equip) / len(equip))
        if abs(diff) > 3:
            who = "存储原厂" if diff > 0 else "设备股"
            questions.append(
                f"{who}本周跑赢对方 {abs(diff):.1f}%，这一分化是否预示周期位置变化？"
            )

    # 新闻主题检测
    news_text = " ".join(item.get("title", "") for item in news[:10]).lower()
    if "hbm4" in news_text or "hbm" in news_text:
        questions.append("本周 HBM 相关新闻增多，SK海力士/三星的 HBM4 进展是否改变了客户端竞争格局？")
    if "dram price" in news_text or "dram contract" in news_text:
        questions.append("DRAM 合约价走势如何？涨价趋势是延续还是出现放缓？")
    if "capex" in news_text or "capital expenditure" in news_text:
        questions.append("云厂商 capex 指引有何变化？AI 算力需求是否足够支撑 HBM 长期增长预期？")

    # 兜底问题
    defaults = [
        "美光最新库存天数走势？去化进程是加速还是趋稳？",
        "DRAM 现货价与合约价价差是否收窄？意味着什么？",
        "是否出现'算法效率突破'或'CXL 替代 HBM'的技术新闻？",
    ]
    for q in defaults:
        if len(questions) >= 5:
            break
        questions.append(q)

    return questions[:5]


# ============================================================
# 分析模块 - 生成警报和洞察
# ============================================================

def generate_alerts(stock_data: dict) -> list:
    """根据股票数据生成警报"""
    alerts = []

    for ticker, data in stock_data.items():
        if "error" in data:
            continue

        name = data.get("name", ticker)
        change = data.get("change_pct", 0)
        week_change = data.get("week_change_pct", 0)

        # 单日大涨大跌
        if abs(change) >= 5:
            emoji = "🚀" if change > 0 else "⚠️"
            direction = "暴涨" if change > 0 else "暴跌"
            alerts.append({
                "level": "high" if abs(change) >= 8 else "medium",
                "emoji": emoji,
                "text": f"{name} 单日{direction} {change:+.1f}%",
            })

        # 周线大变动
        if abs(week_change) >= 15:
            emoji = "📈" if week_change > 0 else "📉"
            alerts.append({
                "level": "medium",
                "emoji": emoji,
                "text": f"{name} 周线 {week_change:+.1f}%",
            })

    if not alerts:
        alerts.append({
            "level": "info",
            "emoji": "✅",
            "text": "今日各标的无异常波动",
        })

    return alerts


def calculate_summary(stock_data: dict) -> dict:
    """计算各板块汇总均值"""
    groups: dict[str, list] = {"memory": [], "aerospace": [], "grid": []}
    for data in stock_data.values():
        if "error" in data:
            continue
        sector = data.get("sector", "")
        if sector in groups:
            groups[sector].append(data.get("change_pct", 0))

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    return {
        "memory_avg":   avg(groups["memory"]),
        "aerospace_avg": avg(groups["aerospace"]),
        "grid_avg":     avg(groups["grid"]),
    }


# ============================================================
# HTML报告生成
# ============================================================

def format_market_cap(cap):
    """格式化市值"""
    if not cap:
        return "—"
    if cap >= 1e12:
        return f"${cap/1e12:.2f}T"
    elif cap >= 1e9:
        return f"${cap/1e9:.1f}B"
    else:
        return f"${cap/1e6:.0f}M"


def format_price(price, currency):
    """根据货币格式化价格"""
    if currency == "KRW":
        return f"₩{price:,.0f}"
    elif currency == "USD":
        return f"${price:,.2f}"
    elif currency == "TWD":
        return f"NT${price:,.2f}"
    elif currency == "EUR":
        return f"€{price:,.2f}"
    else:
        return f"{price:,.2f} {currency}"


def color_for_change(change):
    """根据涨跌幅返回颜色"""
    if change > 2:
        return "#16a34a"  # 深绿
    elif change > 0:
        return "#65a30d"  # 浅绿
    elif change < -2:
        return "#dc2626"  # 深红
    elif change < 0:
        return "#ea580c"  # 浅红
    return "#6b7280"  # 灰


def build_html_report(stock_data: dict, news: list, alerts: list, summary: dict, mode: str = "daily", ai_analysis: dict = None) -> str:
    """构建HTML邮件内容"""
    now = datetime.now(timezone(timedelta(hours=10)))  # 布里斯班时区
    date_str = now.strftime("%Y年%m月%d日 %A")
    time_str = now.strftime("%H:%M AEST")

    # 按类别分组
    by_category = {}
    for ticker, data in stock_data.items():
        if "error" in data:
            continue
        cat = data.get("category", "其他")
        by_category.setdefault(cat, []).append(data)

    report_title = "📊 行业追踪周报" if mode == "weekly" else "📊 行业追踪日报"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f9fafb;
    margin: 0;
    padding: 20px 0;
    color: #1f2937;
    line-height: 1.6;
  }}
  .container {{
    max-width: 680px;
    margin: 0 auto;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #e5e7eb;
  }}
  .header {{
    background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%);
    color: white;
    padding: 24px 28px;
  }}
  .header h1 {{
    margin: 0 0 6px 0;
    font-size: 22px;
    font-weight: 600;
  }}
  .header .subtitle {{
    opacity: 0.85;
    font-size: 13px;
  }}
  .section {{
    padding: 20px 28px;
    border-bottom: 1px solid #f3f4f6;
  }}
  .section-title {{
    font-size: 13px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 0 0 14px 0;
  }}
  .summary-grid {{
    display: table;
    width: 100%;
    border-spacing: 8px;
    margin: 0 -8px;
  }}
  .summary-card {{
    display: table-cell;
    background: #f9fafb;
    border-radius: 8px;
    padding: 14px 16px;
    text-align: left;
    width: 50%;
  }}
  .summary-card .label {{
    font-size: 12px;
    color: #6b7280;
    margin-bottom: 4px;
  }}
  .summary-card .value {{
    font-size: 20px;
    font-weight: 600;
  }}
  .alert {{
    padding: 12px 14px;
    margin-bottom: 8px;
    border-radius: 8px;
    border-left: 3px solid;
    font-size: 14px;
  }}
  .alert-high {{ background: #fef2f2; border-color: #dc2626; }}
  .alert-medium {{ background: #fffbeb; border-color: #f59e0b; }}
  .alert-info {{ background: #f0fdf4; border-color: #16a34a; }}
  .stock-group {{
    margin-bottom: 18px;
  }}
  .stock-group-title {{
    font-size: 13px;
    font-weight: 600;
    color: #374151;
    margin: 0 0 10px 0;
    padding: 6px 10px;
    background: #f3f4f6;
    border-radius: 6px;
    display: inline-block;
  }}
  .stock-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }}
  .stock-table th {{
    text-align: left;
    color: #6b7280;
    font-weight: 500;
    font-size: 12px;
    padding: 8px 6px;
    border-bottom: 1px solid #e5e7eb;
  }}
  .stock-table td {{
    padding: 10px 6px;
    border-bottom: 1px solid #f3f4f6;
  }}
  .stock-name {{
    font-weight: 500;
  }}
  .ticker-code {{
    color: #9ca3af;
    font-size: 12px;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }}
  .change-badge {{
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    font-weight: 500;
    font-size: 13px;
  }}
  .news-item {{
    padding: 10px 0;
    border-bottom: 1px solid #f3f4f6;
  }}
  .news-item:last-child {{
    border-bottom: none;
  }}
  .news-title {{
    color: #1f2937;
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    display: block;
    margin-bottom: 4px;
  }}
  .news-title:hover {{
    color: #1e40af;
  }}
  .news-meta {{
    font-size: 12px;
    color: #9ca3af;
  }}
  .footer {{
    padding: 20px 28px;
    background: #f9fafb;
    font-size: 12px;
    color: #6b7280;
    text-align: center;
  }}
  .footer a {{
    color: #6b7280;
    text-decoration: underline;
  }}
  .chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0;
  }}
  .chip {{
    background: #eff6ff;
    color: #1e40af;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
  }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <h1>{report_title}</h1>
    <div class="subtitle">{date_str} · {time_str}</div>
  </div>

  <!-- 摘要 -->
  <div class="section">
    <div class="section-title">⚡ 今日摘要</div>
    <div style="display: flex; gap: 8px;">
      <div class="summary-card" style="flex: 1;">
        <div class="label">💾 存储芯片</div>
        <div class="value" style="color: {color_for_change(summary['memory_avg'])}">{summary['memory_avg']:+.2f}%</div>
      </div>
      <div class="summary-card" style="flex: 1;">
        <div class="label">🚀 商业航天</div>
        <div class="value" style="color: {color_for_change(summary['aerospace_avg'])}">{summary['aerospace_avg']:+.2f}%</div>
      </div>
      <div class="summary-card" style="flex: 1;">
        <div class="label">⚡ 电力电网</div>
        <div class="value" style="color: {color_for_change(summary['grid_avg'])}">{summary['grid_avg']:+.2f}%</div>
      </div>
    </div>
  </div>

  <!-- 警报 -->
  <div class="section">
    <div class="section-title">🚨 关键警报</div>
"""

    for alert in alerts:
        html += f"""    <div class="alert alert-{alert['level']}">
      <span style="margin-right: 6px;">{alert['emoji']}</span>{alert['text']}
    </div>
"""

    html += """  </div>
"""

    # AI 观点区块（有 API key 时才显示）
    if ai_analysis and ai_analysis.get("insights"):
        insights_html = ai_analysis["insights"].replace("\n\n", "</p><p>").replace("\n", "<br>")
        html += f"""
  <!-- AI 今日观点 -->
  <div class="section">
    <div class="section-title">🤖 AI 观点</div>
    <div style="background: #f0f4ff; border-left: 3px solid #4f46e5; padding: 14px 16px; border-radius: 6px; font-size: 14px; line-height: 1.8; color: #1e1b4b;">
      <p style="margin: 0;">{insights_html}</p>
    </div>
    <div style="font-size: 11px; color: #9ca3af; margin-top: 8px;">由 DeepSeek AI 生成，仅供参考，不构成投资建议</div>
  </div>
"""

    html += """
  <!-- 股票详情 -->
  <div class="section">
    <div class="section-title">💹 持仓股票详情</div>
"""

    # 按类别输出
    category_order = [
        # 存储芯片
        "存储原厂", "客户端(GPU)", "半导体设备", "代工/封装", "行业指数",
        # 商业航天
        "商业航天", "商业航天ETF",
        # 电力电网
        "电力电网", "电力电网ETF",
    ]
    for cat in category_order:
        if cat not in by_category:
            continue
        stocks = by_category[cat]

        html += f"""    <div class="stock-group">
      <div class="stock-group-title">{cat}</div>
      <table class="stock-table">
        <tr>
          <th>名称</th>
          <th style="text-align: right;">价格</th>
          <th style="text-align: right;">日涨幅</th>
          <th style="text-align: right;">月涨幅</th>
          <th style="text-align: right;">PE</th>
        </tr>
"""
        for stock in stocks:
            change_color = color_for_change(stock["change_pct"])
            week_color = color_for_change(stock["week_change_pct"])
            pe_text = f"{stock['pe_ratio']:.1f}" if stock.get('pe_ratio') else "—"

            html += f"""        <tr>
          <td>
            <div class="stock-name">{stock['name']}</div>
            <div class="ticker-code">{stock['ticker']}</div>
          </td>
          <td style="text-align: right;">{format_price(stock['close'], stock['currency'])}</td>
          <td style="text-align: right;"><span class="change-badge" style="background: {change_color}1a; color: {change_color};">{stock['change_pct']:+.2f}%</span></td>
          <td style="text-align: right;"><span style="color: {week_color}">{stock['week_change_pct']:+.2f}%</span></td>
          <td style="text-align: right; color: #6b7280; font-size: 13px;">{pe_text}</td>
        </tr>
"""
        html += """      </table>
    </div>
"""

    # 新闻摘要
    html += """  </div>

  <!-- 新闻 -->
  <div class="section">
    <div class="section-title">📰 行业新闻 (过去24小时)</div>
"""

    if news:
        for item in news[:10]:
            source = item.get("source", "")
            published = item.get("published", "")[:16] if item.get("published") else ""
            html += f"""    <div class="news-item">
      <a href="{item['link']}" class="news-title" target="_blank">{item['title']}</a>
      <div class="news-meta">{source} · {published}</div>
    </div>
"""
    else:
        html += """    <div style="color: #9ca3af; font-size: 13px;">暂无新闻</div>
"""

    # 周末深度报告:增加思考清单（优先用 AI 生成，否则用动态规则生成）
    if mode == "weekly":
        if ai_analysis and ai_analysis.get("checklist"):
            checklist = ai_analysis["checklist"]
            checklist_note = "由 DeepSeek AI 根据本周数据生成"
        else:
            checklist = generate_dynamic_checklist(stock_data, news)
            checklist_note = "根据本周数据动态生成"

        items_html = "".join(f"<li>{q}</li>" for q in checklist)
        html += f"""  </div>

  <!-- 周末:思考清单 -->
  <div class="section">
    <div class="section-title">🤔 本周思考清单</div>
    <div style="background: #fefce8; border-left: 3px solid #ca8a04; padding: 12px 16px; border-radius: 6px; font-size: 14px; line-height: 1.7;">
      <p style="margin: 0 0 8px 0;"><strong>问自己这5个问题:</strong></p>
      <ol style="margin: 0; padding-left: 20px; color: #422006;">
        {items_html}
      </ol>
    </div>
    <div style="font-size: 11px; color: #9ca3af; margin-top: 8px;">{checklist_note}</div>
"""

    # Footer
    html += f"""  </div>

  <!-- Footer -->
  <div class="footer">
    <div>📡 数据源: Yahoo Finance · Google News</div>
    <div style="margin-top: 6px;">⚠️ 本报告仅供参考,不构成投资建议</div>
    <div style="margin-top: 6px;">生成时间: {now.strftime("%Y-%m-%d %H:%M:%S")} AEST</div>
  </div>

</div>
</body>
</html>
"""
    return html


# ============================================================
# 邮件发送
# ============================================================

def send_email(html_content: str, subject: str):
    """通过SMTP发送邮件"""
    if not all([EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO]):
        print("⚠️ 邮件配置不完整,跳过发送")
        print(f"   EMAIL_USER: {'已设置' if EMAIL_USER else '未设置'}")
        print(f"   EMAIL_PASSWORD: {'已设置' if EMAIL_PASSWORD else '未设置'}")
        print(f"   EMAIL_TO: {'已设置' if EMAIL_TO else '未设置'}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("存储芯片追踪器", EMAIL_USER))
    msg["To"] = EMAIL_TO

    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"✅ 邮件已发送至 {EMAIL_TO}")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False


# ============================================================
# 主函数
# ============================================================

def get_mock_data():
    """生成模拟数据(用于离线预览效果)"""
    import random
    random.seed(42)

    mock_data = {}
    base_prices = {
        # 存储芯片
        "MU": 225.71, "005930.KS": 98500, "000660.KS": 1949000,
        "TSM": 215, "ASML": 850, "AMAT": 195,
        "NVDA": 145, "AMD": 165, "SOXX": 280, "SMH": 320,
        # 商业航天
        "RKLB": 7.50, "ASTS": 25.30, "LUNR": 11.80, "PL": 3.60, "UFO": 24.50,
        # 电力电网
        "GEV": 345.00, "PWR": 310.50, "AMSC": 32.40, "NEE": 74.80, "GRID": 112.30,
    }
    for ticker, meta in TICKERS.items():
        base = base_prices.get(ticker, 100)
        change = random.uniform(-3, 8)
        week_change = random.uniform(-5, 15)
        mock_data[ticker] = {
            "ticker": ticker,
            "close": base * (1 + change/100),
            "change_pct": change,
            "week_change_pct": week_change,
            "volume": random.randint(1000000, 50000000),
            "pe_ratio": random.uniform(8, 35),
            "market_cap": random.uniform(50e9, 1.5e12),
            "currency": "KRW" if ".KS" in ticker else "USD",
            "high_52w": base * 1.2,
            "low_52w": base * 0.7,
            **meta,
        }
    return mock_data


def get_mock_news():
    """模拟新闻数据"""
    return [
        # 存储芯片
        {"title": "SK Hynix HBM4 mass production starts, NVIDIA secures full capacity", "link": "#", "published": "2026-05-11 06:00", "source": "Reuters", "keyword": "HBM"},
        {"title": "Micron raises FY2026 capex guidance to $20B amid AI memory boom", "link": "#", "published": "2026-05-10 22:30", "source": "WSJ", "keyword": "Micron"},
        {"title": "DRAM contract prices jump 58% in Q1, TrendForce reports", "link": "#", "published": "2026-05-10 18:45", "source": "TrendForce", "keyword": "DRAM price"},
        # 商业航天
        {"title": "Rocket Lab wins $50M Pentagon contract for Neutron rocket development", "link": "#", "published": "2026-05-11 04:30", "source": "SpaceNews", "keyword": "Rocket Lab"},
        {"title": "AST SpaceMobile completes BlueBird satellite deployment, targets 2026 revenue", "link": "#", "published": "2026-05-10 20:15", "source": "Bloomberg", "keyword": "satellite"},
        {"title": "SpaceX Starship completes 7th integrated flight test successfully", "link": "#", "published": "2026-05-10 16:00", "source": "Reuters", "keyword": "SpaceX"},
        # 电力电网
        {"title": "GE Vernova secures $3B grid equipment order from US utilities amid AI data center surge", "link": "#", "published": "2026-05-11 05:00", "source": "FT", "keyword": "GE Vernova"},
        {"title": "US power grid investment to hit record $200B in 2026, driven by AI demand", "link": "#", "published": "2026-05-10 23:00", "source": "WSJ", "keyword": "power grid"},
        {"title": "Quanta Services raises full-year guidance on record electric infrastructure backlog", "link": "#", "published": "2026-05-10 17:30", "source": "Bloomberg", "keyword": "grid infrastructure"},
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily",
                        help="报告模式: daily=每日早报, weekly=周末深度")
    parser.add_argument("--no-email", action="store_true",
                        help="只生成HTML文件,不发送邮件(用于本地测试)")
    parser.add_argument("--mock", action="store_true",
                        help="使用模拟数据(用于离线预览样式)")
    parser.add_argument("--output", default="report.html",
                        help="HTML输出路径")
    args = parser.parse_args()

    print(f"🚀 启动行业追踪器 · 存储芯片/商业航天/电力电网 ({args.mode}模式)")
    print(f"   时间: {datetime.now()}")

    # 1. 抓取股票数据
    print("\n📈 抓取股票数据...")
    if args.mock:
        print("   [使用模拟数据]")
        stock_data = get_mock_data()
    else:
        stock_data = fetch_all_stocks()

    # 2. 抓取新闻
    print("\n📰 抓取新闻...")
    if args.mock:
        news = get_mock_news()
    else:
        news = fetch_news()
    print(f"   获取到 {len(news)} 条新闻")

    # 3. 生成警报和摘要
    print("\n🔍 分析数据...")
    alerts = generate_alerts(stock_data)
    summary = calculate_summary(stock_data)

    # 4. AI 分析（有 ANTHROPIC_API_KEY 时才运行）
    ai_analysis = {}
    if DEEPSEEK_API_KEY:
        print("\n🤖 调用 DeepSeek AI 生成分析...")
        ai_analysis = generate_ai_analysis(stock_data, news, alerts, mode=args.mode)
    else:
        print("\n🤖 未设置 DEEPSEEK_API_KEY，跳过 AI 分析")

    # 5. 生成HTML报告
    print("\n📄 生成HTML报告...")
    html = build_html_report(stock_data, news, alerts, summary, mode=args.mode, ai_analysis=ai_analysis)

    # 保存HTML文件
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   报告已保存: {args.output}")

    # 6. 发送邮件
    if not args.no_email:
        date_tag = datetime.now().strftime("%m.%d")
        if args.mode == "weekly":
            subject = f"📊 行业周报（芯片/航天/电网）· {date_tag}"
        else:
            subject = f"📊 行业日报（芯片/航天/电网）· {date_tag}"
        send_email(html, subject)

    print("\n✨ 完成!")


if __name__ == "__main__":
    main()
