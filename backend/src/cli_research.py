import argparse
import json
from langchain_core.messages import HumanMessage
from langgraph.errors import NodeInterrupt
from agent.graph import graph

# 可能失败原因：VPN，APIKEY，酒旅 餐饮 潮玩 广东 长三角
# 查三轮 python backend/src/cli_research.py --max-concurrency 4 --auto-approve "最近有哪些广东地区的酒旅相关的项目"
# 查一轮（优先）python backend/src/cli_research.py --max-concurrency 4 --max-loops 1 --auto-approve "最近有哪些广东地区的酒旅相关的项目"
def main() -> None:
    """Run the research agent from the command line."""
    parser = argparse.ArgumentParser(description="Run the LangGraph research agent")
    parser.add_argument("question", help="Research question")
    parser.add_argument(
        "--effort",
        type=str,
        default="medium",
        help="Effort level: 'low', 'medium', 'high'.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=None,
        help="Override: concurrent node executions within a superstep. If not set, computed as max_parallel_queries * (1 + enable_rag_rest)",
    )
    parser.add_argument(
        "--initial-queries",
        type=int,
        default=3,
        help="Number of initial search queries",
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=3,
        help="Maximum number of research loops",
    )
    parser.add_argument(
        "--reasoning-model",
        default="gemini-2.5-flash-lite",
        help="Model for the final answer",
    )
    parser.add_argument(
        "--quick-lookup",
        action="store_true",
        help="Prefer quick/direct lookup route by injecting {\"action\":\"quick_lookup\"} at HITL",
    )
    parser.add_argument(
        "--direct-lookup",
        action="store_true",
        help="Force direct lookup route by injecting {\"action\":\"direct_lookup\"} at HITL",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve the research plan at the HITL stage for testing",
    )
    args = parser.parse_args()

    state = {
        "messages": [HumanMessage(content=args.question)],
        "initial_search_query_count": args.initial_queries,
        "max_research_loops": args.max_loops,
        "reasoning_model": args.reasoning_model,
        "effort": args.effort,
    }

    # Run graph, handling HITL NodeInterrupt by optionally auto-approving
    while True:
        try:
            # Enable true parallel execution of branches within the same superstep
            # If user did not override, compute from configuration
            from agent.configuration import Configuration
            cfg = Configuration()
            factor = 1 + 1 # (1 if getattr(cfg, "enable_rag_rest", True) else 0)
            computed_mc = (getattr(cfg, "max_parallel_queries", 4) or 1) * max(1, factor)
            mc = args.max_concurrency if args.max_concurrency is not None else computed_mc
            result = graph.invoke(state, {"max_concurrency": mc})
            break
        except NodeInterrupt as interrupt:
            print("[CLI] Caught NodeInterrupt (HITL)")
            # Priorities: quick_lookup/direct_lookup > auto_approve > prompt user
            if args.quick_lookup or args.direct_lookup:
                action = "quick_lookup" if args.quick_lookup else "direct_lookup"
                payload = {"action": action}
                state.setdefault("messages", []).append(
                    HumanMessage(content=json.dumps(payload))
                )
                print(f"[CLI] Injected HITL action: {action}")
                continue
            if args.auto_approve:
                # Auto-approve: simulate a human message approving the plan
                approval_payload = {"action": "approve_plan", "plan_approved": True}
                state.setdefault("messages", []).append(
                    HumanMessage(content=json.dumps(approval_payload))
                )
                print("[CLI] Injected HITL action: approve_plan")
                continue
            # Otherwise, show the plan summary and exit with guidance
            print(str(interrupt))
            print("\n[HITL] 需要人工批准。可使用 --quick-lookup / --direct-lookup / --auto-approve 以自动注入指令继续执行。")
            return

    messages = result.get("messages", [])
    if messages:
        print("\n报告：\n" + messages[-1].content)


if __name__ == "__main__":
    main()
