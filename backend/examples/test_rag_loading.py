#!/usr/bin/env python3
"""
简单的RAG数据加载测试
验证RAG数据文件能否正确加载和查询
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.rag_rest import query_rag_rest, query_user_projects, _load_local_projects

def test_rag_data_loading():
    """测试RAG数据加载功能"""
    print("=== 测试RAG数据加载功能 ===")
    
    # 1. 测试本地JSON文件加载
    print("\n1. 测试本地JSON文件加载:")
    local_json = "backend/examples/vendor_projects.json"
    projects = _load_local_projects(local_json)
    print(f"   加载项目数量: {len(projects)}")
    
    if projects:
        print("   前3个项目:")
        for i, project in enumerate(projects[:3], 1):
            print(f"   {i}. {project.get('project_name', 'N/A')}")
            print(f"      用户: {project.get('user_name', 'N/A')}")
            print(f"      甲方: {project.get('party_a_name', 'N/A')}")
            print(f"      日期: {project.get('date', 'N/A')}")
    
    # 2. 测试RAG查询功能
    print("\n2. 测试RAG查询功能:")
    test_queries = [
        "办公家具",
        "恒丰家具", 
        "联通数据智能",
        "科益药业"
    ]
    
    for query in test_queries:
        print(f"\n   查询: '{query}'")
        results = query_rag_rest(query, local_json=local_json, top_k=2)
        print(f"   结果数量: {len(results)}")
        
        for i, result in enumerate(results, 1):
            print(f"   {i}. {result.get('label', 'N/A')}")
            print(f"      评分: {result.get('score', 0):.2f}")
            print(f"      文本: {result.get('text', 'N/A')[:100]}...")
    
    # 3. 测试用户项目推荐
    print("\n3. 测试用户项目推荐:")
    test_users = ["恒丰家具", "浙江办公设备公司", "现代办公家具"]
    
    for user in test_users:
        print(f"\n   用户: '{user}'")
        user_projects = query_user_projects(user, local_json=local_json, top_k=2)
        print(f"   项目数量: {len(user_projects)}")
        
        for i, project in enumerate(user_projects, 1):
            print(f"   {i}. {project.get('label', 'N/A')}")
            print(f"      评分: {project.get('score', 0):.2f}")
    
    print("\n=== RAG数据加载测试完成 ===")
    return len(projects) > 0

if __name__ == "__main__":
    success = test_rag_data_loading()
    if success:
        print("✅ RAG数据加载测试通过")
    else:
        print("❌ RAG数据加载测试失败")
