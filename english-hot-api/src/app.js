import { Hono } from "hono";
import { cors } from "hono/cors";
import { cached, err } from "./utils.js";
import { hackernews } from "./sources/hackernews.js";
import { reddit } from "./sources/reddit.js";
import { github } from "./sources/github.js";
import { googleTrends } from "./sources/googletrends.js";

const TTL = 10 * 60 * 1000; // 缓存 10 分钟

export const app = new Hono();
app.use("*", cors());

app.get("/", (c) =>
  c.json({
    name: "english-hot-api",
    version: "0.1.0",
    routes: {
      "/hackernews": "params: type=front_page|ask_hn|show_hn, limit",
      "/reddit": "params: sub (default all, supports a+b), sort=hot|top|rising|new, limit",
      "/github": "params: since=daily|weekly|monthly, lang",
      "/google-trends": "params: geo (default US)",
      "/all": "aggregate of all four sources",
    },
  })
);

const wrap = (name, fn) => async (c) => {
  try {
    const q = c.req.query();
    const key = `${name}:${JSON.stringify(q)}`;
    const data = await cached(key, TTL, () => fn(q));
    return c.json(data);
  } catch (e) {
    return c.json(err(name, e.message), 500);
  }
};

app.get("/hackernews", wrap("hackernews", (q) => hackernews(q)));
app.get("/reddit", wrap("reddit", (q) => reddit(q)));
app.get("/github", wrap("github", (q) => github(q)));
app.get("/google-trends", wrap("google-trends", (q) => googleTrends(q)));

// 聚合接口：并行抓四源，单源失败不影响整体
app.get("/all", async (c) => {
  const q = c.req.query();
  const tasks = {
    hackernews: () => hackernews(q),
    reddit: () => reddit(q),
    github: () => github(q),
    "google-trends": () => googleTrends(q),
  };
  const entries = await Promise.all(
    Object.entries(tasks).map(async ([name, fn]) => {
      try {
        const key = `${name}:${JSON.stringify(q)}`;
        return [name, await cached(key, TTL, fn)];
      } catch (e) {
        return [name, err(name, e.message)];
      }
    })
  );
  return c.json({
    code: 200,
    updateTime: new Date().toISOString(),
    sources: Object.fromEntries(entries),
  });
});
