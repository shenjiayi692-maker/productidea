# HANDOFF：给 Claude Code 的交接文档

## 项目背景（30 秒版）

Jiayi 要一个「需求雷达」：每天自动扫描英文社区讨论和热点，用 LLM 提炼出**具体、真实、可以 1-3 天 vibecode 成小网站变现**的痛点，发中文日报到 shenjiayi692@gmail.com。完整产品定义见上级目录 `PRD-需求雷达.md`。

本目录（needs-radar）代码已写完并通过离线自测，但**未在真实网络环境端到端跑过**（编写环境沙箱无法连 Reddit/Anthropic/Resend）。你的任务是联网调试并部署。

## 架构

```
radar.py 单文件流水线：
抓取(Reddit定向subreddit + Reddit关键词搜索 + HN + Google Trends RSS)
→ 粗筛(互动阈值 + SQLite 去重, data/seen.db)
→ Claude API 两轮(提炼痛点卡片 → 评分排序)
→ 渲染中文 Markdown 日报(reports/YYYY-MM-DD.md)
→ Resend 发邮件
```

配置全在 `config.yaml`（9 个垂直领域 + 5 个搜索句式 + 阈值），周期性事件在 `events.yaml`。同目录 `../english-hot-api` 是独立的英文热榜 API 项目（Node），雷达不依赖它，不用管。

## 你要做的事（按序）

1. `pip install -r requirements.txt`，复制 `.env.example` 为 `.env` 填好两个 key（用户提供）。
2. `python radar.py --selftest` —— 应打印样例日报并显示 OK。
3. `python radar.py --no-llm` —— 真实抓取+粗筛。**预期问题**：
   - Reddit 403/429：加长 `time.sleep`，或 UA 被封时换一个描述性 UA；仍不行则实现 OAuth（免费 script app，改 `get()` 走 `oauth.reddit.com` + token）。
   - 某 subreddit 名字失效/私有化：从 config.yaml 移除即可，单源失败已有容错。
4. `python radar.py --dry-run` —— 走完 LLM 两轮，检查 reports/ 下日报质量：
   - 卡片少于 5 张 → 调低 config 阈值或检查 extract prompt 是否解析失败（看 stderr warn）。
   - JSON 解析失败率高 → 在 `call_claude()` 里加重试或改用 tool-use 强制 JSON。
5. `python radar.py` —— 真实发一封邮件确认收到（Resend 免费档 from 必须是 onboarding@resend.dev，除非用户验证了域名）。
6. 部署：建私有 GitHub 仓库（整个 productidea 或单独 needs-radar 均可，workflow 里路径按 needs-radar/ 写的），推送后在 repo Settings → Secrets 配 `ANTHROPIC_API_KEY`、`RESEND_API_KEY`，手动 workflow_dispatch 跑一次验证。

## 已知设计决策（别改，除非用户要求）

- 只有**进入日报的条目**才标记 seen，落选的次日可再进（信号可能变强）。
- 搜索线（"is there a tool that" 等句式）阈值低且排序优先——信噪比最高的入口。
- 日报中文、证据引用保留英文原文。
- 成本控制：max_candidates=120，extract 分批 20 条/次，约 7 次调用/天。

## v0.2 待办清单（v0.1 稳定跑两周后再做，按优先级排序）

1. ✅（2026-07-14 已实现并激活，用 SerpAPI 免费档；支持 SERPER_API_KEY/SERPAPI_API_KEY 二选一）**自动竞品核查（最优先）**：评委轮之前，对每张卡片的 site_idea 生成 2-3 个英文搜索词，
   调搜索 API（Brave Search API 免费 2000 次/月，或 SerpAPI）查首页结果，统计：
   现成工具数量、是否有大站/官方工具占位、是否全是内容页而无工具页（=空白信号）。
   把结果作为事实依据喂给评委轮，替代 LLM 凭印象打的 gap 分。
2. **历史频率检查**：seen.db 加一张 pains 表存历次卡片的 pain 向量或关键词；
   新卡片入库时比对过去 30/90 天的相似记录，日报标注「该痛点第 N 次出现」。
   反复出现 = 慢性痛（常青工具），单次爆发 = 事件性（要抢窗口）。
3. **机会打分升级**：Google Trends 关键词搜索量趋势拉进评分。
4. **一键生成 vibecoding prompt**：对日报 Top 3 自动附一段可直接喂给 AI 编程工具的
   MVP 需求描述（功能边界、页面结构、SEO 关键词、变现位）。
5. **App Store / Chrome 商店差评挖掘**：新信号源，差评 = 已验证付费市场的未满足需求。

## 用户偏好

回复务必简洁。改动前先说清楚要动什么。
