import { XMLParser } from "fast-xml-parser";
import { fetchWith, ok } from "../utils.js";

// Google Trends 每日热搜 RSS，免费无鉴权
// geo: US / GB / CA / AU ...
export async function googleTrends({ geo = "US" } = {}) {
  const safeGeo = String(geo).replace(/[^A-Za-z-]/g, "").toUpperCase() || "US";
  const url = `https://trends.google.com/trending/rss?geo=${safeGeo}`;
  const res = await fetchWith(url);
  const xml = await res.text();

  const parser = new XMLParser({ ignoreAttributes: false });
  const parsed = parser.parse(xml);
  let rssItems = parsed?.rss?.channel?.item || [];
  if (!Array.isArray(rssItems)) rssItems = [rssItems];

  const items = rssItems.map((it, i) => {
    let news = it["ht:news_item"] || [];
    if (!Array.isArray(news)) news = [news];
    const traffic = String(it["ht:approx_traffic"] || "0");
    return {
      id: `${safeGeo}-${i}-${it.title}`,
      title: it.title,
      url: `https://www.google.com/search?q=${encodeURIComponent(it.title)}`,
      mobileUrl: `https://www.google.com/search?q=${encodeURIComponent(it.title)}`,
      hot: parseInt(traffic.replace(/[^\d]/g, ""), 10) || 0,
      extra: {
        approxTraffic: traffic,
        news: news.slice(0, 3).map((n) => ({
          title: n["ht:news_item_title"],
          url: n["ht:news_item_url"],
          source: n["ht:news_item_source"],
        })),
      },
      time: it.pubDate ? new Date(it.pubDate).toISOString() : null,
    };
  });

  return ok("google-trends", `Google Trends · ${safeGeo}`, items, {
    geo: safeGeo,
  });
}
