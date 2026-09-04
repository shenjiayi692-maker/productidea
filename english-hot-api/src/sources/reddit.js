import { XMLParser } from "fast-xml-parser";
import { fetchWith, ok } from "../utils.js";

// Reddit 自 2026-07 起对匿名 .json 接口一律返回 403（换 UA 无效）。
// 因此默认走免登录的 .rss，代价是拿不到赞数/评论数（hot 恒为 0，见 extra.scored）。
// 配了 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET 则改走官方 OAuth，数据完整。
// 同样的取舍见 ../../needs-radar/radar.py 的 fetch_subreddits()。

const SORTS = ["hot", "top", "rising", "new"];
const TOP_RANGES = ["hour", "day", "week", "month", "year", "all"];
const UA = "web:english-hot-api:v0.1 (personal aggregator)";

// RSS 突发限流较严，实测退避需 10 秒量级（radar.py 用的是 8/16/24 秒）。
// 这里是 API 不能让请求挂太久，取 5/10/20 秒共三次重试，配合 app.js 的 10 分钟缓存足够。
async function fetchRss(url, tries = 4) {
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetchWith(url, { headers: { "User-Agent": UA } });
      return await res.text();
    } catch (e) {
      if (!/HTTP 429/.test(e.message) || i === tries - 1) throw e;
      await new Promise((r) => setTimeout(r, 5000 * 2 ** i));
    }
  }
}

let tokenCache = null; // { token, exp }

async function oauthToken() {
  if (tokenCache && Date.now() < tokenCache.exp) return tokenCache.token;
  const basic = Buffer.from(
    `${process.env.REDDIT_CLIENT_ID}:${process.env.REDDIT_CLIENT_SECRET}`
  ).toString("base64");
  const res = await fetchWith("https://www.reddit.com/api/v1/access_token", {
    method: "POST",
    headers: {
      Authorization: `Basic ${basic}`,
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": UA,
    },
    body: "grant_type=client_credentials",
  });
  const j = await res.json();
  tokenCache = { token: j.access_token, exp: Date.now() + (j.expires_in - 60) * 1000 };
  return tokenCache.token;
}

function entryToItem(e) {
  const rawId = String(e.id || "");
  const id = rawId.includes("_") ? rawId.split("_").pop() : rawId;
  const url = e.link?.["@_href"] || "";
  const label = e.category?.["@_label"] || e.category?.["@_term"] || "";
  const time = e.published || e.updated || null;
  return {
    id,
    title: typeof e.title === "string" ? e.title : String(e.title ?? ""),
    url,
    mobileUrl: url,
    hot: 0, // RSS 不提供赞数
    extra: {
      comments: null,
      subreddit: label.replace(/^r\//, ""),
      flair: null,
      externalUrl: null,
      scored: false, // 提醒调用方：本条目无热度数据，排序不可依赖 hot
    },
    time: time ? new Date(time).toISOString() : null,
  };
}

export async function reddit({ sub = "all", sort = "hot", limit = 30, t = "day" } = {}) {
  const safeSub = String(sub).replace(/[^\w+]/g, "") || "all"; // 支持 r/a+b 多版块
  const safeSort = SORTS.includes(sort) ? sort : "hot";
  const safeLimit = Math.min(Math.max(parseInt(limit, 10) || 30, 1), 100);
  const safeT = TOP_RANGES.includes(t) ? t : "day";
  const query = `limit=${safeLimit}${safeSort === "top" ? `&t=${safeT}` : ""}`;
  const meta = { sub: safeSub, sort: safeSort, ...(safeSort === "top" && { t: safeT }) };

  // 有凭据 → OAuth，数据带赞数与评论数
  if (process.env.REDDIT_CLIENT_ID && process.env.REDDIT_CLIENT_SECRET) {
    const token = await oauthToken();
    const res = await fetchWith(
      `https://oauth.reddit.com/r/${safeSub}/${safeSort}?${query}&raw_json=1`,
      { headers: { Authorization: `Bearer ${token}`, "User-Agent": UA } }
    );
    const json = await res.json();
    const items = (json.data?.children || [])
      .map((c) => c.data)
      .filter((d) => d && !d.stickied)
      .map((d) => ({
        id: d.id,
        title: d.title,
        url: `https://www.reddit.com${d.permalink}`,
        mobileUrl: `https://www.reddit.com${d.permalink}`,
        hot: d.ups ?? 0,
        extra: {
          comments: d.num_comments ?? 0,
          subreddit: d.subreddit,
          flair: d.link_flair_text || null,
          externalUrl: d.is_self ? null : d.url,
          scored: true,
        },
        time: new Date(d.created_utc * 1000).toISOString(),
      }));
    return ok("reddit", `Reddit · r/${safeSub} · ${safeSort}`, items, {
      ...meta,
      via: "oauth",
    });
  }

  // 无凭据 → 免登录 RSS
  const xml = await fetchRss(
    `https://www.reddit.com/r/${safeSub}/${safeSort}.rss?${query}`
  );
  const parsed = new XMLParser({ ignoreAttributes: false }).parse(xml);
  let entries = parsed?.feed?.entry || [];
  if (!Array.isArray(entries)) entries = [entries];

  const items = entries.map(entryToItem).filter((it) => it.id && it.url);
  return ok("reddit", `Reddit · r/${safeSub} · ${safeSort}`, items, {
    ...meta,
    via: "rss",
    note: "匿名 RSS 不含赞数/评论数，hot 恒为 0；配置 REDDIT_CLIENT_ID/SECRET 可获取完整数据",
  });
}
