# Daily Stock Analysis 技术文档

- 文档版本：v1.0
- 生成日期：2026-02-13
- 适用代码基线：当前 `main` 工作区代码

---

## 1. 项目概述

`daily_stock_analysis` 是一个面向 A 股/港股/美股的智能分析系统，核心目标是将「多源行情 + 舆情搜索 + LLM 分析 + 多渠道推送 + 回测验证」串成可自动化运行的闭环。

系统支持三类典型运行方式：

1. CLI 单次/定时分析（`main.py`）
2. FastAPI 服务化运行（含前端管理界面）
3. Electron 桌面封装运行（本地启动后端并托管 UI）

核心能力：

1. 多数据源自动切换获取日线、实时行情、筹码和大盘数据
2. 多维舆情搜索（Bocha/Tavily/Brave/SerpAPI）
3. Gemini 优先、OpenAI 兼容回退的 AI 分析
4. 决策仪表盘生成与多渠道推送
5. 异步任务队列 + SSE 实时状态推送
6. 历史结果落库与回测评估

---

## 2. 总体架构

### 2.1 分层结构

```text
+-------------------------------------------------------------+
|                         Client Layer                        |
|  CLI(main.py) | Web(React) | Desktop(Electron) | BotStream |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                        Service Layer                         |
| FastAPI Endpoints | Task Queue | Analysis/History/Backtest  |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                         Core Layer                           |
| Pipeline | Analyzer | SearchService | Notification | Review  |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                     Data & Integration Layer                 |
| DataFetcherManager | Repositories | SQLAlchemy(SQLite)       |
+-------------------------------------------------------------+
```

### 2.2 关键目录

```text
daily_stock_analysis/
├── main.py                     # 主入口（CLI/服务/定时/回测）
├── api/                        # FastAPI
├── src/                        # 核心业务层
├── data_provider/              # 多数据源适配层
├── bot/                        # 命令与平台适配（Stream 为主）
├── apps/dsa-web/               # React + Vite 前端
├── apps/dsa-desktop/           # Electron 桌面壳
├── docker/                     # Dockerfile / compose
├── tests/                      # pytest 测试
└── .github/workflows/          # CI/CD 与定时任务
```

---

## 3. 运行模式与入口

主入口：`main.py`

支持参数（核心）：

1. `--stocks` 指定股票列表（覆盖配置）
2. `--dry-run` 仅抓取数据不做 AI 分析
3. `--schedule` 定时运行
4. `--market-review` 仅大盘复盘
5. `--serve` 启动 API 并执行分析
6. `--serve-only` 仅启动 API
7. `--webui` / `--webui-only`（兼容映射到 `--serve` / `--serve-only`）
8. `--backtest` 运行回测
9. `--no-notify` 不推送
10. `--single-notify` 每只股票分析后立即推送
11. `--no-context-snapshot` 不保存分析上下文快照

模式判定顺序（高优先级在前）：

1. 回测模式（`--backtest`）
2. 仅大盘复盘（`--market-review`）
3. 定时模式（`--schedule` 或 `SCHEDULE_ENABLED=true`）
4. 默认单次完整分析

---

## 4. 核心业务流程

### 4.1 个股分析主流程（`src/core/pipeline.py`）

```text
输入股票代码
  -> 获取并保存日线（断点续传）
  -> 获取实时行情（多源优先级 + 字段补全）
  -> 获取筹码分布（带熔断）
  -> 趋势分析（MA/量能/乖离率）
  -> 多维舆情搜索并存储 news_intel
  -> 组装增强上下文
  -> 调用 AI 分析（Gemini/OpenAI fallback）
  -> 保存 analysis_history（含可选 context_snapshot）
  -> 生成报告并推送
```

批量运行时：

1. 使用线程池并发（默认 `MAX_WORKERS=3`）
2. 股票数 `>=5` 时可预取实时行情缓存
3. 支持单股推送与汇总推送两种策略

### 4.2 API 异步任务流程

入口：`POST /api/v1/analysis/analyze`（`async_mode=true`）

```text
请求到达
  -> TaskQueue.submit_task
  -> 重复股票检查（正在分析则 409）
  -> 线程池执行 AnalysisService
  -> 广播 SSE 事件（created/started/completed/failed）
  -> 前端 useTaskStream 实时更新 UI
```

SSE 端点：`GET /api/v1/analysis/tasks/stream`

### 4.3 大盘复盘流程

核心：`src/core/market_review.py` + `src/market_analyzer.py`

1. 拉取指数、市场涨跌统计、板块排行
2. 检索市场新闻
3. AI 生成复盘（不可用时模板兜底）
4. 保存复盘文件并可推送

