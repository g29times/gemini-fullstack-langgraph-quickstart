#!/usr/bin/env python3
"""
简化的RAG数据测试脚本
直接测试JSON数据读取和TF-IDF匹配功能
"""

import json
import re
from typing import List, Dict, Any

def load_json_data(file_path: str) -> List[Dict[str, Any]]:
    """加载JSON数据"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载JSON失败: {e}")
        return []

def simple_tf_idf_score(query: str, item: Dict[str, Any]) -> float:
    """简单的TF-IDF评分"""
    if not query or not item:
        return 0.0
    
    # 构建搜索字段
    fields = [
        str(item.get("project_name", "")),
        str(item.get("user_name", "")),
        str(item.get("party_a_name", "")),
        str(item.get("date", "")),
        str(item.get("tags", "")),
        str(item.get("project_summary", "")),
    ]
    text = " ".join(fields).lower()
    query_lower = query.lower()
    
    # 简单匹配评分
    score = 0.0
    query_tokens = re.findall(r'\w+', query_lower)
    
    for token in query_tokens:
        if token in text:
            score += 1.0
    
    return score

def search_projects(query: str, data: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """搜索项目"""
    results = []
    
    for i, item in enumerate(data):
        score = simple_tf_idf_score(query, item)
        if score > 0:
            result = {
                "label": item.get("project_name", f"Project-{i+1}"),
                "url": item.get("url", f"rag://project/{i}"),
                "score": score,
                "text": f"项目：{item.get('project_name', '')}；概要：{item.get('project_summary', '')}；日期：{item.get('date', '')}；用户：{item.get('user_name', '')}；甲方：{item.get('party_a_name', '')}",
                "raw_data": item
            }
            results.append(result)
    
    # 按评分排序
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

def test_rag_functionality():
    """测试RAG功能"""
    print("=== 简化RAG功能测试 ===")
    
    # 加载数据
    data_file = "backend/examples/vendor_projects.json"
    data = load_json_data(data_file)
    
    if not data:
        print("❌ 无法加载数据文件")
        return
    
    print(f"✅ 成功加载 {len(data)} 条数据")
    
    # 测试查询
    test_queries = [
        "办公家具",
        "招投标",
        "恒丰家具", 
        "联通数据智能",
        "绿城集团",
        "科益药业"
    ]
    
    for query in test_queries:
        print(f"\n--- 查询: '{query}' ---")
        results = search_projects(query, data, top_k=3)
        
        if results:
            print(f"找到 {len(results)} 条匹配记录:")
            for i, result in enumerate(results, 1):
                print(f"  {i}. 项目: {result['label']}")
                print(f"     评分: {result['score']}")
                print(f"     概要: {result['text'][:100]}...")
                print(f"     URL: {result['url']}")
                print()
        else:
            print("  未找到匹配记录")
    
    # 测试用户项目推荐
    print("\n=== 用户项目推荐测试 ===")
    test_users = ["恒丰家具", "华信科技", "联通"]
    
    for user in test_users:
        print(f"\n--- 用户: '{user}' ---")
        user_results = []
        
        for item in data:
            user_name = str(item.get("user_name", "")).lower()
            if user.lower() in user_name or any(token in user_name for token in user.lower().split()):
                user_results.append({
                    "label": item.get("project_name", ""),
                    "text": f"项目：{item.get('project_name', '')}；概要：{item.get('project_summary', '')}；日期：{item.get('date', '')}；用户：{item.get('user_name', '')}；甲方：{item.get('party_a_name', '')}",
                    "raw_data": item
                })
        
        if user_results:
            print(f"找到 {len(user_results)} 个相关项目:")
            for i, result in enumerate(user_results[:3], 1):
                print(f"  {i}. {result['label']}")
                print(f"     {result['text'][:80]}...")
        else:
            print("  未找到相关项目")
    
    print("\n=== 数据结构验证 ===")
    sample_item = data[0] if data else {}
    expected_fields = ["project_name", "user_name", "party_a_name", "date", "project_summary", "url"]
    
    print("检查数据字段完整性:")
    for field in expected_fields:
        has_field = field in sample_item
        print(f"  {field}: {'✅' if has_field else '❌'}")
    
    print(f"\n✅ RAG数据测试完成！")
    print(f"数据文件: {data_file}")
    print(f"数据条数: {len(data)}")
    print(f"办公家具相关项目: {len([item for item in data if '办公家具' in str(item.get('tags', []))])}")

if __name__ == "__main__":
    test_rag_functionality()
