# 需求雷达（needs-radar）

每天自动扫英文社区，用 LLM 提炼出**具体、真实、能 1–3 天 vibecode 成小网站变现**的痛点，发一封中文日报到邮箱。

不是网站，不是 skill——**一个 GitHub Actions 定时脚本**，没有界面、没有服务器、没有常驻进程。交互界面就是你的邮箱。

产品定义见 [../PRD-需求雷达.md](../PRD-需求雷达.md)，联调与部署过程见 [HANDOFF.md](HANDOFF.md)。

## 日报长什么样

摘自 [reports/2026-07-29.md](reports/2026-07-29.md)：

```markdown
### 1. Substack作者依赖平台域名和模板，缺乏真正属于自己、可自定义的独立网站
- **谁在痛**：Substack上的作家/内容创作者　**窗口**：常青
- **证据**：r/hackernews（530 赞 / 268 评）："Substack writers, you need a website" — [原帖](...)
- **现状**：Substack自带页面可自定义程度低，SEO 和品牌归属都被平台控制
- **可做**：做一个能一键抓取 Substack RSS 并生成可绑定自有域名的静态网站生成器
- **评分**：可建 3/5 · 变现 4/5 · 空白 4/5 · 点评：确实没人做这个细分工具,但
  Substack 作者是否愿意为脱离平台付费值得怀疑
- **反馈**：[👍 值得做](...) ・ [👎 不行](...)
```

同一痛点 90 天内再次出现时，「窗口」后面会多一个 `🔁 第 N 次出现（上次 YYYY-MM-DD）`。
反复出现 = 慢性痛，适合做常青工具；只冒一次 = 事件性，要抢窗口。

日报中文，证据引用保留英文原文。历史报告都在 [reports/](reports/)。

## 流水线

```
抓取 ──┬─ Reddit 定向 subreddit（免登录 top.rss）
       ├─ Reddit 句式搜索（Serper 搜 site:reddit.com "is there a tool that" 等）
       ├─ Hacker News（Algolia API）
       └─ Google Trends（RSS）
   ↓
粗筛 ── 互动阈值 + 36h 时效 + SQLite 去重（data/seen.db）
   ↓
LLM 第 1 轮 ── 提炼痛点卡片（含建议的英文搜索词）
   ↓
竞品核查 ── 拿卡片的搜索词真去 Google 查首页：几个现成工具？有无大站/官方占位？
   ↓
LLM 第 2 轮 ── 按「可建/变现/空白」打分排序（空白分以上一步的事实为准，不靠印象）
   ↓
历史频率 ── 比对过去 90 天，标注「🔁 第 N 次出现」
   ↓
渲染中文日报（reports/YYYY-MM-DD.md）→ Resend 发邮件 → 结果提交回仓库
```

**核心设计**：竞品核查这一步是整个系统最值钱的地方。LLM 凭印象打的「空白分」不可信——同一张「押金利息计算器」卡片，凭印象打 4/5，真去搜发现首页 11 个现成工具外加两个州政府官方计算器，实际是 1/5。假需求在这一步被事实拦掉。