### 4.4 回测流程

核心：`src/services/backtest_service.py` + `src/core/backtest_engine.py`

1. 选择候选分析记录（按时间窗、强制标记）
2. 解析分析日期和止盈止损点位
3. 补齐缺失日线数据
4. 评估方向准确率、目标价命中、模拟收益
5. 保存 `backtest_results` 并重算 `backtest_summaries`

---

## 5. 配置体系

### 5.1 运行时配置（`src/config.py`）

- `Config` 为全局单例
- `setup_env()` 支持从 `.env` 加载并可 `override=True` 热重载
- `Config.validate()` 在启动时输出关键缺失告警
- `REALTIME_SOURCE_PRIORITY` 支持 Tushare token 自动注入优先级

默认重点：

1. 未配置 `STOCK_LIST` 时使用示例股票
2. `SCHEDULE_TIME` 默认 `18:00`
3. `report_type` 支持 `simple/full`
4. 支持 `SAVE_CONTEXT_SNAPSHOT` 控制上下文落库

### 5.2 系统配置管理 API（`.env` 在线修改）

模块：

1. `src/core/config_manager.py`：`.env` 原子读写与版本哈希
2. `src/core/config_registry.py`：字段 schema 与分组元数据
3. `src/services/system_config_service.py`：校验、冲突检测、重载

关键机制：

1. 乐观锁：`config_version` 不匹配返回 409
2. 敏感字段 mask token 占位保留
3. 字段级与跨字段校验（例如 Telegram token/chat_id 依赖）
4. 保存后可触发 `Config.reset_instance()` + `setup_env(override=True)`

---

## 6. 数据源架构与容错

核心组件：`data_provider/base.py::DataFetcherManager`

### 6.1 日线数据源优先级

默认初始化（动态）：

1. `EfinanceFetcher`（P0）
2. `AkshareFetcher`（P1）
3. `TushareFetcher`（P2，配置 token 时可提升）
4. `PytdxFetcher`（P2）
5. `BaostockFetcher`（P3）
6. `YfinanceFetcher`（P4）

策略：按优先级顺序尝试，失败自动切换，直到成功或全部失败。

### 6.2 实时行情策略

- 支持数据源优先级配置：`REALTIME_SOURCE_PRIORITY`
- 内置源：`efinance / akshare_em / akshare_sina / tencent / tushare`
- 美股优先走 `YfinanceFetcher`
- 首个成功结果作为主结果，后续源可补齐缺失字段（如 `volume_ratio/turnover_rate/pe/pb`）

### 6.3 筹码分布策略

- 受 `ENABLE_CHIP_DISTRIBUTION` 开关控制
- 源顺序：Akshare -> Tushare -> Efinance
- 使用独立熔断器（失败阈值、冷却恢复）

### 6.4 熔断与类型统一

`data_provider/realtime_types.py` 提供：

1. `UnifiedRealtimeQuote` 统一实时字段
2. `ChipDistribution` 统一筹码字段
3. `CircuitBreaker` 熔断状态机（closed/open/half_open）

---

## 7. AI 与情报模块

### 7.1 AI 分析器（`src/analyzer.py`）

`GeminiAnalyzer` 行为：

1. 优先 Gemini
2. Gemini 初始化失败或调用失败时回退 OpenAI 兼容 API
3. 统一重试 + 指数退避 + 可切换 fallback model
4. 输出 JSON 解析失败时，降级文本提取
5. 使用 `json_repair` 修复不规范 JSON

输出对象：`AnalysisResult`

- 包含评分、建议、趋势、风险、点位、dashboard 等结构化字段

### 7.2 搜索服务（`src/search_service.py`）

Provider 优先顺序：

1. Bocha
2. Tavily
3. Brave
4. SerpAPI

特性：

1. 多 key 轮询与错误计数
2. 多维情报搜索（latest/risk/earnings/industry/market）
3. 内存缓存（默认 TTL 600 秒）
4. 数据源失败时支持增强兜底搜索

---

## 8. 通知与报告

核心：`src/notification.py`

### 8.1 支持渠道

1. 企业微信
2. 飞书
3. Telegram
4. Email
5. Pushover
6. PushPlus
7. Server酱3
8. 自定义 Webhook
9. Discord
10. AstrBot
11. 会话上下文回复（Bot stream reply）

### 8.2 报告策略

1. `generate_single_stock_report`：单股精简报告
2. `generate_dashboard_report`：决策仪表盘完整报告
3. 企业微信走专用精简样式，其它渠道默认完整报告
4. 本地报告统一落盘到 `reports/`

---

## 9. 存储模型与数据字典

