import os
import re
from agent.state import OverallState
from agent.configuration import Configuration

# Unified summaries separator and builder
SUMMARY_SEPARATOR = "\n\n---\n\n"

def _prepare_summaries(results: list[str] | None, max_items: int = 10, max_chars: int = 40000) -> str:
    """Build a normalized, light deduped and size-capped summaries string.

    - Filters non-strings
    - Deduplicates by normalized lowercase + collapsed whitespace
    - Caps by items count and total characters
    - Joins with a unified separator
    """
    if not results:
        return "No research results available"
    # 过滤与轻量去重
    safe = [s for s in results if isinstance(s, str)]
    seen: set[str] = set()
    dedup: list[str] = []
    for s in safe:
        try:
            norm = " ".join(s.lower().split())
        except Exception:
            norm = str(s).lower()
        if norm in seen:
            continue
        seen.add(norm)
        dedup.append(s)

    # 按预算裁剪
    out: list[str] = []
    total = 0
    for s in dedup:
        if len(out) >= max_items:
            break
        sep_len = len(SUMMARY_SEPARATOR) if out else 0
        if total + sep_len + len(s) > max_chars:
            remaining = max_chars - total - sep_len
            if remaining > 0:
                out.append(s[:remaining])
            break
        out.append(s)
        total += sep_len + len(s)
    return SUMMARY_SEPARATOR.join(out) if out else "No research results available"

def _contains_cjk(text: str) -> bool:
    """Lightweight detection for CJK characters to decide if translation is needed."""
    try:
        return bool(re.search(r"[\u4e00-\u9fff]", text or ""))
    except Exception:
        return False

def _extract_cjk_terms(text: str) -> list[str]:
    """Extract unique CJK substrings (length>=2) to preserve local entity names in queries."""
    try:
        terms = re.findall(r"[\u4e00-\u9fff]{2,}", text or "")
        out: list[str] = []
        seen: set[str] = set()
        for t in terms:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out
    except Exception:
        return []

def _translate_to_english(text: str, model_name: str) -> str:
    """Translate Chinese query to concise English using the same LLM family. Fallback to original on failure."""
    try:
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.0,
            max_retries=2,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
        prompt = (
            "Translate the following Chinese search query into concise English suitable for web search. （Keep the Local NER name or terminology）"
            "Only output the translation without quotes.\n\n" + (text or "")
        )
        res = llm.invoke(prompt)
        translated = (getattr(res, "content", "") or "").strip()
        return translated
    except Exception:
        try:
            logger.exception("[translation] failed to translate query; using original")
        except Exception:
            pass
        return ""

def _repair_json_format(raw_content: str, prev_objectives_progress: dict = None) -> dict | None:
    """Attempt to repair common JSON format issues in LLM output."""
    import json
    import re
    
    try:
        # First, try direct JSON parsing
        parsed = json.loads(raw_content)
        # Ensure objectives_progress is preserved if missing
        if 'objectives_progress' not in parsed and prev_objectives_progress:
            parsed['objectives_progress'] = prev_objectives_progress.copy()
            logger.info("[_repair_json_format] Preserved previous objectives_progress: %d objectives", len(prev_objectives_progress))
        return parsed
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_content, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            # Ensure objectives_progress is preserved if missing
            if 'objectives_progress' not in parsed and prev_objectives_progress:
                parsed['objectives_progress'] = prev_objectives_progress.copy()
                logger.info("[_repair_json_format] Preserved previous objectives_progress from markdown: %d objectives", len(prev_objectives_progress))
            return parsed
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON-like content
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_content, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            # Fix common issues
            # Fix unescaped quotes in strings
            json_str = re.sub(r'(?<!\\)"([^"]*)"([^"]*)"([^"]*)"(?=\s*[,}])', r'"\1\"\2\"\3"', json_str)
            # Fix trailing commas (more comprehensive pattern)
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            json_str = re.sub(r',(\s*,)', r'\1', json_str)  # Remove duplicate commas
            # Fix single quotes
            json_str = json_str.replace("'", '"')
            # Remove extra spaces and newlines that might cause issues
            json_str = re.sub(r'\s+', ' ', json_str).strip()
            
            parsed = json.loads(json_str)
            
            # Validate required fields for Reflection
            required_fields = ['is_sufficient', 'knowledge_gap', 'follow_up_queries']
            if all(field in parsed for field in required_fields):
                # Set defaults for missing optional fields, preserving previous objectives_progress
                current_objectives = parsed.get('objectives_progress', {})
                if not current_objectives and prev_objectives_progress:
                    # If current is empty/missing but we have previous progress, preserve it
                    parsed['objectives_progress'] = prev_objectives_progress.copy()
                    logger.info("[_repair_json_format] Preserved previous objectives_progress in repair: %d objectives", len(prev_objectives_progress))
                elif not current_objectives:
                    # No current and no previous
                    parsed['objectives_progress'] = {}
                # If current_objectives exists and is not empty, keep it as is
                parsed.setdefault('overall_completion', 0.0)
                return parsed
                
        except json.JSONDecodeError:
            pass
    
    return None

# 重点方法 Effort utilities
def _infer_effort(state: OverallState, configurable: Configuration) -> str:
    """Infer effort level from state; prefer explicit configuration or state['effort'].

    Priority order:
    1. configurable.effort (from frontend/config)
    2. state['effort'] (from runtime state)
    3. Fallback based on initial_search_query_count
    """
    # Priority 1: Configuration effort (from frontend)
    try:
        if configurable.effort and configurable.effort.lower() in {"low", "medium", "high"}:
            return configurable.effort.lower()
    except Exception:
        pass

    # Priority 2: State effort (runtime override)
    try:
        explicit = (state.get("effort") or "").lower()
        if explicit in {"low", "medium", "high"}:
            return explicit
    except Exception:
        pass

    # Priority 3: Default fallback (since effort now controls query count directly)
    return "medium"

def _effort_completion_threshold(configurable: Configuration, effort: str) -> float:
    if effort == "high":
        return float(configurable.effort_high_completion_threshold)
    if effort == "medium":
        return float(configurable.effort_medium_completion_threshold)
    return float(configurable.effort_low_completion_threshold)

def _effort_max_parallel(configurable: Configuration, effort: str) -> int:
    base = int(configurable.max_parallel_queries)
    try:
        if effort == "high":
            return int(configurable.effort_high_max_parallel_queries)
        if effort == "medium":
            return int(configurable.effort_medium_max_parallel_queries)
        if effort == "low":
            return int(configurable.effort_low_max_parallel_queries)
    except Exception:
        pass
    return max(1, base)
