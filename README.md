# productidea

找产品点子的工作区。核心是 **needs-radar**——每天自动扫英文社区、用 LLM 提炼可 vibecode 变现的痛点、发中文日报到邮箱。

## 目录里有什么

| | 是什么 | 状态 |
|---|---|---|
| [needs-radar/](needs-radar/) | 需求雷达。GitHub Actions 定时脚本，每天抓 Reddit/HN/Google Trends → LLM 提炼痛点 → 真实搜索核查竞品 → 中文日报邮件 | ✅ **在跑**，每天自动出报 |
| [PRD-需求雷达.md](PRD-需求雷达.md) | needs-radar 的原始产品定义（做给谁、解决什么、为什么这么设计） | 📌 冻结，作为设计依据保留 |
| [english-hot-api/](english-hot-api/) | 英文热榜聚合 API（Node + Hono + Vercel），对标 DailyHotApi，四个源各一个路由 | ⏸ **休眠**，见下方说明 |

## 三者的关系

**PRD → needs-radar** 是同一件事的两个阶段：PRD 是当初的产品定义，needs-radar 是它的实现。PRD 不再更新，只在需要回溯"当初为什么这么设计"时看。

**english-hot-api 与 needs-radar 无依赖关系**，是两个独立项目。两者确实都抓 HN / Reddit / Google Trends，但形态完全不同——一个是给外部调用的 HTTP API，一个是自己跑完就发邮件的批处理管道。

**目前不建议把两者的抓取层合并**，原因是它们已经实质性分叉：Reddit 在 2026 年 7 月封掉了匿名 `.json` 接口（现在一律 403）。needs-radar 已改走免登录 RSS + 搜索 API 绕过，而 english-hot-api 的 `/reddit` 路由仍在调那个死接口，**该路由目前是坏的**。合并意味着要么让雷达迁就一个用不了的实现，要么先把 API 修好——共用代码的收益并不存在，反而给每天在跑的雷达引入一个新的失败点。

english-hot-api 自 2026-07-14 导入后未再改动。要么哪天有实际用途时修好 `/reddit` 路由（照搬 radar.py 的 RSS 方案即可），要么就当作归档项目留着。

## 文档分工

needs-radar 有三份文档，各管一段，别混：

- **[README](needs-radar/README.md)**：是什么、怎么跑、怎么部署、有哪些坑 —— 日常查这份
- **[HANDOFF](needs-radar/HANDOFF.md)**：进度、v0.2 待办清单、不能改的设计决策 —— 续跑前先读这份
- **[PRD](PRD-需求雷达.md)**：产品定义 —— 只在追溯设计意图时看

## 快速上手

```bash
cd needs-radar && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
cd needs-radar && .venv/bin/python radar.py --selftest
```

不联网、不花钱，打印一份样例日报即为正常。真跑起来要先填 `.env`，详见 [needs-radar/README.md](needs-radar/README.md)。

## 自动化

`.github/workflows/daily.yml`（在仓库根目录，Actions 只认这里）每天定时跑 needs-radar，跑完把当天日报和去重库提交回 main。**本地开发前先 `git pull --rebase`。**
