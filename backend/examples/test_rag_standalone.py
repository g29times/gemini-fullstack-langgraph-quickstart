#!/usr/bin/env python3
"""
独立的 RAG 功能测试脚本
直接复制 rag_rest.py 的核心功能，避免导入问题

使用方法：
python backend/examples/test_rag_standalone.py
"""

import json
import os
from typing import Any, Dict, List


DEFAULT_LOCAL_JSON = "backend/examples/vendor_projects.json"


def _load_local_projects(local_json: str) -> List[Dict[str, Any]]:
    """加载本地项目数据"""
    raw = local_json or DEFAULT_LOCAL_JSON
    candidates = []
    
    # 尝试多个可能的路径
    candidates.append(os.path.normpath(raw))
    here = os.path.dirname(__file__)
    candidates.append(os.path.normpath(os.path.join(here, raw)))
    backend_dir = os.path.normpath(os.path.join(here, os.pardir))
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
    except Exception as e:
        print(f"加载项目数据失败: {e}")
        return []


def _score_project(query: str, item: Dict[str, Any]) -> float:
    """计算项目与查询的匹配分数"""
    q = (query or "").strip().lower()
    if not q:
        return 0.0
    
    fields = [
        str(item.get("project_name", "")),
        str(item.get("user_name", "") or item.get("vendor_name", "")),
        str(item.get("date", "")),
        str(item.get("tags", "")),
        str(item.get("description", "")),
    ]
    text = " \n ".join(fields).lower()
    score = 0.0
    
    # 精确匹配
    if q in text:
        score += 2.0
    
    # 分词匹配
    tokens = [t for t in q.replace("，", ",").replace(" ", ",").split(",") if t]
    for t in tokens:
        if t and t in text:
            score += 1.0
    
    return score


def _normalize_item(item: Dict[str, Any], idx: int, path_hint: str, score: float) -> Dict[str, Any]:
    """标准化项目数据格式"""
    pname = str(item.get("project_name") or f"Project-{idx+1}")
    uname = str(item.get("user_name") or item.get("vendor_name") or "UnknownUser")
    date = str(item.get("date") or "")
    label = pname
    snippet = f"项目：{pname}；用户：{uname}；日期：{date}"
    
    return {
        "label": label,
        "url": f"rag://user_project/{idx}",
        "path": path_hint or "",
        "chunk_index": idx,
        "text": snippet,
        "score": float(score),
    }


