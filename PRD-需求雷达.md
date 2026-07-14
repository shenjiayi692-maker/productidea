# PRD：需求雷达（Niche Radar）

版本 v0.1 · 2026-07-13 · Owner: Jiayi

## 1. 一句话定义

每日自动扫描英文互联网的真实讨论与即时事件，提炼出「具体、真实、可 vibecode 成小网站变现」的 niche 痛点清单，推送到我的邮箱。

## 2. 背景与目标

- 目标用户：自己（indie hacker），验证有效后再产品化为 SaaS。
- 核心价值：把「找点子」从刷帖数小时压缩到每天读一封 5 分钟的邮件。
- 成功标准（自用阶段）：
  - 每周至少产出 3 个我认为「值得做」的点子；
  - 3 个月内至少 1 个点子被 vibecode 上线并产生首笔收入或可观流量。

## 3. 信号来源（MVP 范围）

| 来源 | 内容 | 获取方式 | 难度 |
|---|---|---|---|
| Reddit | 细分 subreddit 的抱怨/求助帖（"is there a tool that…"、"I hate that…"、"how do I…"） | 官方 API（免费额度 100 QPM，个人用足够）| 低 |
| Hacker News | Ask HN / Show HN 评论区痛点 | Algolia HN API，免费无鉴权 | 低 |
| Google Trends | 突发搜索飙升（即时事件信号，如考试季、报税季） | pytrends（非官方，偶尔失效） | 中 |
| Product Hunt | 新品评论区的"缺了 X 功能"抱怨 | 官方 GraphQL API | 低 |
| 日历事件库 | 可预测的周期性窗口：报税季、开学季、黑五、世界杯… | 手工维护一个 YAML | 极低 |

**不做（v0.1）**：Twitter/X（API 太贵）、TikTok/小红书（无合规 API、爬虫风控重）、App Store 评论（v0.2 再加）。

## 4. 核心流程

```
每日 cron（UTC 06:00）
 → 抓取：各源近 24h 内容（关键词模板 + 订阅的 subreddit 列表）
 → 过滤：互动量阈值（如 Reddit ≥20 upvotes 或 ≥10 条共鸣评论）、去重、排除已收录
 → LLM 提炼：每条候选 → {痛点一句话, 原文引用, 链接, 谁在痛, 现有替代方案, 建议的网站形态}
 → LLM 粗筛：剔除「需要 App/硬件/牌照」「巨头已解决」「纯情绪无需求」类
 → 生成日报：Top 10 痛点清单，按讨论热度排序
 → 推送：邮件（Resend/SMTP）
```

## 5. 日报格式（单条示例）

> **痛点**：美国大学生抱怨 FAFSA 新表格的 SAI 计算完全看不懂
> **证据**：r/ApplyingToCollege，帖子 3 天 480 upvotes，"why is there no simple calculator for this" ×7 条评论 → [链接]
> **谁在痛**：申请季学生和家长（季节性：10月–3月）
> **现状**：官方工具难用，无独立计算器排名靠前
> **可做**：单页 SAI 计算器 + AdSense/邮件订阅，vibecode 1 天可上线

## 6. 技术方案（自用版）

- 一个 Python 脚本 + GitHub Actions 定时跑（零服务器成本）；
- 数据存 SQLite / JSON 文件（去重用）；
- LLM 用 Claude API，每天成本估计 <$0.5；
- 邮件用 Resend 免费档。

## 7. 明确不做 / 风险提示

- **不自动验证需求真伪**：工具只提供「证据链」（原帖链接+互动数据），判断留给人。自动打分放 v0.2。
- **Reddit API 合规**：GummySearch 因拿不到商业授权关停。自用免费档没问题，**产品化前必须先解决商业授权**，这是产品化的最大风险。
- **即时事件窗口短**：热点类点子从发现到上线要 <48h 才有意义，所以日报必须每天跑、事件类条目单独标注「窗口期」。
- **Google Trends 无官方 API**：pytrends 可能随时挂，做好降级（挂了就跳过该源）。

## 8. 里程碑

- **W1**：Reddit + HN 两源跑通，邮件日报发出第一封。
- **W2**：加 LLM 提炼与过滤，日报可读性达标。
- **W3**：加 Google Trends + 事件日历，覆盖即时性机会。
- **W4–**：用 4 周日报实际选题并上线 1 个网站；复盘信号质量，决定是否加打分/产品化。

## 9. v0.2 候选（不承诺，详细清单见 needs-radar/HANDOFF.md）

按优先级：自动竞品核查（搜索 API 查首页现成工具，把 gap 分从 LLM 印象变成事实）、
历史频率检查（同类痛点 30/90 天内重复出现 = 慢性痛，单次爆发 = 事件性窗口）、
Google Trends 搜索量入评分、一键生成 vibecoding prompt、App Store/Chrome 商店差评挖掘、Dashboard 检索。

## 附：可借鉴的开源项目

- [DailyHotApi](https://github.com/imsyy/DailyHotApi)：多平台热榜聚合架构参考（若日后加中文源可直接用）
- [reddit-pain-point-analyzer](https://github.com/thebarbariangroup/reddit-pain-point-analyzer)：Reddit 抓取 + GPT 提炼痛点的完整流程，与本项目核心环节几乎一致
- [pytrends](https://github.com/GeneralMills/pytrends)：Google Trends 非官方 API
- [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)：中文平台爬虫（合规风险自担，v0.1 不用）
- n8n 的 [Reddit→AI→MVP idea 工作流](https://n8n.io/workflows/3824-auto-generate-mvp-startup-ideas-from-reddit-with-ai-and-excel-storage/)：无代码版同类流程，可参考其 prompt 设计
