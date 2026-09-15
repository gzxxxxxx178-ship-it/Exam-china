# Exam Finding

个人使用的公职、事业单位和国企招聘信息聚合系统。当前完成 M0：统一数据模型、行政区划筛选、来源注册、数据库初始化和查询 API。

## 启动

```bash
uv sync
uv run python -m app.cli init-db
uv run uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000/docs> 查看接口。

## 当前接口

- `GET /health`：服务和数据库状态；
- `GET /api/divisions`：行政区划级联数据；
- `GET /api/positions`：按省、市、类别、状态和关键词筛选岗位；
- `GET /api/batches`：招聘批次列表；
- `GET /api/batches/{id}`：批次详情和考试时间线；
- `GET /api/sources/coverage`：来源接入和采集健康状态。
- `GET /api/crawl-runs`：采集运行记录与失败原因。

`config/divisions.csv` 目前只包含用于验证层级筛选的少量样例。接入真实来源前，应从民政部门或其他权威发布渠道导入完整且带版本日期的 GB/T 2260 数据，禁止把非权威网络列表直接标记为官方区划数据。

数据库结构由 Alembic 管理；`init-db` 会先升级到最新结构，再幂等导入行政区划样例和来源配置。

当前关键词查询是字段级匹配；中文二元词 FTS5 索引将在真实岗位解析流程接入后建立，避免先生成与最终规范化字段不一致的索引。

## M1 采集

先初始化配置，再进行只读试跑：

```bash
uv run python -m app.cli init-db
uv run python -m app.cli run-source national_civil_service --max-items 3 --dry-run
```

确认解析正常后写入本地数据库：

```bash
uv run python -m app.cli run-source national_civil_service --max-items 20
```

国家公务员局职位附件的网页下载流程带图形验证码，系统不会绕过该限制。现阶段自动采集公开公告正文和考试时间线；职位表通过后续的本地 XLSX 导入功能接入。

## 测试

```bash
uv run pytest
```

完整设计见 [ARCHITECTURE.md](ARCHITECTURE.md)。
