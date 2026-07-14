# english-hot-api

英文互联网热榜聚合 API，对标 [DailyHotApi](https://github.com/imsyy/DailyHotApi) 的架构（每源一个路由 + 聚合接口 + 内存缓存 + Vercel 部署），数据源换成英文世界四大免费源。

## 数据源

| 路由 | 来源 | 参数 | 鉴权 |
|---|---|---|---|
| `/hackernews` | HN Algolia API | `type=front_page\|ask_hn\|show_hn`，`limit` | 无 |
| `/reddit` | Reddit 公开 JSON | `sub`（默认 all，支持 `a+b` 多版块），`sort=hot\|top\|rising\|new`，`limit` | 无 |
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

1. **Reddit 反爬**：公开 `.json` 接口必须带自定义 User-Agent（已内置）。个人 IP 下稳定；**Vercel 等数据中心 IP 可能被 403**。若遇到，改用 Reddit 官方 OAuth（免费注册 script app，100 QPM 额度），把 `reddit.js` 的请求换成 `oauth.reddit.com` + token 即可。
2. **GitHub Trending 是页面解析**：GitHub 改版会导致解析失效，属正常维护成本（DailyHotApi 的各源也一样）。
3. **Google Trends RSS** 每个地区约 10~20 条，只有当日热搜，无历史数据。
4. 缓存为进程内存，10 分钟 TTL。Vercel serverless 冷启动后缓存清空——够用；要持久缓存可加 Upstash Redis。
5. 抓取行为请遵守各平台 robots/ToS；本项目仅供个人研究聚合使用，产品化前需评估各源商用条款（尤其 Reddit）。

## 用作「需求雷达」的数据层

需求雷达（见 PRD）每日 cron 直接请求 `/all`，再对 Reddit/HN 的条目跑 LLM 痛点提炼。推荐订阅的 subreddit 通过 `sub` 参数传入，如：

```
/reddit?sub=SideProject+Entrepreneur+smallbusiness&sort=top&limit=50
```
