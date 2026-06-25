# Competitor AI Workflow

Competitor AI is a local workflow for product managers, market analysts, and engineering decision makers. It connects brief input, competitor discovery, per-product web research, report synthesis, quality review, questionnaires, and reusable Skill Wiki output into one browser-driven workflow.

## Features

- Web workspace: create analysis jobs, watch runtime logs, select competitors, and preview Markdown reports.
- Competitor discovery and crawling: search related products, extract web page text, and optionally use Playwright or Crawl4AI for dynamic pages.
- Report Agent: merge per-product research into structured competitor reports, evidence cards, comparison tables, and final summaries.
- Quality Agent: inspect report structure, evidence, logic, and recommendations, then generate QA reports and issues.
- Questionnaire center: generate competitor research questionnaires, simulate test responses, and analyze response files.
- Skill Wiki: turn generated reports into reusable searchable knowledge files and chat with them.

## Requirements

Recommended environment:

- Linux server such as Ubuntu, Debian, Alibaba Cloud Linux, CentOS, or RHEL-compatible distributions
- Python 3.10 or later
- python3, pip3, and venv
- Network access to the selected LLM and search APIs

Common environment variables:

```bash
# LLM provider: 0 = Doubao/Volcengine Ark, 1 = SiliconFlow, 2 = Xiaomi MiMo
export LLM_PROVIDER="0"
export LLM0_API_KEY="your-ark-api-key"
export LLM0_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
export LLM0_MODEL="your-model"

# Search APIs
export BOCHA_API_KEY="your-bocha-api-key"
export GOOGLE_API_KEY="your-google-api-key"
export GOOGLE_CX_ID="your-google-cx-id"
```

You can also create a `.env` file in the repository root or enter these values in the web Settings page.

## Install

```bash
chmod +x start_competitor_ai.sh
./start_competitor_ai.sh install -y
```

For the interactive menu:

```bash
./start_competitor_ai.sh
```

Choose option `[1] Install/update Python environment`. The script creates or reuses `.venv`, installs dependencies, and initializes Playwright Chromium and Crawl4AI.

## Start

```bash
./start_competitor_ai.sh start 8000
```

Or start the backend directly:

```bash
source .local_env.sh
python3 backend/server.py 8000
```

Then open:

```text
http://SERVER_IP:8000
```

Main pages:

- Workspace: create competitor analysis jobs and configure search, model, QA, and existing materials.
- Report Library: preview Markdown reports under `reports/`.
- Questionnaire Center: generate questionnaires, simulate responses, and analyze response data.
- Report Skill: build and inspect Skill Wiki files derived from reports.
- QA & Issues: review problems found by the Quality Agent.
- Settings: configure model, search, and workflow parameters.

## CLI Examples

```bash
python3 run_similar_product_reports_with_new_analyze_quality.py "AI IDE competitor analysis"
python3 generate_competitor_questionnaire.py
python3 analyze_questionnaire_results.py questionnaires/xxx.jsonl questionnaires/xxx_responses.jsonl "Product or competitor direction"
python3 -m agent.quality_agent.cli reports/your_report.md --save
```

## Directory Map

| Path | Purpose |
| --- | --- |
| `backend/` | Web backend for jobs, reports, questionnaires, Skill Wiki, and QA APIs. |
| `frontend/` | Web pages, styles, and browser interaction logic. |
| `extracted_core/` | Search, crawling, LLM client, and product positioning utilities. |
| `report_agent/` | Report synthesis, evidence structuring, table completion, and strategy recommendations. |
| `agent/quality_agent/` | Report QA agent, inspectors, scoring, feedback, and export logic. |
| `workflows/` | Workflow orchestration, including the QA loop. |
| `skill_wiki_builder/` | Builds Skill Wiki files from reports and supports wiki-based Q&A. |
| `questionnaires/` | Questionnaire JSONL, simulated responses, CSV exports, and analysis reports. |
| `reports/` | Generated product reports, final reports, QA output, and Skill Wiki files. |
| `logs/` | Runtime logs and Quality Agent traces. |

Local environment files such as `.env`, `.local_env.sh`, `.local_python_path.txt`, and `.venv/` are intentionally ignored by git.
