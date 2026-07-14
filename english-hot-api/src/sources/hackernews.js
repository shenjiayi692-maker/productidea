import { fetchWith, ok } from "../utils.js";

// HN Algolia API，免费无鉴权
// type: front_page | ask_hn | show_hn
export async function hackernews({ type = "front_page", limit = 30 } = {}) {
  const tag = ["front_page", "ask_hn", "show_hn"].includes(type)
    ? type
    : "front_page";
  const url = `https://hn.algolia.com/api/v1/search?tags=${tag}&hitsPerPage=${limit}`;
  const res = await fetchWith(url);
  const json = await res.json();

  const items = (json.hits || []).map((h) => ({
    id: h.objectID,
    title: h.title,
    url: h.url || `https://news.ycombinator.com/item?id=${h.objectID}`,
    mobileUrl: `https://news.ycombinator.com/item?id=${h.objectID}`,
    hot: h.points ?? 0,
    extra: { comments: h.num_comments ?? 0, author: h.author },
    time: h.created_at,
  }));

  return ok("hackernews", `Hacker News · ${tag}`, items, { type: tag });
}
