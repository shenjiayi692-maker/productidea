#!/usr/bin/env python3
"""需求雷达：每日扫描英文社区讨论与热点，LLM 提炼可 vibecode 的痛点，邮件日报。

用法:
  python radar.py                # 完整流程（需 ANTHROPIC_API_KEY / RESEND_API_KEY）
  python radar.py --dry-run      # 不发邮件，日报打印到终端并存 reports/
  python radar.py --no-llm       # 只抓取+粗筛，检查信号源质量
  python radar.py --selftest     # 无网络离线自测（内置样例数据，跳过 LLM 和邮件）
"""

import argparse
import html
import json
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

ROOT = Path(__file__).parent
UA = {"User-Agent": "web:needs-radar:v0.1 (personal research aggregator)"}
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


# ---------------------------------------------------------------- 基础设施

def load_config():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["events"] = yaml.safe_load((ROOT / "events.yaml").read_text(encoding="utf-8"))["events"]
    return cfg


def db_connect():
    data_dir = Path(os.environ.get("RADAR_DATA_DIR", ROOT / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(data_dir / "seen.db")
    db.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, first_seen TEXT)")
    # v0.2：历次卡片留档，用于历史频率检查 + 日后 join 👍/👎 反馈做调优
    db.execute("""CREATE TABLE IF NOT EXISTS pains (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, item_id TEXT, pain TEXT, who TEXT, site_idea TEXT, window TEXT,
        keywords TEXT, buildable INT, monetize INT, gap INT, total INT,
        tool_count INT, url TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pains_date ON pains(date)")
    return db


def is_new(db, item_id):
    return db.execute("SELECT 1 FROM seen WHERE id=?", (item_id,)).fetchone() is None


def mark_seen(db, item_id):
    db.execute(
        "INSERT OR IGNORE INTO seen VALUES (?, ?)",
        (item_id, datetime.now(timezone.utc).isoformat()),
    )


def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=20, **kw)
    r.raise_for_status()
    return r


_reddit_token = None


def reddit_get(path, **kw):
    """Reddit 请求：有 REDDIT_CLIENT_ID/SECRET 时走 OAuth（www.reddit.com 匿名 JSON 已被封 403）。"""
    global _reddit_token
    cid, secret = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return get(f"https://www.reddit.com{path}", **kw)
    if _reddit_token is None:
        r = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(cid, secret),
            data={"grant_type": "client_credentials"},
            headers=UA,
            timeout=20,
        )
        r.raise_for_status()
        _reddit_token = r.json()["access_token"]
    headers = {**UA, "Authorization": f"Bearer {_reddit_token}"}
    r = requests.get(f"https://oauth.reddit.com{path}", headers=headers, timeout=20, **kw)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- 信号线 1+2：抓取

ATOM = {"a": "http://www.w3.org/2005/Atom"}


def _strip_html(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _sub_from_url(url):
    m = re.search(r"reddit\.com/r/([^/]+)/", url)
    return m.group(1) if m else "reddit"


def _fetch_rss(url, tries=4):
    """Reddit RSS 突发限流较严，429 时退避重试。"""
    for i in range(tries):
        try:
            return get(url).text
        except requests.HTTPError as e:
            if getattr(e.response, "status_code", None) == 429 and i < tries - 1:
                time.sleep(8 * (i + 1))
                continue
            raise


def _parse_reddit_rss(xml_text, line, vertical):
    out = []
    for e in ET.fromstring(xml_text).findall("a:entry", ATOM):
        link_el = e.find("a:link", ATOM)
        url = link_el.get("href") if link_el is not None else ""
        atom_id = e.findtext("a:id", "", ATOM)            # 形如 t3_1v3dvsd
        rid = atom_id.split("_")[-1] if atom_id else None
        if not rid:
            m = re.search(r"/comments/(\w+)/", url)
            rid = m.group(1) if m else url
        cat = e.find("a:category", ATOM)
        sub = ((cat.get("label", "") or cat.get("term", "")) if cat is not None else "").removeprefix("r/")
        pub = e.findtext("a:published", "", ATOM) or e.findtext("a:updated", "", ATOM)
        try:
            created = datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp() if pub else 0
        except ValueError:
            created = 0
        out.append({
            "id": f"reddit:{rid}", "source": "reddit", "line": line, "vertical": vertical,
            "title": (e.findtext("a:title", "", ATOM) or "").strip(),
            "text": _strip_html(e.findtext("a:content", "", ATOM))[:800],
            "url": url, "sub": sub or _sub_from_url(url),
            "ups": 0, "comments": 0, "created": created, "pre_ranked": True,
        })
    return out


def fetch_subreddits(cfg):
    """有 Reddit OAuth 凭据走 .json（带赞数），否则走免登录 .rss（top/day 本身即质量门槛）。"""
    out = []
    for vertical, subs in cfg["subreddits"].items():
        multi = "+".join(subs)
        try:
            if os.environ.get("REDDIT_CLIENT_ID"):
                j = reddit_get(f"/r/{multi}/top.json?t=day&limit=60&raw_json=1").json()
                out += [reddit_item(c["data"], "vertical", vertical)
                        for c in j.get("data", {}).get("children", [])]
            else:
                xml_text = _fetch_rss(f"https://www.reddit.com/r/{multi}/top.rss?t=day")
                out += _parse_reddit_rss(xml_text, "vertical", vertical)
        except Exception as e:
            print(f"[warn] subreddit {vertical}: {e}", file=sys.stderr)
        time.sleep(3)  # 尊重速率限制
    return out


def fetch_searches(cfg):
    """有 Reddit 凭据走站内 search.json；否则用搜索 API 查 site:reddit.com '句式'（无凭据也能跑）。"""
    if os.environ.get("REDDIT_CLIENT_ID"):
        out = []
        for q in cfg["search_queries"]:
            try:
                j = reddit_get(
                    "/search.json",
                    params={"q": q, "sort": "new", "t": "day", "limit": 25, "raw_json": 1},
                ).json()
                out += [reddit_item(c["data"], "search", f"搜索:{q}")
                        for c in j.get("data", {}).get("children", [])]
            except Exception as e:
                print(f"[warn] search {q}: {e}", file=sys.stderr)
            time.sleep(1)
        return out
    if not (os.environ.get("SERPER_API_KEY") or os.environ.get("SERPAPI_API_KEY")):
        print("[info] 无 Reddit 凭据且无搜索 key，跳过关键词搜索线", file=sys.stderr)
        return []
    out, seen_ids = [], set()
    for q in cfg["search_queries"]:
        try:
            hits = web_search(f"site:reddit.com {q}", tbs="qdr:w")
        except Exception as e:
            print(f"[warn] search {q}: {e}", file=sys.stderr)
            continue
        for h in hits:
            m = re.search(r"/comments/(\w+)/", h["url"])
            if not m or m.group(1) in seen_ids:
                continue
            seen_ids.add(m.group(1))
            out.append({
                "id": f"reddit:{m.group(1)}", "source": "reddit", "line": "search",
                "vertical": f"搜索:{q}", "title": h.get("title", ""),
                "text": (h.get("snippet") or "")[:800], "url": h["url"],
                "sub": _sub_from_url(h["url"]),
                "ups": 0, "comments": 0, "created": 0, "pre_ranked": True,
            })
        time.sleep(1)
    return out


def reddit_item(d, line, vertical):
    return {
        "id": f"reddit:{d['id']}",
        "source": "reddit",
        "line": line,
        "vertical": vertical,
        "title": d.get("title", ""),
        "text": (d.get("selftext") or "")[:800],
        "url": f"https://www.reddit.com{d.get('permalink', '')}",
        "sub": d.get("subreddit", ""),
        "ups": d.get("ups", 0),
        "comments": d.get("num_comments", 0),
        "created": d.get("created_utc", 0),
    }


def fetch_hackernews(cfg):
    out = []
    for t in cfg["hackernews_types"]:
        try:
            j = get(f"https://hn.algolia.com/api/v1/search?tags={t}&hitsPerPage=30").json()
        except Exception as e:
            print(f"[warn] hn {t}: {e}", file=sys.stderr)
            continue
        for h in j.get("hits", []):
            out.append({
                "id": f"hn:{h['objectID']}",
                "source": "hackernews",
                "line": "event",
                "vertical": f"HN:{t}",
                "title": h.get("title", ""),
                "text": "",
                "url": f"https://news.ycombinator.com/item?id={h['objectID']}",
                "sub": "hackernews",
                "ups": h.get("points", 0),
                "comments": h.get("num_comments", 0),
                "created": h.get("created_at_i", 0),
            })
    return out


def fetch_google_trends(cfg):
    out = []
    try:
        xml_text = get(f"https://trends.google.com/trending/rss?geo={cfg['google_trends_geo']}").text
        root = ET.fromstring(xml_text)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        for i, item in enumerate(root.iter("item")):
            title = item.findtext("title", "")
            traffic = item.findtext("ht:approx_traffic", "0", ns)
            news = item.find("ht:news_item", ns)
            news_title = news.findtext("ht:news_item_title", "", ns) if news is not None else ""
            news_url = news.findtext("ht:news_item_url", "", ns) if news is not None else ""
            out.append({
                "id": f"gtrends:{datetime.now(timezone.utc):%Y%m%d}:{title}",
                "source": "google-trends",
                "line": "event",
                "vertical": "即时热搜",
                "title": title,
                "text": f"关联新闻: {news_title} {news_url}",
                "url": f"https://www.google.com/search?q={requests.utils.quote(title)}",
                "sub": "google-trends",
                "ups": int(re.sub(r"[^\d]", "", str(traffic)) or 0),
                "comments": 0,
                "created": time.time(),
            })
    except Exception as e:
        print(f"[warn] google trends: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- 粗筛

def coarse_filter(items, cfg, db):
    f = cfg["filters"]
    cutoff = time.time() - f["max_age_hours"] * 3600
    kept = []
    for it in items:
        if it["created"] and it["created"] < cutoff:
            continue
        if not is_new(db, it["id"]):
            continue
        if it["source"] == "reddit" and not it.get("pre_ranked"):
            # pre_ranked = 来自 top/day RSS 或句式搜索命中，本身即质量门槛，无赞数可筛
            th_ups = f["search_min_ups"] if it["line"] == "search" else f["reddit_min_ups"]
            if it["ups"] < th_ups and it["comments"] < f["reddit_min_comments"]:
                continue
        elif it["source"] == "hackernews" and it["ups"] < f["hn_min_points"]:
            continue
        kept.append(it)
    # 搜索线优先（信噪比最高），再按互动量排
    kept.sort(key=lambda x: (x["line"] != "search", -(x["ups"] + 2 * x["comments"])))
    return kept[: cfg["llm"]["max_candidates"]]


# ---------------------------------------------------------------- LLM 两轮

EXTRACT_PROMPT = """你是需求挖掘分析师。下面是今天从 Reddit/HN/Google Trends 抓到的英文帖子。
逐条判断：是否包含「一个真实、具体、可以用一个小型网页工具解决」的痛点或机会。

对每条符合的，输出 JSON 对象：
{"idx": 原编号, "pain": "痛点一句话(中文)", "who": "谁在痛(中文)", "evidence": "原文关键句(英文原样引用)",
 "existing": "现有方案及其不足(中文)", "site_idea": "建议做什么网站(中文,一句话)", "window": "常青|事件性(注明窗口)",
 "queries": ["目标用户找这类工具时会搜的 2-3 个英文搜索词"]}

跳过：纯情绪宣泄、需要 App/硬件/牌照/线下服务、巨头产品已完美解决、政治新闻、名人八卦。
只输出 JSON 数组，无其他文字。没有符合的输出 []。

帖子列表:
{posts}"""

JUDGE_PROMPT = """你是独立开发者的投资顾问。以下是今天提炼出的痛点卡片(JSON)。
为每张卡打分(1-5)三个维度：
- buildable: 一个人用 AI 辅助编程 1-3 天能否上线网页版 MVP
- monetize: 变现路径清晰度(SEO流量+广告 / 直接付费 / 邮件订阅)
- gap: 竞争空白度(搜了会不会发现已有一堆同类)

部分卡片附有 market_scan——真实搜索引擎首页结果。有它时 gap 分必须以这些事实为准：
- no_tool_pages=true(首页全是论坛/文章,没有现成工具页) → gap 4-5
- tool_count 1-2 且无大站 → gap 3
- tool_count ≥3 或 big_players 有大站/官方工具占位 → gap 1-2
没有 market_scan 的卡片才按你的印象判断，并在 verdict 里注明「未核查」。

输出 JSON 数组，每项: {"idx": 卡片idx, "buildable": n, "monetize": n, "gap": n, "verdict": "一句话点评(中文,毒舌但中肯)"}
只输出 JSON，无其他文字。

卡片:
{cards}"""


def call_claude(cfg, prompt, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": cfg["llm"]["model"],
                    "max_tokens": 8192,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=180,
            )
            r.raise_for_status()
            # 模型可能先输出 thinking block，只取 text block 拼接
            text = "".join(
                b.get("text", "") for b in r.json()["content"] if b.get("type") == "text"
            )
            m = re.search(r"\[.*\]", text, re.DOTALL)
            return json.loads(m.group(0)) if m else []
        except Exception as e:
            if attempt == retries:
                raise
            print(f"[warn] call_claude 第{attempt + 1}次失败将重试: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def llm_extract(cfg, candidates):
    cards = []
    bs = cfg["llm"]["extract_batch_size"]
    for i in range(0, len(candidates), bs):
        batch = candidates[i : i + bs]
        posts = "\n".join(
            f"[{i + j}] ({it['source']}/r/{it['sub']}, {it['ups']}赞 {it['comments']}评) "
            f"{it['title']} || {it['text'][:400]}"
            for j, it in enumerate(batch)
        )
        try:
            for card in call_claude(cfg, EXTRACT_PROMPT.replace("{posts}", posts)):
                idx = card.get("idx")
                if isinstance(idx, int) and 0 <= idx - i < len(batch):
                    card["item"] = batch[idx - i]
                    cards.append(card)
        except Exception as e:
            print(f"[warn] extract batch {i}: {e}", file=sys.stderr)
    return cards


# ---------------------------------------------------------------- v0.2：竞品核查

TOOL_HINTS = ("calculator", "generator", "template", "checker", "converter",
              "tracker", "planner", "estimator", "builder", "tool", "free online")
CONTENT_DOMAINS = ("reddit.com", "quora.com", "youtube.com", "medium.com", "wikipedia.org",
                   "facebook.com", "twitter.com", "x.com", "tiktok.com", "news.ycombinator.com")
BIG_SITES = ("google.com", "microsoft.com", "apple.com", "adobe.com", "canva.com",
             "zillow.com", "nerdwallet.com", "bankrate.com", "smartasset.com", "turbotax.intuit.com")


def web_search(query, tbs=None):
    """搜索抽象：配了 SERPER_API_KEY 走 Serper.dev（送2500次），否则 SERPAPI_API_KEY 走 SerpAPI（免费100次/月）。
    tbs: 时间过滤（如 'qdr:w' 近一周）。返回 [{title, url, snippet}]。"""
    if os.environ.get("SERPER_API_KEY"):
        payload = {"q": query, "num": 10}
        if tbs:
            payload["tbs"] = tbs
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": os.environ["SERPER_API_KEY"],
                     "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
        return [{"title": w.get("title", ""), "url": w.get("link", ""), "snippet": w.get("snippet", "")}
                for w in r.json().get("organic", [])]
    params = {"engine": "google", "q": query, "num": 10, "api_key": os.environ["SERPAPI_API_KEY"]}
    if tbs:
        params["tbs"] = tbs
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
    r.raise_for_status()
    return [{"title": w.get("title", ""), "url": w.get("link", ""), "snippet": w.get("snippet", "")}
            for w in r.json().get("organic_results", [])]


def competitor_scan(cfg, cards):
    """对每张卡的 queries 查搜索首页，把竞争事实写进 card["scan"] 供评委轮打 gap 分。"""
    if not (os.environ.get("SERPER_API_KEY") or os.environ.get("SERPAPI_API_KEY")):
        print("[info] 未配 SERPER_API_KEY/SERPAPI_API_KEY，跳过竞品核查（gap 分退回 LLM 印象）", file=sys.stderr)
        return
    cc = cfg.get("competitor_check", {})
    per_card = cc.get("queries_per_card", 2)
    budget = cc.get("max_searches_per_day", 40)
    used = 0
    for c in cards:
        queries = [q for q in c.get("queries", []) if isinstance(q, str) and q.strip()][:per_card]
        if not queries or used >= budget:
            continue
        results, seen_urls = [], set()
        for q in queries:
            if used >= budget:
                break
            try:
                hits = web_search(q)
                used += 1
            except Exception as e:
                print(f"[warn] web search {q!r}: {e}", file=sys.stderr)
                continue
            finally:
                time.sleep(0.5)
            for h in hits:
                if h["url"] and h["url"] not in seen_urls:
                    seen_urls.add(h["url"])
                    results.append(h)
        if not results:
            continue
        tool_doms, bigs, top_results = set(), set(), []
        for h in results:
            dom = urlparse(h["url"]).netloc.removeprefix("www.")
            blob = (h["title"] + " " + h["url"]).lower()
            if any(w in blob for w in TOOL_HINTS) and not any(dom.endswith(cd) for cd in CONTENT_DOMAINS):
                tool_doms.add(dom)
            if dom.endswith(".gov") or any(dom == b or dom.endswith("." + b) for b in BIG_SITES):
                bigs.add(dom)
            if len(top_results) < 8:
                top_results.append(f"{dom} — {h['title'][:70]}")
        c["scan"] = {
            "queries": queries,
            "tool_count": len(tool_doms),
            "big_players": sorted(bigs),
            "no_tool_pages": not tool_doms,
            "top_results": top_results,
        }
    print(f"竞品核查：{sum(1 for c in cards if 'scan' in c)}/{len(cards)} 张卡已核查（{used} 次搜索）")


def llm_judge(cfg, cards):
    if not cards:
        return []
    slim = []
    for i, c in enumerate(cards):
        s = {k: c[k] for k in ("pain", "who", "existing", "site_idea", "window") if k in c}
        s["idx"] = i
        if c.get("scan"):
            s["market_scan"] = c["scan"]
        slim.append(s)
    try:
        scores = call_claude(cfg, JUDGE_PROMPT.replace("{cards}", json.dumps(slim, ensure_ascii=False)))
    except Exception as e:
        print(f"[warn] judge: {e}", file=sys.stderr)
        scores = []
    by_idx = {s["idx"]: s for s in scores if isinstance(s.get("idx"), int)}
    for i, c in enumerate(cards):
        s = by_idx.get(i, {})
        c["scores"] = {k: s.get(k, 3) for k in ("buildable", "monetize", "gap")}
        c["verdict"] = s.get("verdict", "")
        c["total"] = sum(c["scores"].values())
    cards.sort(key=lambda c: -c["total"])
    return cards[: cfg["llm"]["top_n"]]


# ---------------------------------------------------------------- 事件日历

def upcoming_events(cfg, today=None):
    today = today or datetime.now(timezone.utc).date()
    hits = []
    for ev in cfg["events"]:
        for year in (today.year, today.year + 1):
            try:
                d = datetime(year, ev["month"], ev["day"]).date()
            except ValueError:
                continue
            days = (d - today).days
            if 0 <= days <= ev["lead_weeks"] * 7:
                hits.append((days, ev))
                break
    hits.sort()
    return hits


# ---------------------------------------------------------------- v0.2：历史频率

STOPWORDS = set("的 了 和 与 在 是 为 不 有 无 也 都 或 而 及 等 个 中 上 下 到 从 对 把 被 让 使 能 会 要 就 还 更 很 太 最 一个 一种 一些 如何 怎么 什么 哪些 没有 难以 缺乏 无法 不知道 找不到 用户 网站 工具 平台 服务 需求 问题 方式 情况 相关 进行 提供 需要 可以 通过 由于 导致 但是 因为 所以 自己 他们 我们".split())


def pain_keywords(card, n=6):
    """从痛点+建议里抽中文关键词做相似度比对（无分词库，按 2-4 字滑窗取高频片段）。"""
    text = f"{card.get('pain', '')} {card.get('site_idea', '')} {card.get('who', '')}"
    zh = re.findall(r"[一-鿿]{2,}", text)
    en = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", text)]
    grams = {}
    for seg in zh:
        for size in (3, 2):
            for i in range(len(seg) - size + 1):
                g = seg[i : i + size]
                if g not in STOPWORDS:
                    grams[g] = grams.get(g, 0) + (2 if size == 3 else 1)
    for w in en:
        if w not in ("the", "and", "for", "with"):
            grams[w] = grams.get(w, 0) + 2
    return sorted(grams, key=lambda g: -grams[g])[:n]


def check_recurrence(db, card, days=90):
    """返回 (出现次数, 上次日期)；靠关键词重合度判定同一痛点。"""
    kws = set(card.get("_keywords", []))
    if not kws:
        return 1, None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    hits = []
    for date, kw_str in db.execute(
        "SELECT date, keywords FROM pains WHERE date >= ? ORDER BY date DESC", (cutoff,)
    ):
        old = set((kw_str or "").split(","))
        if old and len(kws & old) / min(len(kws), len(old)) >= 0.5:
            hits.append(date)
    return len(hits) + 1, (hits[0] if hits else None)


def record_pains(db, cards):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for c in cards:
        s = c.get("scores", {})
        db.execute(
            "INSERT INTO pains (date, item_id, pain, who, site_idea, window, keywords,"
            " buildable, monetize, gap, total, tool_count, url)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (today, c["item"]["id"], c.get("pain", ""), c.get("who", ""), c.get("site_idea", ""),
             c.get("window", ""), ",".join(c.get("_keywords", [])),
             s.get("buildable"), s.get("monetize"), s.get("gap"), c.get("total"),
             (c.get("scan") or {}).get("tool_count"), c["item"]["url"]),
        )
    db.commit()


def feedback_links(cfg, card, rank):
    """👍/👎 = 预填的 GitHub Issue 链接，点开即提交，数据落在私有仓库 issues。"""
    repo = cfg.get("feedback_repo")
    if not repo:
        return ""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = requests.utils.quote(f"[{date}] #{rank} {card.get('pain', '')[:50]}")
    body = requests.utils.quote(
        f"卡片：{card.get('pain', '')}\n建议：{card.get('site_idea', '')}\n"
        f"原帖：{card['item']['url']}\n评分：{card.get('scores')}\n\n补充理由（可选）：\n"
    )
    base = f"https://github.com/{repo}/issues/new?title={title}&body={body}&labels="
    return f"- **反馈**：[👍 值得做]({base}good) ・ [👎 不行]({base}bad)"


# ---------------------------------------------------------------- 日报

def render_report(cfg, top_cards, events, n_raw, n_filtered):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    L = [f"# 需求雷达日报 {today}", "",
         f"今日扫描 {n_raw} 条 → 粗筛 {n_filtered} 条 → 精选 {len(top_cards)} 条", ""]

    if events:
        L.append("## ⏰ 窗口期提醒")
        for days, ev in events:
            L.append(f"- **{days} 天后**：{ev['name']} → 可做：{ev['ideas']}")
        L.append("")

    L.append("## 🔥 今日痛点 Top")
    for i, c in enumerate(top_cards, 1):
        it = c["item"]
        s = c["scores"]
        ev = c.get("evidence", "")[:200]
        if it["ups"] or it["comments"]:
            meta = f"{it['ups']} 赞 / {it['comments']} 评"
        else:
            meta = "句式命中" if it["line"] == "search" else "当日热帖"
        src = it["sub"] if it["source"] == "reddit" else it["source"]
        n_seen, last_date = c.get("_recur", (1, None))
        badge = f"　🔁 **第 {n_seen} 次出现**（上次 {last_date}）" if n_seen > 1 else ""
        L += [
            f"### {i}. {c['pain']}",
            f"- **谁在痛**：{c['who']}　**窗口**：{c.get('window', '?')}{badge}",
            f"- **证据**：r/{src}（{meta}）"
            f"：\"{ev}\" — [原帖]({it['url']})",
            f"- **现状**：{c.get('existing', '')}",
            f"- **可做**：{c['site_idea']}",
            f"- **评分**：可建 {s['buildable']}/5 · 变现 {s['monetize']}/5 · 空白 {s['gap']}/5"
            + (f" · 点评：{c['verdict']}" if c.get("verdict") else ""),
        ]
        fb = feedback_links(cfg, c, i)
        if fb:
            L.append(fb)
        L.append("")
    if not top_cards:
        L.append("今天没有过筛的痛点（阈值可在 config.yaml 调低）。")
    return "\n".join(L)


def send_email(cfg, subject, md_body):
    import markdown as mdlib

    html = mdlib.markdown(md_body)
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": cfg["email"]["from"],
            "to": [cfg["email"]["to"]],
            "subject": subject,
            "html": html,
        },
        timeout=30,
    )
    r.raise_for_status()
    print(f"邮件已发送: {r.json()}")


# ---------------------------------------------------------------- 自测样例

SAMPLE_ITEMS = [
    {"id": "reddit:sample1", "source": "reddit", "line": "search", "vertical": "搜索",
     "title": "Is there a tool that calculates security deposit interest by state?",
     "text": "My landlord returned my deposit without interest. Every state has different rules and I can't find a simple calculator anywhere.",
     "url": "https://www.reddit.com/r/renting/sample1", "sub": "renting",
     "ups": 45, "comments": 23, "created": time.time()},
    {"id": "reddit:sample2", "source": "reddit", "line": "vertical", "vertical": "学贷与大学申请",
     "title": "Why is the SAI calculation so confusing??",
     "text": "The new FAFSA formula makes no sense. Paid three sites and still don't know what we'll owe.",
     "url": "https://www.reddit.com/r/ApplyingToCollege/sample2", "sub": "ApplyingToCollege",
     "ups": 320, "comments": 88, "created": time.time()},
]

SAMPLE_CARDS = [
    {"pain": "租客不知道各州押金利息规则，也找不到计算器", "who": "美国租客",
     "evidence": "Every state has different rules and I can't find a simple calculator anywhere.",
     "existing": "各州官网法条难读，无聚合工具", "site_idea": "按州押金利息计算器+追讨信模板",
     "window": "常青", "item": SAMPLE_ITEMS[0],
     "scores": {"buildable": 5, "monetize": 4, "gap": 4}, "verdict": "小而美，SEO 长尾词一抓一把", "total": 13},
]


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="不发邮件")
    ap.add_argument("--no-llm", action="store_true", help="只抓取粗筛")
    ap.add_argument("--selftest", action="store_true", help="离线自测")
    args = ap.parse_args()

    cfg = load_config()
    db = db_connect()

    if args.selftest:
        raw = SAMPLE_ITEMS
        filtered = coarse_filter(raw, cfg, db)
        report = render_report(cfg, SAMPLE_CARDS, upcoming_events(cfg), len(raw), len(filtered))
        print(report)
        print("\n[selftest] OK: 抓取样例→粗筛→渲染 全链路通过（LLM 与邮件已跳过）")
        return

    raw = fetch_subreddits(cfg) + fetch_searches(cfg) + fetch_hackernews(cfg) + fetch_google_trends(cfg)
    print(f"抓取 {len(raw)} 条")
    filtered = coarse_filter(raw, cfg, db)
    print(f"粗筛后 {len(filtered)} 条")

    if args.no_llm:
        for it in filtered[:30]:
            print(f"  [{it['line']}/{it['vertical']}] {it['ups']}↑ {it['title'][:80]}")
        return

    cards = llm_extract(cfg, filtered)
    print(f"LLM 提炼 {len(cards)} 张卡片")
    competitor_scan(cfg, cards)
    top = llm_judge(cfg, cards)

    for c in top:  # 只把进入日报的标记为已见，落选的明天还有机会
        mark_seen(db, c["item"]["id"])
        c["_keywords"] = pain_keywords(c)
        c["_recur"] = check_recurrence(db, c)
    db.commit()
    record_pains(db, top)

    report = render_report(cfg, top, upcoming_events(cfg), len(raw), len(filtered))
    (ROOT / "reports").mkdir(exist_ok=True)
    out = ROOT / "reports" / f"{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text(report, encoding="utf-8")
    print(f"日报已存 {out}")

    if not args.dry_run:
        subject = f"{cfg['email']['subject_prefix']} {datetime.now(timezone.utc):%m-%d} · {len(top)} 个机会"
        send_email(cfg, subject, report)
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()
