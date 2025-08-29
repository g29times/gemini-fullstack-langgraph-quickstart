import json
import os
import time
import re
from typing import Any, Dict, List, Optional
from urllib import request, parse, error

DEFAULT_LOCAL_JSON = "backend/examples/vendor_projects.json"


def _http_post_json(url: str, payload: dict, headers: dict | None, timeout: int) -> dict | list | None:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers=headers or {}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    except Exception:
        return None


def _load_local_projects(local_json: str) -> List[Dict[str, Any]]:
    """Load local mock projects with robust relative path resolution.

    Tries a list of candidate paths so it works when running from repo root,
    backend/, or backend/src/ as CWD.
    """
    raw = local_json or DEFAULT_LOCAL_JSON
    candidates: list[str] = []
    # 1) As provided (relative to CWD if not absolute)
    candidates.append(os.path.normpath(raw))
    # 2) Relative to this file (agent/ directory)
    here = os.path.dirname(__file__)
    candidates.append(os.path.normpath(os.path.join(here, raw)))
    # 3) Relative to backend/ (parent of src)
    backend_dir = os.path.normpath(os.path.join(here, os.pardir, os.pardir))
    candidates.append(os.path.normpath(os.path.join(backend_dir, os.path.relpath(raw, start="backend") if raw.startswith("backend" + os.sep) or raw.startswith("backend/") else raw)))
    # 4) Direct known default under backend/examples
    candidates.append(os.path.normpath(os.path.join(backend_dir, "examples", "vendor_projects.json")))

    path = None
    for c in candidates:
        try:
            if os.path.exists(c):
                path = c
                break
        except Exception:
            continue
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []

# 双重评分机制
# 精确匹配：查询字符串完全包含在项目文本中 → +2.0分
# 分词匹配：查询字符串的每个分词（以逗号或空格分隔）在项目文本中出现 → +1.0分
# 实际匹配示例
# 以查询"办公家具 投标 爱企查"为例：

# 分词结果：
# ["办公家具", "投标", "爱企查"]
# 匹配过程：
# python
# # 项目数据
# item = {
#     "project_name": "办公家具采购竞价公告",
#     "user_name": "恒丰家具", 
#     "date": "2025-09-01",
#     "tags": "办公家具,采购,招标"
# }

# # 合并文本
# text = "办公家具采购竞价公告 \n 恒丰家具 \n 2025-09-01 \n 办公家具,采购,招标"

# # 评分计算
# score = 0.0
# # "办公家具" in text → +1.0
# # "投标" not in text → +0.0  
# # "爱企查" not in text → +0.0
# # 最终得分：1.0
def _score_project(query: str, item: Dict[str, Any]) -> float:
    # very simple heuristic score based on substring hits across fields
    q = (query or "").strip().lower()
    if not q:
        return 0.0
    fields = [
        str(item.get("project_name", "")),
        str(item.get("user_name", "")),
        str(item.get("date", "")),
        str(item.get("tags", "")),
    ]
    text = " \n ".join(fields).lower()
    score = 0.0
    # exact substring weight
    if q in text:
        score += 2.0
    # token hits
    toks = [t for t in q.replace("，", ",").replace(" ", ",").split(",") if t]
    for t in toks:
        if t and t in text:
            score += 1.0
    return score


def _normalize_item(item: Dict[str, Any], idx: int, path_hint: str | None, score: float) -> Dict[str, Any]:
    pname = str(item.get("project_name") or f"Project-{idx+1}")
    uname = str(item.get("user_name") or "UnknownUser")
    aname = str(item.get("party_a_name") or "")
    summary = str(item.get("project_summary") or "")
    date = str(item.get("date") or "")
    label = pname
    snippet = f"项目：{pname}；概要：{summary}；日期：{date}；用户：{uname}；甲方：{aname}"
    return {
        "label": label,
        "url": f"rag://user_project/{idx}",
        "path": path_hint or "",
        "chunk_index": idx,
        "text": snippet,
        "score": float(score),
    }


def query_rag_rest(
    query: str,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 8,
    local_json: str = DEFAULT_LOCAL_JSON,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Query RAG via REST endpoint. If endpoint not provided or call fails,
    fallback to local JSON mock of user projects.

    Expected REST response (flexible): a list of items with fields like
    { project_name, project_summary, date, url?, score?, user_name, party_a_name }.
    Unknown fields are ignored.
    """
    # 1) Try REST if endpoint is configured
    hits: List[Dict[str, Any]] = []
    if endpoint:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {"query": query, "top_k": int(top_k)}
        resp = _http_post_json(endpoint, payload, headers, timeout)
        if isinstance(resp, list):
            # normalize top_k first N items
            for i, it in enumerate(resp[: max(1, top_k)]):
                try:
                    pname = it.get("project_name") or it.get("title") or f"Project-{i+1}"
                    uname = it.get("user_name") or "User"
                    aname = it.get("party_a_name") or "甲方"
                    date = it.get("date") or it.get("time") or ""
                    label = str(pname)
                    url = it.get("url") or f"rag://user_project/rest/{i}"
                    score = float(it.get("score") or 0.0)
                    summary = str(it.get("project_summary") or "")
                    snippet = f"项目：{pname}；概要：{summary}；日期：{date}；用户：{uname}；甲方：{aname}"
                    hits.append(
                        # _normalize_item(it, i, endpoint, score)
                        {
                            "label": label,
                            "url": url,
                            "path": endpoint,
                            "chunk_index": i,
                            "text": snippet,
                            "score": score,
                        }
                    )
                except Exception:
                    continue
        # If REST enabled but empty/failed, continue to fallback below

    # 2) Fallback to local JSON
    if not hits:
        items = _load_local_projects(local_json)
        scored = [(it, _score_project(query, it)) for it in items]
        scored = [pair for pair in scored if pair[1] > 0.0] or scored  # if no matches, allow zero-scores
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[: max(1, top_k)]
        for idx, (it, sc) in enumerate(top):
            hits.append(_normalize_item(it, idx, local_json, sc))

    return hits


def query_user_projects(
    user_name: str,
    local_json: str = DEFAULT_LOCAL_JSON,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Get top-K projects by user from local mock JSON.

    - user_name: 用户名（支持部分匹配，大小写不敏感）
    - 返回字段与 query_rag/query_rag_rest 归一：label/url/text/score/path/chunk_index
    - 排序规则：优先按日期降序（YYYY-MM-DD），缺失日期的排在后面
    """
    items = _load_local_projects(local_json)
    v = (user_name or "").strip().lower()
    if not items:
        return []

    # filter by user name contains
    matched = []
    for it in items:
        un = str(it.get("user_name", "")).lower()
        if v and v in un:
            matched.append(it)
    if not matched and v:
        # fallback: Levenshtein-free simple heuristic; token contains by whitespace split
        tokens = [t for t in re.split(r"[\s,，]+", v) if t]
        for it in items:
            un = str(it.get("user_name", "")).lower()
            if any(t in un for t in tokens):
                matched.append(it)

    def _date_key(it: Dict[str, Any]):
        d = str(it.get("date") or "")
        # YYYY-MM-DD 字符串按字典序即可正确降序
        return d

    matched.sort(key=_date_key, reverse=True)
    top = matched[: max(1, top_k)] if matched else items[: max(1, top_k)]

    hits: List[Dict[str, Any]] = []
    for i, it in enumerate(top):
        # score: 优先匹配用户则给较高分，否则为0
        base = 1.0 if it in matched else 0.0
        hits.append(_normalize_item(it, i, local_json, base))
    return hits

# Backward compatibility alias
query_vendor_projects = query_user_projects
