import { fetchWith, ok } from "../utils.js";

// Reddit 公开 JSON 接口。注意：
// 1. 必须带自定义 User-Agent，否则 429/403
// 2. 数据中心 IP（如 Vercel）可能被 403，见 README 的 OAuth 降级方案
// sort: hot | top | rising
export async function reddit({ sub = "all", sort = "hot", limit = 30 } = {}) {
  const safeSub = String(sub).replace(/[^\w+]/g, ""); // 支持 r/a+b 多版块
  const safeSort = ["hot", "top", "rising", "new"].includes(sort) ? sort : "hot";
  const url = `https://www.reddit.com/r/${safeSub}/${safeSort}.json?limit=${limit}&raw_json=1`;
  const res = await fetchWith(url, {
    headers: { "User-Agent": "web:english-hot-api:v0.1 (personal aggregator)" },
  });
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
      },
      time: new Date(d.created_utc * 1000).toISOString(),
    }));

  return ok("reddit", `Reddit · r/${safeSub} · ${safeSort}`, items, {
    sub: safeSub,
    sort: safeSort,
  });
}
