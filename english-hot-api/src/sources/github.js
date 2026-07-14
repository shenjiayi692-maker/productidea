import * as cheerio from "cheerio";
import { fetchWith, ok } from "../utils.js";

// GitHub Trending 无官方 API，抓取页面解析
// since: daily | weekly | monthly；lang 可选（如 javascript、python）
export async function github({ since = "daily", lang = "" } = {}) {
  const safeSince = ["daily", "weekly", "monthly"].includes(since)
    ? since
    : "daily";
  const langPath = lang ? `/${encodeURIComponent(lang)}` : "";
  const url = `https://github.com/trending${langPath}?since=${safeSince}`;
  const res = await fetchWith(url);
  const html = await res.text();
  const $ = cheerio.load(html);

  const items = [];
  $("article.Box-row").each((_, el) => {
    const $el = $(el);
    const repo = $el.find("h2 a").attr("href")?.replace(/^\//, "") || "";
    const desc = $el.find("p").text().trim();
    const starsText = $el
      .find(`a[href="/${repo}/stargazers"]`)
      .text()
      .trim()
      .replace(/,/g, "");
    const periodStars = $el
      .find("span.d-inline-block.float-sm-right")
      .text()
      .trim();
    const language = $el.find('[itemprop="programmingLanguage"]').text().trim();
    if (!repo) return;
    items.push({
      id: repo,
      title: repo,
      url: `https://github.com/${repo}`,
      mobileUrl: `https://github.com/${repo}`,
      hot: parseInt(starsText, 10) || 0,
      extra: {
        description: desc || null,
        language: language || null,
        periodStars: periodStars || null,
      },
      time: null,
    });
  });

  return ok("github", `GitHub Trending · ${safeSince}`, items, {
    since: safeSince,
    lang: lang || null,
  });
}
