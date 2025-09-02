#!/usr/bin/env python3
"""
测试新的RAG REST接口
"""
import sys
import os
import logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from agent.rag_rest import query_rag_rest

def test_new_rag_api():
    """测试新的RAG REST接口"""
    print("=== 测试新的RAG REST接口 ===")
    
    # 新接口配置
    endpoint = "http://www-test.raritag.cn/intelligence-platform/bidProject/search"
    query = "农田建设项目 招投标"
    
    print(f"接口地址: {endpoint}")
    print(f"查询内容: {query}")
    print()
    
    try:
        # 调用新接口，使用Bearer token
        api_key = "eyJhbGciOiJIUzUxMiJ9.eyJjcmVhdGVfdGltZSI6IjIwMjUtMDktMDEgMTQ6NDc6NTgiLCJ1c2VyX2lkIjoxNTk2MDQxNzE0NDQ0MTg1NjAxLCJ1c2VyX25hbWUiOiLpgpPlrrbmmI4gIDEzNzEzNTUxMzQ0IiwidXNlcl9rZXkiOiJhakM3cjI5Sm50QUdIaGR1MGZnSU0iLCJuZXdfZmxhZyI6Im5ld19mbGFnIn0.sm3yfjGIMJd-EZIAKuBqgczSROpHOfTIuW_ZbIeON_7Dsu_g2AWI9gawWNFxDd6T_S5yqOt-Rix2DG5Lux6vwA"
        results = query_rag_rest(
            query=query,
            endpoint=endpoint,
            api_key=api_key,
            timeout=10,
            local_json="backend/examples/vendor_projects.json",
            top_k=5
        )
        
        print(f"返回结果数量: {len(results)}")
        print()
        
        if results:
            print("=== 返回的项目信息 ===")
            for i, item in enumerate(results, 1):
                print(f"{i}. {item.get('label', 'N/A')}")
                print(f"   URL: {item.get('url', 'N/A')}")
                print(f"   评分: {item.get('score', 0.0)}")
                print(f"   内容: {item.get('text', 'N/A')[:100]}...")
                print()
        else:
            print("未返回任何结果，可能使用了本地JSON回退")
            
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_new_rag_api()
