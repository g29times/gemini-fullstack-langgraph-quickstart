#!/usr/bin/env python3
"""
完整的 Web + RAG 集成测试脚本
基于 cli_research.py 模式，专门测试供应商项目查询场景

使用方法：
python backend/examples/test_web_rag_full.py "我是供应商 华信科技 我想看看有没有酒店施工项目"
"""

import argparse
import json
import os
import sys
from pathlib import Path
from langchain_core.messages import HumanMessage
from langgraph.errors import NodeInterrupt

# 添加 src 目录到路径，避免循环导入
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def run_agent_test(question: str, bypass_method: str = "direct_lookup"):
    """运行 Agent 测试，使用指定的绕过方法"""
    print(f"🚀 开始测试 Web + RAG 集成")
    print(f"问题: {question}")
    print(f"绕过方法: {bypass_method}")
    
    try:
        # 延迟导入，避免循环导入问题
        from agent.graph import graph
        
        # 构建状态，优化参数以加快测试速度
        state = {
            "messages": [HumanMessage(content=question)],
            "initial_search_query_count": 2,  # 减少查询数量
            "max_research_loops": 1,  # 限制研究轮数
            "reasoning_model": "gemini-2.5-pro-preview-05-06",
        }
        
        print(f"\n=== 开始执行 Agent ===")
        
        # 运行图，处理 HITL 中断
        max_attempts = 3
        attempt = 0
        
        while attempt < max_attempts:
            try:
                print(f"\n--- 尝试 {attempt + 1}/{max_attempts} ---")
                result = graph.invoke(state)
                
                print("✅ Agent 执行成功")
                
                # 输出最终结果
                messages = result.get("messages", [])
                if messages:
                    final_message = messages[-1]
                    print(f"\n{'='*60}")
                    print("🎯 最终回答:")
                    print(f"{'='*60}")
                    print(final_message.content)
                    print(f"{'='*60}")
                    
                    # 检查回答中是否包含 RAG 数据
                    content = final_message.content.lower()
                    has_user_projects = "用户项目" in content or "华信科技" in content
                    has_web_data = "http" in content or "www" in content
                    
                    print(f"\n📊 结果分析:")
                    print(f"   - 包含用户项目数据: {'是' if has_user_projects else '否'}")
                    print(f"   - 包含网络搜索数据: {'是' if has_web_data else '否'}")
                    
                    if has_user_projects and has_web_data:
                        print("🎉 Web + RAG 集成成功！")
                    elif has_user_projects:
                        print("✅ RAG 数据集成成功")
                    elif has_web_data:
                        print("✅ Web 搜索成功")
                    else:
                        print("⚠️  可能缺少预期的数据源")
                else:
                    print("⚠️ 未获得最终回答")
                
                return result
                
            except NodeInterrupt as interrupt:
                attempt += 1
                print(f"[HITL] 捕获到人工干预请求")
                print(f"详情: {interrupt}")
                
                # 根据绕过方法注入相应的指令
                if bypass_method == "direct_lookup":
                    payload = {"action": "direct_lookup"}
                    print("[HITL] 注入直接查询指令")
                elif bypass_method == "quick_lookup":
                    payload = {"action": "quick_lookup"}
                    print("[HITL] 注入快速查询指令")
                elif bypass_method == "auto_approve":
                    payload = {"action": "approve_plan", "plan_approved": True}
                    print("[HITL] 注入自动批准指令")
                else:
                    print(f"[HITL] 未知的绕过方法: {bypass_method}")
                    break
                
                # 将指令添加到状态中
                state.setdefault("messages", []).append(
                    HumanMessage(content=json.dumps(payload))
                )
                print(f"[HITL] 已注入指令，继续执行...")
                
            except Exception as e:
                print(f"❌ Agent 执行出错: {e}")
                import traceback
                traceback.print_exc()
                break
        
        print(f"❌ Agent 执行失败，已尝试 {max_attempts} 次")
        return None
        
    except ImportError as e:
        print(f"❌ 无法导入 Agent 模块: {e}")
        print("提示：请确保在项目根目录下运行此脚本，并且已修复所有导入问题")
        return None
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_rag_preview():
    """预览 RAG 功能，确保数据可用"""
    print("=== RAG 功能预览 ===")
    
    try:
        # 直接导入 RAG 功能进行快速测试
        from agent.rag_rest import query_user_projects, query_rag_rest
        
        # 测试华信科技项目
        print("1. 华信科技相关项目:")
        user_projects = query_user_projects("华信科技", top_k=2)
        for i, project in enumerate(user_projects, 1):
            print(f"   {i}. {project.get('text', 'N/A')}")
        
        # 测试酒店相关项目
        print("\n2. 酒店相关项目:")
        hotel_projects = query_rag_rest("酒店施工", top_k=2)
        for i, project in enumerate(hotel_projects, 1):
            print(f"   {i}. {project.get('text', 'N/A')}")
        
        has_data = len(user_projects) > 0 or len(hotel_projects) > 0
        print(f"\n✅ RAG 数据可用: {'是' if has_data else '否'}")
        return has_data
        
    except Exception as e:
        print(f"❌ RAG 预览失败: {e}")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Web + RAG 集成测试")
    parser.add_argument(
        "question", 
        nargs="?",
        default="我是供应商 华信科技 我想看看有没有酒店施工项目",
        help="测试问题"
    )
    parser.add_argument(
        "--bypass-method",
        choices=["direct_lookup", "quick_lookup", "auto_approve"],
        default="direct_lookup",
        help="绕过深度研究的方法"
    )
    parser.add_argument(
        "--skip-rag-preview",
        action="store_true",
        help="跳过 RAG 功能预览"
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="仅运行 RAG 预览，不执行完整测试"
    )
    
    args = parser.parse_args()
    
    print("🔬 Web + RAG 集成测试")
    print(f"测试问题: {args.question}")
    
    # 检查环境变量
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ 错误: 未设置 GEMINI_API_KEY 环境变量")
        return 1
    
    success = True
    
    # RAG 功能预览
    if not args.skip_rag_preview:
        try:
            rag_available = test_rag_preview()
            if not rag_available:
                print("⚠️ 警告: RAG 数据不可用，可能影响测试结果")
        except Exception as e:
            print(f"❌ RAG 预览失败: {e}")
            success = False
    
    # 如果只是预览，则退出
    if args.preview_only:
        print("\n✅ RAG 预览完成")
        return 0 if success else 1
    
    # 运行完整的 Agent 测试
    try:
        result = run_agent_test(args.question, args.bypass_method)
        if result is None:
            success = False
        else:
            print("\n🎯 测试建议:")
            print("   - 检查回答是否同时包含了外部搜索和内部RAG数据")
            print("   - 验证供应商匹配逻辑是否合理")
            print("   - 确认项目推荐是否基于历史数据和外部信息")
            
    except Exception as e:
        print(f"❌ 完整测试失败: {e}")
        success = False
    
    # 总结
    print(f"\n{'='*60}")
    if success:
        print("✅ Web + RAG 集成测试完成")
        print("💡 如果回答质量不理想，可以尝试不同的绕过方法:")
        print("   --bypass-method quick_lookup")
        print("   --bypass-method auto_approve")
    else:
        print("❌ 测试过程中遇到问题")
        print("💡 建议:")
        print("   1. 检查 GEMINI_API_KEY 是否正确设置")
        print("   2. 确保所有依赖模块导入正常")
        print("   3. 运行 test_rag_standalone.py 验证 RAG 功能")
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
