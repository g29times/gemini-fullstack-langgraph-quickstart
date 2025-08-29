#!/usr/bin/env python3
"""
测试RAG假数据的读取和处理功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.rag_rest import query_rag_rest, query_user_projects

def test_rag_data():
    """测试RAG数据读取功能"""
    print("=== 测试RAG数据读取功能 ===")
    
    # 测试办公家具相关查询
    test_queries = [
        "办公家具",
        "招投标",
        "采购公告",
        "恒丰家具",
        "联通数据智能"
    ]
    
    for query in test_queries:
        print(f"\n--- 查询: '{query}' ---")
        
        # 测试RAG REST查询（使用本地JSON回退）
        try:
            results = query_rag_rest(
                query=query,
                endpoint=None,  # 使用本地JSON回退
                api_key=None,
                timeout=8,
                local_json="backend/examples/vendor_projects.json",
                top_k=3
            )
            
            print(f"找到 {len(results)} 条相关记录:")
            for i, result in enumerate(results, 1):
                print(f"  {i}. 项目: {result.get('label', 'N/A')}")
                print(f"     概要: {result.get('text', 'N/A')[:100]}...")
                print(f"     URL: {result.get('url', 'N/A')}")
                print(f"     评分: {result.get('score', 'N/A')}")
                print()
                
        except Exception as e:
            print(f"查询失败: {e}")
    
    # 测试用户项目推荐
    print("\n=== 测试用户项目推荐功能 ===")
    test_users = ["恒丰家具", "华信科技", "联通"]
    
    for user in test_users:
        print(f"\n--- 用户: '{user}' ---")
        try:
            user_results = query_user_projects(
                user_name=user,
                local_json="backend/examples/vendor_projects.json",
                top_k=3
            )
            
            print(f"找到 {len(user_results)} 个相关项目:")
            for i, result in enumerate(user_results, 1):
                print(f"  {i}. {result.get('label', 'N/A')}")
                print(f"     {result.get('text', 'N/A')[:80]}...")
                print()
                
        except Exception as e:
            print(f"用户查询失败: {e}")

if __name__ == "__main__":
    test_rag_data()