## 快速开始

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # 然后自己填 key，见下表
```

跑起来（四种模式）：

```bash
.venv/bin/python radar.py --selftest   # 离线自测，不联网、不花钱，验证渲染链路
```

```bash
set -a && source ./.env && set +a && .venv/bin/python radar.py --no-llm   # 只抓取+粗筛，检查信号源
```

```bash
set -a && source ./.env && set +a && .venv/bin/python radar.py --dry-run  # 走完 LLM，存报告但不发邮件
```

```bash
set -a && source ./.env && set +a && .venv/bin/python radar.py            # 完整流程，真发邮件
```

完整跑一次约 7 分钟，大头是 Reddit RSS 的限流退避。

## 环境变量

| 变量 | 必需 | 去哪拿 | 不填会怎样 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | console.anthropic.com | 跑不了 |
| `RESEND_API_KEY` | ✅ | resend.com | 发不了邮件 |
| `SERPER_API_KEY` | 推荐 | serper.dev（注册送 2500 次） | 句式搜索线和竞品核查都停摆 |
| `SERPAPI_API_KEY` | 备选 | serpapi.com（免费 100 次/月） | Serper 的备胎，两者只用其一 |
| `REDDIT_CLIENT_ID` / `_SECRET` | 可选 | reddit.com/prefs/apps（script app） | 走免登录 RSS；填了则改走官方 OAuth，能多拿到赞数/评论数 |
| `RADAR_DATA_DIR` | 可选 | — | 默认 `./data`，测试时可指向临时目录避免污染 seen.db |

**注意**：`SERPER_API_KEY`（serper.dev）和 `SERPAPI_API_KEY`（serpapi.com）是两家不同的公司，名字极像，很容易拿错。代码优先用 Serper，没有才回落 SerpAPI。

## 配置（config.yaml）

| 段落 | 作用 |
|---|---|
| `feedback_repo` | 👍/👎 链接指向的私有仓库，留空则日报不显示反馈行 |
| `email` | 收件人、发件人、标题前缀 |
| `llm` | 模型、批大小、每日最多送 LLM 的候选数（控成本）、日报条数 |
| `subreddits` | 9 个垂直领域的定向版块 |
| `search_queries` | 5 个挖需求句式，**信噪比最高的入口** |
| `competitor_check` | 每卡搜几个词、每天搜索次数上限 |
| `filters` | 互动阈值与时效 |

周期性事件（返校季、报税季等）在 [events.yaml](events.yaml)，用来提前若干周提醒窗口期。

## 部署

已部署在 GitHub Actions：[.github/workflows/daily.yml](../.github/workflows/daily.yml)（注意在**仓库根目录**，不在本目录——Actions 只认根目录）。

- 排程 `0 6 * * *`（UTC）。实际触发常延迟 2–4 小时，这是 GitHub 免费额度的正常现象
- key 配在 repo Settings → Secrets（当前 4 个：Anthropic / Resend / Serper / SerpAPI；Reddit 那两个没配，所以走 RSS 路径）
- 跑完由 `radar-bot` 把 `seen.db` 和当天报告提交回 main

**本地开发前先 `git pull --rebase`**，bot 每天都会推提交。本地 dry-run 会生成同名报告文件挡住 rebase，删掉即可（云端版本权威）。

## 数据

`data/seen.db`（SQLite，跟着仓库走）：

| 表 | 用途 |
|---|---|
| `seen` | 去重。**只有进入日报的条目才标记 seen**——落选的次日可再进，因为信号可能变强 |
| `pains` | 历次卡片留档（痛点、建议、三维评分、竞品数、关键词）。当前用于「第 N 次出现」判定，日后 join 👍/👎 反馈做调优 |

## 反馈闭环（当前状态）

日报每张卡带 👍/👎，点开是预填好的 GitHub Issue，再点 Submit 就完事，数据落进私有仓库 issues：

```bash
gh issue list --label good --json title,body   # 之后这样导出
```

**目前只收集，不影响推送。** 明天推什么和你昨天点了什么无关——现在没有任何代码会去读这些标签。所谓「调优」目前指的是人工看数据后去改 `config.yaml` 的阈值和 `radar.py` 里的两段 prompt。

攒够几十条正负样本后，可以把标注过的卡片作为范例注入 prompt（「这类他打勾、这类他打叉」），那时才算自动跟着口味走。但这个量级只够做范例注入，**不足以训练任何模型**——能达到的效果是「不再反复推你明确说过不喜欢的类型」，而不是「猜出你没说过的偏好」。

## 成本

| 项 | 用量 | 说明 |
|---|---|---|
| Claude API | 约 7 次调用/天 | 提炼分批 20 条/次（约 6 次）+ 评分 1 次 |
| Serper | 约 45 次/天 | 句式搜索 5 + 竞品核查最多 40；免费 2500 次一次性额度约撑 2 个月 |
| Resend | 1 封/天 | 免费档 |
| GitHub Actions | 约 8 分钟/天 | 私有仓库免费额度内 |

Serper 额度耗尽后调低 `competitor_check.max_searches_per_day` 或换 key。

## 已知限制与坑

- **Reddit 匿名 `.json` 接口全面 403**，换 UA 无效。现走两条免登录路径：定向版块用 `top.rss`（带 429 退避重试），句式搜索用 Serper 查 `site:reddit.com`。代价是**拿不到赞数和评论数**，所以这类条目跳过互动阈值筛选——`top/day` 和句式命中本身就是质量门槛，日报里如实显示「当日热帖」「句式命中」而不是伪造数字
- **发件人是共享的 `onboarding@resend.dev`，大概率进 Gmail 垃圾箱**。用 `in:anywhere 需求雷达` 搜，或建过滤器勾选「永不放入垃圾邮件」。治本方案是在 Resend 验证自有域名后改 `config.yaml` 的 `email.from`
- **模型响应可能带 thinking block**，解析时必须拼接所有 text block，不能取 `content[0]["text"]`
- **信号质量高度依赖句式搜索线**。HN 和 Google Trends 基本是科技新闻和名人热搜，很难出可做的生活类痛点——只跑这两条源时日报常只有 0–2 张卡
- **CI 失败时当次日报会丢失**（runner 销毁）。已加 push 重试，但如果失败在雷达步骤本身，需要本地 `--dry-run` 补跑

## 文件结构

```
needs-radar/
├── radar.py          # 单文件流水线，全部逻辑
├── config.yaml       # 信号源、阈值、LLM 参数、邮件
├── events.yaml       # 周期性事件日历（窗口期提醒）
├── requirements.txt  # requests / PyYAML / markdown
├── data/seen.db      # 去重 + 卡片留档
├── reports/          # 历史日报
├── HANDOFF.md        # 交接文档、v0.2 待办清单
└── README.md
```
