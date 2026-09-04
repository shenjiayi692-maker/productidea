# english-hot-api

英文互联网热榜聚合 API，对标 [DailyHotApi](https://github.com/imsyy/DailyHotApi) 的架构（每源一个路由 + 聚合接口 + 内存缓存 + Vercel 部署），数据源换成英文世界四大免费源。

## 数据源

| 路由 | 来源 | 参数 | 鉴权 |
|---|---|---|---|
| `/hackernews` | HN Algolia API | `type=front_page\|ask_hn\|show_hn`，`limit` | 无 |
| `/reddit` | Reddit RSS（匿名）／官方 OAuth（配了凭据时） | `sub`（默认 all，支持 `a+b` 多版块），`sort=hot\|top\|rising\|new`，`t`（sort=top 时的时间范围），`limit` | 可选 |
| `/github` | GitHub Trending 页面解析 | `since=daily\|weekly\|monthly`，`lang` | 无 |
| `/google-trends` | Google Trends 每日热搜 RSS | `geo`（默认 US） | 无 |
| `/all` | 以上四源并行聚合（单源失败不影响整体） | 透传以上参数 | 无 |

统一返回格式（对齐 DailyHotApi）：

```json
{
  "code": 200,
  "name": "hackernews",
  "title": "Hacker News · front_page",
  "total": 30,
  "updateTime": "...",
  "data": [
    { "id": "...", "title": "...", "url": "...", "hot": 1066, "extra": { "comments": 1206 }, "time": "..." }
  ]
}
```

## 运行

```bash
npm install
npm start          # http://localhost:6689
```

部署 Vercel：仓库根目录直接 `vercel deploy`（已含 `vercel.json` 和 `api/index.js` 入口）。

## 已知限制与注意事项

1. **Reddit 匿名 `.json` 接口已于 2026-07 全面失效**（一律 403，换 User-Agent 无效，与 IP 无关）。
   现默认走免登录的 `.rss`，**代价是拿不到赞数和评论数**——返回项里 `hot` 恒为 0、`extra.comments` 为 null，
   并以 `extra.scored: false` 标记，调用方不要拿 `hot` 给这些条目排序。
   想要完整数据就配 `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`（reddit.com/prefs/apps 免费 script app），
   代码会自动改走 `oauth.reddit.com`，返回项 `params.via` 会从 `rss` 变成 `oauth`。
   另注意 RSS 突发限流较严，已内置 5/10/20 秒退避重试，配合 10 分钟缓存足够日常使用。
2. **GitHub Trending 是页面解析**：GitHub 改版会导致解析失效，属正常维护成本（DailyHotApi 的各源也一样）。
3. **Google Trends RSS** 每个地区约 10~20 条，只有当日热搜，无历史数据。
4. 缓存为进程内存，10 分钟 TTL。Vercel serverless 冷启动后缓存清空——够用；要持久缓存可加 Upstash Redis。
5. 抓取行为请遵守各平台 robots/ToS；本项目仅供个人研究聚合使用，产品化前需评估各源商用条款（尤其 Reddit）。

## 与需求雷达的关系

**没有依赖关系。** 曾设想让需求雷达调本 API 的 `/all` 取数，最终没有这么做——
[../needs-radar](../needs-radar) 自己直连抓取，两个项目互不影响。原因见[根 README](../README.md)：
两者形态不同（一个是 HTTP 服务、一个是批处理管道），共用抓取层会给每天在跑的雷达引入新的失败点。

本项目当前处于休眠状态，作为独立的热榜 API 保留。真要拿它当数据层时这样用：

```
/reddit?sub=SideProject+Entrepreneur+smallbusiness&sort=top&t=day&limit=50
```
