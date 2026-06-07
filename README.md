# Competitor AI 竞品分析工作流

Competitor AI 是一个面向产品经理、市场分析和研发决策场景的本地竞品分析工作流。项目通过 Web 控制台把“需求输入 -> 竞品发现 -> 单品资料抓取与分析 -> 综合报告生成 -> 报告质检 -> 问卷与知识库沉淀”串成一条可操作的流程，最终输出 Markdown、JSON、CSV 等本地文件。

## 功能概览

- Web 工作台：在浏览器中创建分析任务、查看运行日志、选择竞品、预览 Markdown 报告。
- 竞品发现与资料抓取：支持搜索相关产品、抓取网页正文，并可用 Playwright / Crawl4AI 增强动态网页解析。
- Report Agent：把多个单品分析结果整合为结构化竞品报告、证据卡、对比表和最终综合报告。
- Quality Agent：对报告结构、证据、逻辑、建议等维度做质量检查，并生成质检报告。
- 问卷中心：生成竞品调研问卷、模拟问卷填写、分析问卷结果。
- Skill Wiki：从已生成报告中沉淀可复用的知识文件、表格、玩法指南和参考材料。

## 依赖环境

推荐使用 Docker 启动，宿主机只需要：

- Docker Desktop 或 Docker Engine
- Docker Compose v2，命令为 `docker compose`
- 可访问大模型和搜索服务的网络环境

容器内运行环境：

- Python 3.11
- Playwright Chromium 浏览器依赖
- Python 依赖见 [requirements.txt](requirements.txt)

核心 Python 包包括：

```text
requests
openai
duckduckgo-search
trafilatura
beautifulsoup4
lxml
playwright
crawl4ai
python-dotenv
tqdm
pydantic
python-dateutil
```

可选开发依赖：

```text
pytest
pytest-asyncio
black
flake8
mypy
langchain-openai
```

## 环境变量

推荐在仓库根目录创建 `.env` 文件，Docker Compose 会读取该文件并注入到容器。至少需要配置当前大模型供应商对应的 API Key，以及搜索服务 Key。

常用 `.env` 示例：

```env
# Web 服务
WEB_PORT=8000

# 大模型供应商：0 = 豆包/火山 Ark，1 = SiliconFlow，2 = 小米 MiMo
LLM_PROVIDER=0

# 供应商 0：豆包/火山 Ark
LLM0_API_KEY=your-ark-api-key
LLM0_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM0_MODEL=your-ark-model

# 供应商 1：SiliconFlow 或其他 OpenAI 兼容服务
LLM1_API_KEY=your-provider1-api-key
LLM1_BASE_URL=https://api.siliconflow.cn/v1/chat/completions
LLM1_MODEL=deepseek-ai/DeepSeek-V4-Flash

# 供应商 2：小米 MiMo
LLM2_API_KEY=your-mimo-api-key
LLM2_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
LLM2_MODEL=mimo-v2.5-pro

# Report Agent 可单独覆盖模型；留空则跟随上面的 LLM_PROVIDER 配置
REPORT_LLM_API_KEY=
REPORT_LLM_BASE_URL=
REPORT_LLM_MODEL=

# 搜索配置：bocha / google / duckduckgo
SEARCH_SOURCE=bocha
BOCHA_API_KEY=your-bocha-api-key
GOOGLE_API_KEY=
GOOGLE_CX_ID=

# 抓取后端：0 = requests/trafilatura，1 = Playwright，2 = Crawl4AI
SEARCH_BACKEND=1

# 如需代理，改为 1 并填写代理地址
USE_NETWORK_PROXY=0
HTTP_PROXY=
HTTPS_PROXY=
ALL_PROXY=
```

`ARK_API_KEY`、`LLM_API_KEY`、`MIMO_API_KEY` 可作为兼容写法使用，但推荐优先使用 `LLM0_API_KEY`、`LLM1_API_KEY`、`LLM2_API_KEY`。

也可以运行项目后在 Web 控制台的配置页填写运行参数。

## 安装步骤

首次启动会自动构建镜像、安装 Python 依赖，并安装 Playwright Chromium：

```bash
docker compose build
```

如果修改了 [requirements.txt](requirements.txt) 或 [Dockerfile](Dockerfile)，重新构建：