存储实现：`src/storage.py`（SQLAlchemy + SQLite）

数据库默认路径：`./data/stock_analysis.db`

### 9.1 `stock_daily`

用途：股票日线与技术指标。

关键字段：

1. `code`, `date`（唯一约束）
2. `open/high/low/close/volume/amount/pct_chg`
3. `ma5/ma10/ma20/volume_ratio`
4. `data_source`

### 9.2 `news_intel`

用途：搜索情报入库，支持 query 关联和去重。

关键字段：

1. `query_id`, `code`, `dimension`, `provider`
2. `title`, `snippet`, `url`（`url` 唯一约束）
3. 请求上下文字段（platform/user/chat/message/query）

### 9.3 `analysis_history`

用途：分析结果历史与详情页源数据。

关键字段：

1. `query_id`, `code`, `name`, `report_type`
2. `sentiment_score`, `operation_advice`, `trend_prediction`
3. `raw_result`, `news_content`, `context_snapshot`
4. 回测相关点位：`ideal_buy/secondary_buy/stop_loss/take_profit`

### 9.4 `backtest_results`

用途：单条历史分析对应的回测结果。

关键字段：

1. `analysis_history_id`, `code`, `analysis_date`
2. `eval_status`（completed/insufficient_data/error）
3. `direction_correct`, `outcome`, `stock_return_pct`
4. `hit_stop_loss/hit_take_profit/first_hit`
5. `simulated_return_pct`

### 9.5 `backtest_summaries`

用途：按 scope（overall/stock）聚合回测指标。

关键字段：

1. `scope`, `code`, `eval_window_days`, `engine_version`
2. 计数：`total/completed/insufficient/win/loss/neutral`
3. 比率：`direction_accuracy/win_rate/trigger_rate`
4. `advice_breakdown_json`, `diagnostics_json`

---

## 10. API 设计

根应用：`api/app.py`

- v1 前缀：`/api/v1`
- 健康检查：`GET /api/health`
- 前端静态资源存在时，根路由返回 SPA

### 10.1 Analysis

1. `POST /api/v1/analysis/analyze` 触发分析（同步/异步）
2. `GET /api/v1/analysis/tasks` 任务列表
3. `GET /api/v1/analysis/tasks/stream` SSE 任务流
4. `GET /api/v1/analysis/status/{task_id}` 查询任务状态

注意：请求支持 `stock_code` 与 `stock_codes`，当前实现只处理去重后的第一只股票。

### 10.2 History

1. `GET /api/v1/history` 历史分页
2. `GET /api/v1/history/{query_id}` 历史详情
3. `GET /api/v1/history/{query_id}/news` 关联新闻

### 10.3 Stocks

1. `GET /api/v1/stocks/{stock_code}/quote` 实时行情
2. `GET /api/v1/stocks/{stock_code}/history` 历史 K 线（当前仅 `daily`）

### 10.4 Backtest

1. `POST /api/v1/backtest/run` 触发回测
2. `GET /api/v1/backtest/results` 回测结果分页
3. `GET /api/v1/backtest/performance` 全局表现
4. `GET /api/v1/backtest/performance/{code}` 单股表现

### 10.5 System Config

1. `GET /api/v1/system/config`
2. `PUT /api/v1/system/config`
3. `POST /api/v1/system/config/validate`
4. `GET /api/v1/system/config/schema`

---

## 11. 前端架构（`apps/dsa-web`）

技术栈：React 19 + TypeScript + Vite + Zustand + Axios。

### 11.1 页面

1. 首页（分析输入、任务面板、历史列表、报告详情）
2. 回测页（触发回测、表现卡片、结果列表）
3. 设置页（动态 schema 渲染配置编辑器）

### 11.2 数据交互

1. REST 调用：`src/api/*`
2. SSE 实时任务流：`useTaskStream`
3. 配置编辑使用 optimistic version + 校验先行

### 11.3 构建输出

`vite.config.ts` 将前端打包到项目根 `static/`，由 FastAPI 直接托管。

---

## 12. 桌面端架构（`apps/dsa-desktop`）

技术栈：Electron。

运行逻辑（`main.js`）：

1. 初始化日志与用户目录
2. 生成/校验 `.env`
3. 查找可用端口
4. 启动后端（开发模式 `python main.py --serve-only`；打包模式执行内置二进制）
5. 轮询 `api/health` 就绪后加载 Web UI

桌面模式会强制关闭调度和 bot stream（由环境变量控制），以保证本地前台使用体验。

---

## 13. Bot 架构

模块：`bot/`

