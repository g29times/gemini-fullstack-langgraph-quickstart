#!/usr/bin/env python3
"""
测试新的RAG API响应格式兼容性
"""
import sys
import os
import json
import logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_mock_response_parsing():
    """测试mock响应数据的解析"""
    print("=== 测试新API响应格式解析 ===")
    
    # 加载mock响应数据
    mock_file = "backend/examples/mock_rag_response.json"
    try:
        with open(mock_file, 'r', encoding='utf-8') as f:
            mock_response = json.load(f)
        print(f"成功加载mock数据: {mock_file}")
        print(f"响应格式: success={mock_response.get('success')}, code={mock_response.get('code')}")
        print(f"数据项数量: {len(mock_response.get('data', []))}")
        print()
        
        # 模拟解析逻辑
        projects_data = []
        if isinstance(mock_response, dict):
            if mock_response.get("success") and mock_response.get("data"):
                projects_data = mock_response["data"]
                print(f"从API响应中提取到 {len(projects_data)} 个项目")
            else:
                print(f"API响应格式错误或无数据")
        
        # 处理项目数据
        if projects_data:
            print("\n=== 解析的项目信息 ===")
            for i, it in enumerate(projects_data[:3]):  # 只显示前3个
                pname = (it.get("projectName") or it.get("project_name") or 
                        it.get("title") or f"Project-{i+1}")
                uname = (it.get("userName") or it.get("user_name") or 
                        it.get("supplier") or "供应商")
                aname = (it.get("partyAName") or it.get("party_a_name") or 
                        it.get("owner") or "甲方")
                date = it.get("date") or it.get("time") or ""
                summary = (it.get("projectSummary") or it.get("project_summary") or 
                          it.get("description") or "")
                
                snippet = f"项目：{pname}"
                if summary:
                    snippet += f"；概要：{summary}"
                if date:
                    snippet += f"；日期：{date}"
                if uname and uname != "供应商":
                    snippet += f"；用户：{uname}"
                if aname and aname != "甲方":
                    snippet += f"；甲方：{aname}"
                
                print(f"{i+1}. {pname}")
                print(f"   用户: {uname}")
                print(f"   甲方: {aname}")
                print(f"   日期: {date}")
                print(f"   概要: {summary or '无'}")
                print(f"   文本: {snippet}")
                print()
                
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

def test_with_rag_rest():
    """使用rag_rest模块测试mock数据"""
    print("=== 使用rag_rest模块测试 ===")
    
    try:
        from agent.rag_rest import query_rag_rest
        
        # 临时修改_http_post_json来返回mock数据
        import agent.rag_rest as rag_module
        
        # 加载mock数据
        with open("backend/examples/mock_rag_response.json", 'r', encoding='utf-8') as f:
            mock_data = json.load(f)
        
        # 备份原函数
        original_func = rag_module._http_post_json
        
        # 创建mock函数
        def mock_http_post_json(url, payload, headers, timeout):
            print(f"[MOCK] 模拟HTTP请求: {url}")
            print(f"[MOCK] 返回mock数据")
            return mock_data
        
        # 替换函数
        rag_module._http_post_json = mock_http_post_json
        
        try:
            # 测试查询
            results = query_rag_rest(
                query="农田建设项目",
                endpoint="http://mock-endpoint",
                api_key="mock-token",
                timeout=10,
                local_json="backend/examples/vendor_projects.json",
                top_k=5
            )
            
            print(f"\n返回结果数量: {len(results)}")
            if results:
                print("\n=== rag_rest处理结果 ===")
                for i, item in enumerate(results[:3], 1):
                    print(f"{i}. {item.get('label', 'N/A')}")
                    print(f"   URL: {item.get('url', 'N/A')}")
                    print(f"   评分: {item.get('score', 0.0)}")
                    print(f"   内容: {item.get('text', 'N/A')}")
                    print()
        finally:
            # 恢复原函数
            rag_module._http_post_json = original_func
            
    except Exception as e:
        print(f"rag_rest测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mock_response_parsing()
    print("\n" + "="*50 + "\n")
    test_with_rag_rest()