def query_user_projects_standalone(user_name: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """查询用户项目（独立版本）"""
    items = _load_local_projects(DEFAULT_LOCAL_JSON)
    v = (user_name or "").strip().lower()
    if not items:
        return []
    
    # 按用户名过滤
    matched = []
    for it in items:
        un = str(it.get("user_name", "") or it.get("vendor_name", "")).lower()
        if v and v in un:
            matched.append(it)
    
    # 按日期排序
    def _date_key(it: Dict[str, Any]):
        d = str(it.get("date") or "")
        return d
    
    matched.sort(key=_date_key, reverse=True)
    top = matched[: max(1, top_k)] if matched else items[: max(1, top_k)]
    
    hits = []
    for i, it in enumerate(top):
        base = 1.0 if it in matched else 0.0
        hits.append(_normalize_item(it, i, DEFAULT_LOCAL_JSON, base))
    
    return hits


def query_rag_rest_standalone(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """RAG REST 查询（独立版本，仅使用本地数据）"""
    items = _load_local_projects(DEFAULT_LOCAL_JSON)
    scored = [(it, _score_project(query, it)) for it in items]
    scored = [pair for pair in scored if pair[1] > 0.0] or scored
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[: max(1, top_k)]
    
    hits = []
    for idx, (it, sc) in enumerate(top):
        hits.append(_normalize_item(it, idx, DEFAULT_LOCAL_JSON, sc))
    
    return hits


def test_user_projects():
    """测试用户项目查询功能"""
    print("=== 测试用户项目查询 ===")
    
    # 测试华信科技
    print("1. 查询华信科技的项目:")
    projects = query_user_projects_standalone("华信科技", top_k=5)
    for i, project in enumerate(projects, 1):
        print(f"   {i}. {project.get('text', 'N/A')}")
        print(f"      Score: {project.get('score', 0.0)}")
    
    print(f"\n   找到 {len(projects)} 个华信科技相关项目")
    
    # 测试其他供应商
    print("\n2. 查询启元数据的项目:")
    projects2 = query_user_projects_standalone("启元数据", top_k=3)
    for i, project in enumerate(projects2, 1):
        print(f"   {i}. {project.get('text', 'N/A')}")
    
    print(f"\n   找到 {len(projects2)} 个启元数据相关项目")
    
    return len(projects) > 0


def test_rag_query():
    """测试 RAG 查询功能"""
    print("\n=== 测试 RAG 查询 ===")
    
    # 测试酒店相关项目
    print("1. 查询酒店相关项目:")
    results = query_rag_rest_standalone("酒店施工项目", top_k=5)
    for i, result in enumerate(results, 1):
        print(f"   {i}. {result.get('text', 'N/A')}")
        print(f"      Score: {result.get('score', 0.0)}")
    
    print(f"\n   找到 {len(results)} 个酒店相关结果")
    
    # 测试物联网相关项目
    print("\n2. 查询物联网相关项目:")
    results2 = query_rag_rest_standalone("物联网 IoT", top_k=3)
    for i, result in enumerate(results2, 1):
        print(f"   {i}. {result.get('text', 'N/A')}")
        print(f"      Score: {result.get('score', 0.0)}")
    
    print(f"\n   找到 {len(results2)} 个物联网相关结果")
    
    return len(results) > 0 or len(results2) > 0


def test_combined_scenario():
    """测试组合场景：供应商查询相关项目"""
    print("\n=== 测试组合场景：华信科技查找酒店施工项目 ===")
    
    # 1. 先查华信科技的历史项目
    print("\n1. 华信科技的历史项目:")
    user_projects = query_user_projects_standalone("华信科技", top_k=3)
    for i, project in enumerate(user_projects, 1):
        print(f"   {i}. {project.get('text', 'N/A')}")
    
    # 2. 再查酒店相关的所有项目
    print("\n2. 酒店相关的所有项目:")
    hotel_projects = query_rag_rest_standalone("酒店 施工", top_k=3)
    for i, project in enumerate(hotel_projects, 1):
        print(f"   {i}. {project.get('text', 'N/A')}")
        print(f"      Score: {project.get('score', 0.0)}")
    
    # 3. 分析匹配度
    print("\n3. 分析结果:")
    if user_projects:
        print(f"   - 华信科技有 {len(user_projects)} 个历史项目")
        # 检查华信科技是否有相关经验
        user_text = " ".join([p.get('text', '') for p in user_projects]).lower()
        has_iot = 'iot' in user_text or '物联网' in user_text
        has_platform = '平台' in user_text
        has_construction = '施工' in user_text or '建设' in user_text
        print(f"   - 有物联网/IoT经验: {'是' if has_iot else '否'}")
        print(f"   - 有平台开发经验: {'是' if has_platform else '否'}")
        print(f"   - 有施工/建设经验: {'是' if has_construction else '否'}")
    
    if hotel_projects:
        print(f"   - 找到 {len(hotel_projects)} 个酒店相关项目机会")
        # 检查是否有匹配的项目
        has_matches = any(p.get('score', 0) > 0 for p in hotel_projects)
        print(f"   - 有匹配的项目: {'是' if has_matches else '否'}")
    
    # 4. 推荐建议
    print("\n4. 推荐建议:")
    if user_projects and hotel_projects:
        if has_iot and has_platform:
            print("   ✅ 华信科技有物联网和平台开发经验，适合承接智能酒店相关项目")
        else:
            print("   ⚠️  华信科技可能需要补充相关经验才能承接酒店项目")
    
    return len(user_projects) > 0 and len(hotel_projects) > 0


def main():
    """主函数"""
    print("🚀 独立 RAG 功能测试开始")
    print("测试场景：供应商华信科技查询酒店施工项目")
    
    success_count = 0
    total_tests = 3
    
    try:
        # 测试1：用户项目查询
        if test_user_projects():
            success_count += 1
            print("✅ 用户项目查询测试通过")
        else:
            print("❌ 用户项目查询测试失败")
    except Exception as e:
        print(f"❌ 用户项目查询测试出错: {e}")
    
    try:
        # 测试2：RAG 查询
        if test_rag_query():
            success_count += 1
            print("✅ RAG 查询测试通过")
        else:
            print("❌ RAG 查询测试失败")
    except Exception as e:
        print(f"❌ RAG 查询测试出错: {e}")
    
    try:
        # 测试3：组合场景
        if test_combined_scenario():
            success_count += 1
            print("✅ 组合场景测试通过")
        else:
            print("❌ 组合场景测试失败")
    except Exception as e:
        print(f"❌ 组合场景测试出错: {e}")
    
    # 总结
    print(f"\n{'='*60}")
    print(f"测试完成: {success_count}/{total_tests} 通过")
    
    if success_count == total_tests:
        print("🎉 所有 RAG 功能测试通过！")
        print("💡 下一步：可以测试完整的 Agent 集成流程")
        print("💡 建议使用 --direct-lookup 或 --quick-lookup 绕过深度研究")
        return 0
    else:
        print("⚠️  部分测试失败，请检查数据文件路径")
        return 1


if __name__ == "__main__":
    exit(main())
