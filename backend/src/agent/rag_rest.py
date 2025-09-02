import json
import os
import time
import re
import logging
from typing import Any, Dict, List, Optional
from urllib import request, parse, error

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_JSON = "backend/examples/vendor_projects.json"


def _http_post_json(url: str, payload: dict | list, headers: dict | None, timeout: int) -> dict | list | None:
    # Mock endpoint: 直接返回mock数据
    if url == "http://mock-endpoint":
        logger.info("使用mock endpoint，返回mock数据")
        try:
            # 尝试多个可能的路径
            mock_paths = [
                "backend/examples/mock_rag_response.json",
                "examples/mock_rag_response.json", 
                os.path.join(os.path.dirname(__file__), "..", "..", "examples", "mock_rag_response.json")
            ]
            
            for mock_path in mock_paths:
                try:
                    if os.path.exists(mock_path):
                        with open(mock_path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception:
                    continue
            
            # 如果文件不存在，返回内置mock数据
            logger.warning("mock文件未找到，使用内置mock数据")
            return {
                "success": True,
                "code": 200,
                "message": "操作成功",
                "data": [
                    {
                        "id": "334",
                        "projectName": "吉县农业生产基地建设项目招标公告",
                        "userName": "",
                        "projectSummary": None,
                        "url": None,
                        "date": "2025-09-08 09:00:00",
                        "partyAName": None
                    },
                    {
                        "id": "390", 
                        "projectName": "2025年濉溪县百善镇叶刘湖村高标准农田建设项目",
                        "userName": "",
                        "projectSummary": None,
                        "url": None,
                        "date": "2025-09-03 09:00:00",
                        "partyAName": None
                    }
                ]
            }
        except Exception as e:
            logger.error("Mock数据加载失败: %s", str(e))
            return None
    
    # 真实HTTP请求
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers=headers or {}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            if not raw:
                return None
            try:
                result = json.loads(raw)
                return result
            except json.JSONDecodeError as e:
                logger.warning("RAG REST JSON解析失败: %s", str(e))
                return None
    except Exception as e:
        logger.warning("RAG REST请求失败: %s", str(e))
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
        logger.info("[NEO_LOG] [query_rag_rest] 调用REST接口: %s", endpoint)
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        # New API format: send query as array of strings
        payload = [query]  # Changed from dict to array format
        
        resp = _http_post_json(endpoint, payload, headers, timeout)
        
        # Handle new API response format: {"success": true, "data": [...]}
        projects_data = []
        if isinstance(resp, dict):
            if resp.get("success") and resp.get("data"):
                projects_data = resp["data"]
                logger.info("[NEO_LOG] [query_rag_rest] 从API响应中提取到 %d 个项目", len(projects_data))
            else:
                logger.warning("[NEO_LOG] [query_rag_rest] API响应格式错误或无数据: success=%s", resp.get('success'))
        elif isinstance(resp, list):
            # 兼容旧格式：直接是项目数组
            projects_data = resp
            logger.info("[NEO_LOG] [query_rag_rest] 使用旧格式，项目数量: %d", len(projects_data))
        
        # Process projects data
        if projects_data:
            for i, it in enumerate(projects_data[: max(1, top_k)]):
                try:
                    # 兼容新旧字段名
                    pname = (it.get("projectName") or it.get("project_name") or 
                            it.get("title") or f"Project-{i+1}")
                    uname = (it.get("userName") or it.get("user_name") or 
                            it.get("supplier") or "供应商")
                    aname = (it.get("partyAName") or it.get("party_a_name") or 
                            it.get("owner") or "甲方")
                    date = it.get("date") or it.get("time") or ""
                    summary = (it.get("projectSummary") or it.get("project_summary") or 
                              it.get("description") or "")
                    
                    label = str(pname)
                    url = it.get("url") or f"rag://user_project/rest/{i}"
                    score = float(it.get("score") or 1.0)  # 默认评分1.0
                    
                    # 构建项目描述文本
                    snippet = f"项目：{pname}"
                    if summary:
                        snippet += f"；概要：{summary}"
                    if date:
                        snippet += f"；日期：{date}"
                    if uname and uname != "供应商":
                        snippet += f"；用户：{uname}"
                    if aname and aname != "甲方":
                        snippet += f"；甲方：{aname}"
                    
                    hits.append({
                        "label": label,
                        "url": url,
                        "path": endpoint,
                        "chunk_index": i,
                        "text": snippet,
                        "score": score,
                    })
                except Exception as e:
                    logger.warning("[NEO_LOG] [query_rag_rest] 处理项目 %d 时出错: %s", i, str(e))
                    continue
    
    logger.info("[NEO_LOG] [query_rag_rest] rest hits: %d", len(hits))
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
        logger.info("[NEO_LOG] [query_rag_rest] local hits: %d", len(hits))
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