```bash
docker compose build --no-cache
```

## 启动步骤

在仓库根目录执行：

```bash
docker compose up -d
```

启动后访问：

```text
http://127.0.0.1:8000
```

如果 `.env` 中配置了 `WEB_PORT=9000`，则访问：

```text
http://127.0.0.1:9000
```

常用 Docker 命令：

```bash
# 查看容器状态
docker compose ps

# 查看日志
docker compose logs -f competitor-ai

# 停止服务
docker compose down
```

容器会把运行产物写回宿主机：

- `./reports:/app/reports`
- `./questionnaires:/app/questionnaires`

Web 控制台主要页面包括：

- 工作台：创建竞品分析任务，配置搜索、模型、质检和已有材料。
- 报告库：查看和预览 `reports/` 下的 Markdown 报告。
- 问卷中心：生成问卷、模拟回答、分析问卷数据。
- 报告 Skill：构建和查看由报告沉淀出的 Skill Wiki。
- 质检 Issue：查看 Quality Agent 发现的问题。
- 配置：填写模型、搜索和流程参数。

## 目录结构

| 路径 | 说明打*号的是有独立子项目readme的|
| --- | --- |
| [backend/](backend/) | *Web 后端，提供任务、报告、问卷、Skill Wiki 和质检接口。 |
| [frontend/](frontend/) | Web 前端页面、样式和交互逻辑。 |
| [extracted_core/](extracted_core/) | *搜索、抓取、LLM 客户端和产品定位分析核心能力。 |
| [report_agent/](report_agent/) | *综合报告生成 Agent、证据结构化、表格补全和策略建议。 |
| [agent/quality_agent/](agent/quality_agent/) | *报告质量检查 Agent、检查器、评分、反馈和导出逻辑。 |
| [workflows/](workflows/) | 质量闭环等流程编排代码。 |
| [skill_wiki_builder/](skill_wiki_builder/README.md) | *从报告构建 Skill Wiki，并支持基于 Wiki 问答。 |
| [questionnaires/](questionnaires/) | 问卷 JSONL、模拟回答 CSV/JSONL、问卷分析报告。 |
| [reports/](reports/) | 运行生成的单品报告、综合报告、质检结果和 Skill Wiki。 |
| [logs/](logs/) | 运行日志和 Quality Agent 追踪记录。 |
| [run_similar_product_reports.py](run_similar_product_reports.py) | 早期竞品报告主流程。 |
| [run_similar_product_reports_with_new_analyze.py](run_similar_product_reports_with_new_analyze.py) | 新版分析流程。 |
| [run_similar_product_reports_with_new_analyze_quality.py](run_similar_product_reports_with_new_analyze_quality.py) | 带 Report Agent 和 Quality Agent 的主流程。 |
| [generate_competitor_questionnaire.py](generate_competitor_questionnaire.py) | 竞品调研问卷生成、模拟和分析。 |
| [analyze_questionnaire_results.py](analyze_questionnaire_results.py) | 已有问卷结果分析入口。 |

## 输出文件

主要输出位于 `reports/`：

- `*_FINAL_COMPARISON.md`：最终综合竞品对比报告。
- `*_REPORT_AGENT_ANALYSIS.md`：Report Agent 生成的结构化分析。
- `*_REPORT_AGENT_EVIDENCE_CARDS.md`：证据卡。
- `*_REPORT_AGENT_PACKAGE.json`：结构化报告包。
- `quality_workflow/`：质检报告、反馈载荷和迭代结果。
- `report_agent_tables/`：报告生成过程中导出的对比表 CSV/JSONL。
- `skill_wikis/`：由报告沉淀的 Skill Wiki 文件夹。

问卷相关输出位于 `questionnaires/`，包括问卷题目、模拟回答和问卷分析报告。

## 注意事项

- 首次构建 Docker 镜像时会安装 Python 依赖和 Playwright Chromium 浏览器依赖。
- 如果抓取动态网页失败，可以在 Web 控制台或环境变量中切换抓取后端。
- 运行完整竞品分析会调用大模型和搜索服务，请确认 API Key、额度和网络可用。
- 报告、日志、问卷结果属于运行产物，默认不会提交到 Git。
