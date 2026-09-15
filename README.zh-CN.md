<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="Needs Radar scans public discussions, verifies competition, and emails a daily shortlist of buildable product pains">
</p>

<p align="center"><a href="./README.md">English</a> · <strong>中文</strong></p>

每个产品点子在你真去搜之前，听起来都像没人做过。**Needs Radar** 在公开讨论里找出具体痛点，数清已经占着搜索结果的竞品，然后每天把清单发到你邮箱。

```bash
git clone https://github.com/shenjiayi692-maker/productidea && cd productidea/needs-radar && python3 -m venv .venv && .venv/bin/pip install -qr requirements.txt && .venv/bin/python radar.py --selftest
```

这跑的是离线自检：不联网、不花 API 钱、不发邮件。它会打印一份样例日报，让你在配置任何东西之前先看到产出长什么样。

**Productidea** 是围绕 [Needs Radar](./needs-radar/) 的工作区：一条定时研究流水线，扫描英文社区寻找具体的痛点，核查竞品是否已经占满搜索结果，然后把一份简明的中文机会日报发到邮箱。

它不是 dashboard，也不是 SaaS 应用。它的界面就是那封每日邮件，运行时是 GitHub Actions。

## 五分钟看懂今天的信号

当前上线的流水线会：

1. 采集定向的 Reddit RSS、基于短语的 Reddit 搜索、Hacker News、Google Trends，以及一份手工维护的事件日历。
2. 应用时效性、互动量和 SQLite 去重规则。
3. 用 LLM 提炼出具体痛点、受众、证据，以及一个小的产品形态。
4. 拿建议的关键词去搜索，数出真实存在的竞品数量。
5. 用这些搜索结果给可建造性、可变现性和市场空白打分。
6. 标记 90 天内重复出现的痛点。
7. 写出 [`reports/YYYY-MM-DD.md`](./needs-radar/reports/)，并把同一份清单发邮件。

**竞品核查是核心护栏。** 一个看起来合理的点子，在 LLM 眼里可能是一片空白，而搜索结果第一页已经摆满了专门的工具和官方计算器；Needs Radar 在给出空白分之前，先把这份证据摆出来。

## 跑离线自检

```bash
cd needs-radar
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python radar.py --selftest
```

这条命令在不联网、不花 API 费用、不发邮件、也不改动已跟踪的去重库的前提下，走完渲染路径。

若要跑实时模式，复制 [`.env.example`](./needs-radar/.env.example)，并阅读完整的 [Needs Radar 指南](./needs-radar/README.md)：

```bash
.venv/bin/python radar.py --no-llm   # 只采集和预筛
.venv/bin/python radar.py --dry-run  # 完整分析、写报告、不发邮件
.venv/bin/python radar.py            # 完整的定时行为
```

## 工作区地图

| 路径 | 用途 | 状态 |
| --- | --- | --- |
| [`needs-radar/`](./needs-radar/) | Python 批处理流水线、配置、数据库和每日报告 | 在跑，每天定时 |
| [`PRD-需求雷达.md`](./PRD-需求雷达.md) | 冻结的原始产品定义与设计依据 | 参考 |
| [`english-hot-api/`](./english-hot-api/) | 独立的 Hono / Vercel 热榜聚合实验 | 休眠 |

`english-hot-api` 不是 Needs Radar 的依赖。它那条匿名 Reddit JSON 路由目前是坏的，因为该接口返回 403；在跑的雷达改用 RSS 和搜索 API。除非有意复活这个休眠的 API，否则两边的实现应当保持分离。

## 配置与成本控制

[`needs-radar/config.yaml`](./needs-radar/config.yaml) 定义数据源、阈值、模型批大小、报告长度、邮件设置，以及每日搜索次数上限。[`events.yaml`](./needs-radar/events.yaml) 记录可预期的时间窗口，比如申请季、报税季和购物季。

实时运行需要 Anthropic 和 Resend 的 key。短语搜索和竞品核查推荐用 Serper，SerpAPI 作为兜底。Reddit OAuth 是可选的。

当前配置每天大约消耗七次模型调用、最多约 45 次搜索调用、一封邮件，以及大约八分钟的 GitHub Actions 时长。这些是观察到的运行数据，不是服务保证。

## 关于自动化

[`.github/workflows/daily.yml`](./.github/workflows/daily.yml) 在 UTC 06:00 运行，并把新报告和去重数据库提交回 `main`。GitHub 的定时任务可能比标称时间晚一些启动。

因为机器人每天都会改动 `main`，本地开发前先 rebase 拉取：

```bash
git pull --rebase
```

运行层面的决策和已知限制见 [`needs-radar/HANDOFF.md`](./needs-radar/HANDOFF.md)。

## 许可

MIT,见 [LICENSE](./LICENSE)。