1. `models.py` 统一平台消息模型
2. `dispatcher.py` 命令分发 + 限流 + 权限
3. `commands/` 提供 `help/analyze/batch/market/status`
4. `platforms/` 目前以钉钉、飞书 Stream 为核心接入方式

说明：代码中存在 webhook handler 抽象，但当前 FastAPI v1 路由未直接暴露 bot webhook endpoint；生产接入主要依赖 Stream 模式后台线程。

---

## 14. 调度、日志与运维

### 14.1 调度

`src/scheduler.py` 基于 `schedule` 库按 `HH:MM` 每日执行，支持优雅退出信号处理。

### 14.2 日志

`src/logging_config.py` 三层输出：

1. 控制台
2. 常规日志（INFO，轮转）
3. 调试日志（DEBUG，轮转）

默认目录：`./logs`

### 14.3 报告与数据目录

1. `data/`：SQLite 数据库
2. `logs/`：运行日志
3. `reports/`：分析与复盘输出

---

## 15. 部署与 CI/CD

### 15.1 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
```

### 15.2 Docker

- 镜像：`docker/Dockerfile`（多阶段构建前端 + Python 后端）
- 编排：`docker/docker-compose.yml`
- API 服务模式示例：

```bash
docker-compose -f docker/docker-compose.yml up -d server
```

### 15.3 GitHub Workflows（关键）

1. `daily_analysis.yml`：工作日定时分析 + 手动触发
2. `ci.yml`：PR 语法、静态检查、Docker 构建
3. `pr-review.yml`：安全检查 + 自动审查流程
4. `docker-publish.yml`：推送 GHCR 镜像
5. `ghcr-dockerhub.yml`：手动多架构镜像发布
6. `auto-tag.yml`：基于提交自动打版本标签

---

## 16. 测试与质量保障

### 16.1 自动化测试

- `tests/` 包含历史、回测、存储、系统配置 API/Service 等测试
- 典型测试入口：

```bash
pytest -v
```

### 16.2 快速脚本

`test.sh` 覆盖语法检查、数据源识别、场景运行（A/HK/US、dry-run、market）。

### 16.3 代码规范

1. `black`（line-length=120）
2. `isort`
3. `flake8`（配置见 `setup.cfg`）

---

## 17. 已识别的技术约束

1. `/api/v1/analysis/analyze` 目前仅处理第一只股票（即便传入 `stock_codes`）。
2. API 当前无鉴权与租户隔离，默认适合内网或单用户场景。
3. SQLite 适合轻量单实例，横向扩展需迁移数据库方案。
4. 部分外部数据源和搜索接口存在配额/稳定性波动。
5. Webhook bot 路由未在 v1 API 中直接暴露，Stream 模式是当前主链路。

---

## 18. 扩展开发指南

### 18.1 新增数据源

1. 在 `data_provider/` 实现 `BaseFetcher` 子类
2. 实现 `_fetch_raw_data` 与 `_normalize_data`
3. 设置 `priority`
4. 在 `DataFetcherManager._init_default_fetchers()` 注册

### 18.2 新增通知渠道

1. 在 `NotificationChannel` 增加枚举
2. 在 `NotificationService` 增加 `send_to_xxx`
3. 在 `get_available_channels` 与 `send` 分发逻辑接入

### 18.3 新增 API 模块

1. 在 `api/v1/endpoints` 增加 endpoint
2. 在 `api/v1/schemas` 定义请求响应模型
3. 在 `api/v1/router.py` 注册路由

### 18.4 新增系统配置项

1. `src/config.py` 增加字段与加载逻辑
2. `src/core/config_registry.py` 注册 schema
3. 必要时在 `SystemConfigService` 增加跨字段校验

---

## 19. 最小可用配置建议

最低可运行建议：

1. `STOCK_LIST`
2. `GEMINI_API_KEY` 或 `OPENAI_API_KEY`
3. 至少一个通知渠道
4. 推荐至少一个搜索 API key（Tavily/Bocha）

若只做本地 API 调试，可暂时关闭推送并使用 `--no-notify`。

---

## 20. 参考文件清单

核心入口与流程：

1. `main.py`
2. `src/core/pipeline.py`
3. `src/analyzer.py`
4. `src/search_service.py`
5. `src/notification.py`
6. `src/storage.py`
7. `src/services/task_queue.py`

API 与前端：

1. `api/app.py`
2. `api/v1/router.py`
3. `api/v1/endpoints/*.py`
4. `apps/dsa-web/src/pages/*.tsx`

配置与部署：

1. `src/config.py`
2. `src/core/config_manager.py`
3. `src/core/config_registry.py`
4. `docker/Dockerfile`
5. `docker/docker-compose.yml`
6. `.github/workflows/*.yml`

