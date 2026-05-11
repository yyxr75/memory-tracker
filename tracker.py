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

import yfinance as yf
import feedparser
import pandas as pd


# ============================================================
# 配置区
# ============================================================

# 跟踪的股票清单
TICKERS = {
    # 存储三巨头
    "MU": {"name": "美光 Micron", "category": "存储原厂"},
    "005930.KS": {"name": "三星电子 Samsung", "category": "存储原厂"},
    "000660.KS": {"name": "SK海力士 SK Hynix", "category": "存储原厂"},

    # 上下游产业链
    "TSM": {"name": "台积电 TSMC", "category": "代工/封装"},
    "ASML": {"name": "阿斯麦 ASML", "category": "半导体设备"},
    "AMAT": {"name": "应用材料 Applied Materials", "category": "半导体设备"},
    "NVDA": {"name": "英伟达 NVIDIA", "category": "客户端(GPU)"},
    "AMD":  {"name": "AMD", "category": "客户端(GPU)"},

    # 指数 ETF
    "SOXX": {"name": "半导体ETF iShares", "category": "行业指数"},
    "SMH":  {"name": "VanEck半导体ETF", "category": "行业指数"},
}

# 新闻关键词 (用于过滤Google News RSS)
NEWS_KEYWORDS = [
    "HBM memory",
    "Micron earnings",
    "SK Hynix HBM",
    "Samsung HBM4",
    "DRAM price",
    "NAND flash price",
    "memory chip shortage",
]

# 邮件配置 (从环境变量读取,GitHub Secrets管理)
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))


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
    """计算汇总数据"""
    memory_makers = []  # 存储三巨头
    chain = []  # 产业链
    for ticker, data in stock_data.items():
        if "error" in data:
            continue
        category = data.get("category", "")
        if "存储原厂" in category:
            memory_makers.append(data.get("change_pct", 0))
        elif "设备" in category or "代工" in category:
            chain.append(data.get("change_pct", 0))

    return {
        "memory_avg": sum(memory_makers) / len(memory_makers) if memory_makers else 0,
        "chain_avg": sum(chain) / len(chain) if chain else 0,
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


def build_html_report(stock_data: dict, news: list, alerts: list, summary: dict, mode: str = "daily") -> str:
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

    report_title = "📊 存储芯片周报" if mode == "weekly" else "📊 存储芯片日报"

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
    <div class="summary-grid">
      <div class="summary-card">
        <div class="label">存储三巨头平均</div>
        <div class="value" style="color: {color_for_change(summary['memory_avg'])}">{summary['memory_avg']:+.2f}%</div>
      </div>
      <div class="summary-card">
        <div class="label">产业链(设备+代工)</div>
        <div class="value" style="color: {color_for_change(summary['chain_avg'])}">{summary['chain_avg']:+.2f}%</div>
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

  <!-- 股票详情 -->
  <div class="section">
    <div class="section-title">💹 持仓股票详情</div>
"""

    # 按类别输出
    category_order = ["存储原厂", "客户端(GPU)", "半导体设备", "代工/封装", "行业指数"]
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

    # 周末深度报告:增加思考清单
    if mode == "weekly":
        html += """  </div>

  <!-- 周末:思考清单 -->
  <div class="section">
    <div class="section-title">🤔 本周思考清单</div>
    <div style="background: #fefce8; border-left: 3px solid #ca8a04; padding: 12px 16px; border-radius: 6px; font-size: 14px; line-height: 1.7;">
      <p style="margin: 0 0 8px 0;"><strong>问自己这5个问题:</strong></p>
      <ol style="margin: 0; padding-left: 20px; color: #422006;">
        <li>本周 DRAM 现货价是否继续上涨? 涨幅环比扩大还是收窄?</li>
        <li>是否有任何超大规模云厂商(Microsoft/Google/Meta/Amazon)调整了 capex 指引?</li>
        <li>三星 HBM4 客户认证有没有最新进展?</li>
        <li>美光、SK海力士、三星最新的库存天数走势?</li>
        <li>有没有"算法效率突破"或"CXL 替代"的技术新闻?</li>
      </ol>
    </div>
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
        "MU": 225.71, "005930.KS": 98500, "000660.KS": 1949000,
        "TSM": 215, "ASML": 850, "AMAT": 195,
        "NVDA": 145, "AMD": 165, "SOXX": 280, "SMH": 320,
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
        {"title": "SK Hynix HBM4 mass production starts, NVIDIA secures full capacity", "link": "#", "published": "2026-05-11 06:00", "source": "Reuters", "keyword": "HBM"},
        {"title": "Samsung HBM3E finally passes NVIDIA qualification", "link": "#", "published": "2026-05-11 03:15", "source": "Bloomberg", "keyword": "Samsung HBM4"},
        {"title": "Micron raises FY2026 capex guidance to $20B amid AI memory boom", "link": "#", "published": "2026-05-10 22:30", "source": "WSJ", "keyword": "Micron"},
        {"title": "DRAM contract prices jump 58% in Q1, TrendForce reports", "link": "#", "published": "2026-05-10 18:45", "source": "TrendForce", "keyword": "DRAM price"},
        {"title": "OpenAI signs additional $80B memory supply deal with SK Hynix", "link": "#", "published": "2026-05-10 14:20", "source": "FT", "keyword": "memory"},
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

    print(f"🚀 启动存储芯片追踪器 ({args.mode}模式)")
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

    # 4. 生成HTML报告
    print("\n📄 生成HTML报告...")
    html = build_html_report(stock_data, news, alerts, summary, mode=args.mode)

    # 保存HTML文件
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   报告已保存: {args.output}")

    # 5. 发送邮件
    if not args.no_email:
        date_tag = datetime.now().strftime("%m.%d")
        if args.mode == "weekly":
            subject = f"📊 存储芯片周报 · {date_tag}"
        else:
            subject = f"📊 存储芯片日报 · {date_tag}"
        send_email(html, subject)

    print("\n✨ 完成!")


if __name__ == "__main__":
    main()
