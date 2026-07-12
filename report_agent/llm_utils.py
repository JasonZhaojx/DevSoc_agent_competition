"""写作 Agent 的 LLM 工具函数。

All云端模型调用都集中在这里。业务节点只调用 `call_json_llm`，拿不到合法
JSON 时自动得到 None 并进入本地 fallback，因此 offline 测试不会触发网络。
"""

from __future__ import annotations

OUTPUT_LANGUAGE = "English"
ENGLISH_OUTPUT_POLICY = """
Output language policy:
- Write every user-facing field in English only.
- Do not use Chinese or any other non-English language in reports, summaries,
  table cells, labels, recommendations, questionnaire items, or file titles.
- If the input or source material is non-English, translate its meaning into
  English before returning it.
- Keep proper nouns and brand names unchanged only when translation would be
  incorrect.
""".strip()

import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

try:  # Package import.
    from .models import WritingAgentConfig
except ImportError:  # Direct script import from this directory.
    from report_agent.models import WritingAgentConfig


def can_use_llm(config: WritingAgentConfig) -> bool:
    """只有显式开启并且 key/base/model 都存在时才允许调用 LLM。"""

    return bool(
        config.use_llm
        and config.llm_api_key
        and config.llm_base_url
        and config.llm_model
    )


def parse_json_payload(content: str) -> Optional[Any]:
    """从模型输出中解析 JSON，兼容 ```json fenced block。"""

    if not content:
        return None


def contains_cjk(text: Any) -> bool:
    """Return True when text contains Chinese/Japanese/Korean ideographs."""

    return bool(re.search(r"[\u3400-\u9fff\uf900-\ufaff]", str(text or "")))


def english_system_prompt(system_prompt: str) -> str:
    """Add the project-wide English-only policy to every LLM system prompt."""

    prompt = str(system_prompt or "").strip()
    if ENGLISH_OUTPUT_POLICY in prompt:
        return prompt
    return f"{ENGLISH_OUTPUT_POLICY}\n\n{prompt}".strip()


def safe_ascii_filename(value: Any, fallback: str = "report", max_chars: int = 80) -> str:
    """Build an ASCII-only filename stem from user/model supplied text."""

    text = re.sub(r"[\u3400-\u9fff\uf900-\ufaff]+", "", str(value or ""))
    text = re.sub(r"[^0-9A-Za-z._-]+", "_", text).strip("._-")
    return text[:max_chars] or fallback

    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start_positions = [
        pos for pos in (cleaned.find("{"), cleaned.find("[")) if pos >= 0
    ]
    if not start_positions:
        return None
    start = min(start_positions)
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if end < start:
        return None

    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _load_chat_content():
    """加载共享 LLM client。

    优先走正常包导入；If包导入因路径issue失败，则直接按文件路径加载
    `extracted_core/llm_client.py`，保证 report_agent 的独立测试可运行。
    """

    try:
        from extracted_core.llm_client import chat_content

        return chat_content
    except Exception:
        llm_path = (
            Path(__file__).resolve().parents[1]
            / "extracted_core"
            / "llm_client.py"
        )
        spec = importlib.util.spec_from_file_location(
            "_report_agent_llm_client", llm_path
        )
        if not spec or not spec.loader:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.chat_content


def call_json_llm(
    *,
    config: WritingAgentConfig,
    system_prompt: str,
    user_prompt: str,
) -> Optional[Any]:
    """调用配置的 LLM 并解析 JSON。

    任何异常都返回 None，由各业务节点 fallback；这样不会因为模型波动阻塞整个
    报告链路。
    """

    if not can_use_llm(config):
        return None

    try:
        chat_content = _load_chat_content()
        content = chat_content(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
            messages=[
                {"role": "system", "content": english_system_prompt(system_prompt)},
                {"role": "user", "content": user_prompt},
            ],
            temperature=config.temperature,
            max_tokens=config.max_tokens if config.max_tokens > 0 else None,
            timeout=config.llm_timeout,
        )
        return parse_json_payload(content or "")
    except Exception as exc:
        if config.verbose and config.progress_printer:
            config.progress_printer(
                f"[writing-agent] LLM JSON call failed, using fallback: {exc}"
            )
        return None


def rewrite_text_to_english(text: str, config: WritingAgentConfig) -> str:
    """Translate generated user-facing text to English when an LLM is available."""

    original = str(text or "")
    if not original.strip() or not can_use_llm(config):
        return original

    try:
        chat_content = _load_chat_content()
        content = chat_content(
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
            model=config.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": english_system_prompt(
                        "You rewrite content into English only and preserve Markdown/JSON structure."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Rewrite the following content into English only. "
                        "Preserve headings, bullets, tables, IDs, URLs, and structure. "
                        "Return only the rewritten content.\n\n"
                        f"{original}"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=config.max_tokens if config.max_tokens > 0 else None,
            timeout=config.llm_timeout,
        )
        rewritten = str(content or "").replace("```markdown", "").replace("```", "").strip()
        if rewritten and not contains_cjk(rewritten):
            return rewritten + ("\n" if original.endswith("\n") else "")
    except Exception as exc:
        if config.verbose and config.progress_printer:
            config.progress_printer(
                f"[writing-agent] English rewrite failed, keeping original text: {exc}"
            )
    return original


def clean_text(value: Any, max_chars: int = 0) -> str:
    """统一做空值、空白和长度处理。"""

    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    no_truncate = os.getenv("REPORT_AGENT_NO_TRUNCATE", "1").strip().lower()
    truncate_enabled = no_truncate in {"0", "false", "no", "off"}
    if truncate_enabled and max_chars and len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def clamp_confidence(value: Any, default: float = 0.7) -> float:
    """把置信度限制在 0-1 范围内。"""

    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


def valid_ids(values: Any, allowed: set[str]) -> list[str]:
    """过滤出当前上下文允许的 id，并保持原顺序去重。"""

    if not isinstance(values, list):
        return []
    ids: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if item in allowed and item not in ids:
            ids.append(item)
    return ids
