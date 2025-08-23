import { useStream } from "@langchain/langgraph-sdk/react";
import type { Message } from "@langchain/langgraph-sdk";
import { useState, useEffect, useRef, useCallback } from "react";
import { ProcessedEvent } from "@/components/ActivityTimeline";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { ChatMessagesView } from "@/components/ChatMessagesView";
import { ResearchPlanApproval } from "@/components/ResearchPlanApproval";
import { CollapsedResearchPlan } from "@/components/CollapsedResearchPlan";
import { EnhancedReport } from "@/components/EnhancedReport";
import { Button } from "@/components/ui/button";

export default function App() {
  const [processedEventsTimeline, setProcessedEventsTimeline] = useState<
    ProcessedEvent[]
  >([]);
  const [historicalActivities, setHistoricalActivities] = useState<
    Record<string, ProcessedEvent[]>
  >({});
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const hasFinalizeEventOccurredRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [researchPlan, setResearchPlan] = useState<any>(null);
  const [showHitlApproval, setShowHitlApproval] = useState(false);
  const [approvedPlan, setApprovedPlan] = useState<any>(null);
  const [showPlanCollapsed, setShowPlanCollapsed] = useState(false);
  const [finalReport, setFinalReport] = useState<any>(null);
  const [thinkingProcess, setThinkingProcess] = useState<any[]>([]);
  const [sourcesGathered, setSourcesGathered] = useState<any[]>([]);
  const thread = useStream<{
    messages: Message[];
    initial_search_query_count: number;
    max_research_loops: number;
    reasoning_model: string;
  }>({
    apiUrl: import.meta.env.DEV
      ? "http://localhost:2024"
      : "http://localhost:8123",
    assistantId: "agent",
    messagesKey: "messages",
    onUpdateEvent: (event: any) => {
      let processedEvent: ProcessedEvent | null = null;
      
      // Debug: log all events to understand the structure
      console.log("Event received:", event);
      
      // Handle interrupt events (HITL) - check for __interrupt__ property
      // Only show HITL if we haven't already approved a plan and don't have a final report
      if ((event.__interrupt__ || event.hasOwnProperty('__interrupt__')) && 
          !finalReport && !showPlanCollapsed) {
        setShowHitlApproval(true);
        processedEvent = {
          title: "等待人工确认",
          data: "研究计划已生成，等待您的确认...",
        };
      }
      // Enhanced DeepResearch flow events
      else if (event.detect_follow_up) {
        processedEvent = {
          title: "检测追问",
          data: "分析是否为追问对话",
        };
      } else if (event.classify_intent) {
        const intent = event.classify_intent?.intent;
        processedEvent = {
          title: "意图分类",
          data: `分类结果: ${intent?.intent_label || "未知"} (置信度: ${intent?.confidence || 0})`,
        };
      } else if (event.generate_research_plan) {
        const plan = event.generate_research_plan?.research_plan;
        setResearchPlan(plan);
        processedEvent = {
          title: "生成研究计划",
          data: `研究目标: ${plan?.research_objectives?.length || 0}个，计划查询: ${plan?.planned_queries?.length || 0}个`,
        };
      } else if (event.wait_for_human_approval && !finalReport && !showPlanCollapsed) {
        setShowHitlApproval(true);
        processedEvent = {
          title: "等待人工确认",
          data: "研究计划已生成，等待您的确认...",
        };
      } else if (event.thinking_startup_stage) {
        processedEvent = {
          title: "起步思考阶段",
          data: "概述分解规划中...",
        };
      } else if (event.thinking_middle_stage) {
        processedEvent = {
          title: "中间思考阶段", 
          data: "洞察梳理深化中...",
        };
      } else if (event.thinking_finalization_stage) {
        processedEvent = {
          title: "收尾思考阶段",
          data: "洞察梳理总结中...",
        };
      } else if (event.generate_enhanced_report) {
        const report = event.generate_enhanced_report;
        setFinalReport(report);
        if (report.thinking_process) {
          setThinkingProcess(report.thinking_process);
        }
        if (report.sources_gathered) {
          setSourcesGathered(report.sources_gathered);
        }
        processedEvent = {
          title: "生成增强报告",
          data: "生成结构化研究报告...",
        };
        hasFinalizeEventOccurredRef.current = true;
      } else if (event.find_official_site) {
        processedEvent = {
          title: "查找官方站点",
          data: "搜索官方域名中...",
        };
      } else if (event.direct_lookup) {
        processedEvent = {
          title: "直接查询",
          data: "在官方站点执行查询...",
        };
      } else if (event.handle_follow_up) {
        processedEvent = {
          title: "处理追问",
          data: "基于之前报告回答追问...",
        };
      }
      // Original flow events (fallback)
      else if (event.generate_query) {
        processedEvent = {
          title: "生成搜索查询",
          data: event.generate_query?.search_query?.join(", ") || "",
        };
      } else if (event.web_research) {
        const sources = event.web_research.sources_gathered || [];
        const numSources = sources.length;
        const uniqueLabels = [
          ...new Set(sources.map((s: any) => s.label).filter(Boolean)),
        ];
        const exampleLabels = uniqueLabels.slice(0, 3).join(", ");
        processedEvent = {
          title: "网络研究",
          data: `收集了 ${numSources} 个来源。相关: ${
            exampleLabels || "N/A"
          }`,
        };
      } else if (event.reflection) {
        processedEvent = {
          title: "反思分析",
          data: "分析网络研究结果",
        };
      } else if (event.finalize_answer) {
        processedEvent = {
          title: "最终答案",
          data: "组织并呈现最终答案",
        };
        hasFinalizeEventOccurredRef.current = true;
      }
      
      if (processedEvent) {
        setProcessedEventsTimeline((prevEvents) => [
          ...prevEvents,
          processedEvent!,
        ]);
      }
    },
    onError: (error: any) => {
      setError(error.message);
    },
  });

  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollViewport = scrollAreaRef.current.querySelector(
        "[data-radix-scroll-area-viewport]"
      );
      if (scrollViewport) {
        scrollViewport.scrollTop = scrollViewport.scrollHeight;
      }
    }
  }, [thread.messages]);

  useEffect(() => {
    if (
      hasFinalizeEventOccurredRef.current &&
      !thread.isLoading &&
      thread.messages.length > 0
    ) {
      const lastMessage = thread.messages[thread.messages.length - 1];
      if (lastMessage && lastMessage.type === "ai" && lastMessage.id) {
        setHistoricalActivities((prev) => ({
          ...prev,
          [lastMessage.id!]: [...processedEventsTimeline],
        }));
      }
      hasFinalizeEventOccurredRef.current = false;
    }
  }, [thread.messages, thread.isLoading, processedEventsTimeline]);

  const handleSubmit = useCallback(
    (submittedInputValue: string, effort: string, model: string) => {
      if (!submittedInputValue.trim()) return;
      setProcessedEventsTimeline([]);
      hasFinalizeEventOccurredRef.current = false;

      // convert effort to, initial_search_query_count and max_research_loops
      // low means max 1 loop and 1 query
      // medium means max 3 loops and 3 queries
      // high means max 10 loops and 5 queries
      let initial_search_query_count = 0;
      let max_research_loops = 0;
      switch (effort) {
        case "low":
          initial_search_query_count = 1;
          max_research_loops = 1;
          break;
        case "medium":
          initial_search_query_count = 3;
          max_research_loops = 3;
          break;
        case "high":
          initial_search_query_count = 5;
          max_research_loops = 10;
          break;
      }

      const newMessages: Message[] = [
        ...(thread.messages || []),
        {
          type: "human",
          content: submittedInputValue,
          id: Date.now().toString(),
        },
      ];
      thread.submit({
        messages: newMessages,
        initial_search_query_count: initial_search_query_count,
        max_research_loops: max_research_loops,
        reasoning_model: model,
      });
    },
    [thread]
  );

  const handleCancel = useCallback(() => {
    thread.stop();
    window.location.reload();
  }, [thread]);

  const handleApproveResearchPlan = useCallback((modifications?: string) => {
    // 保存已批准的计划用于折叠显示
    setApprovedPlan(researchPlan);
    setShowPlanCollapsed(true);
    setShowHitlApproval(false);
    setResearchPlan(null);
    
    // 创建批准消息
    const approvalMessage: Message = {
      type: "human",
      content: JSON.stringify({
        action: "approve_plan",
        plan_approved: true,
        human_modifications: modifications || ""
      }),
      id: Date.now().toString(),
    };
    
    // 关键修复：不重新提交整个对话，而是继续当前流程
    // 通过添加批准消息到现有消息中，但保持当前的配置参数
    const currentConfig = {
      initial_search_query_count: 3,
      max_research_loops: 3,
      reasoning_model: "gemini-1.5-pro",
    };
    
    thread.submit({
      messages: [...thread.messages, approvalMessage],
      ...currentConfig
    });
  }, [thread, researchPlan]);

  const handleModifyResearchPlan = useCallback((modifications: string) => {
    setShowHitlApproval(false);
    setResearchPlan(null); // 清除研究计划状态，回到对话界面
    
    // 重新提交带有修改要求的消息
    const modificationMessage: Message = {
      type: "human", 
      content: JSON.stringify({
        action: "modify_plan",
        plan_approved: false,
        human_modifications: modifications
      }),
      id: Date.now().toString(),
    };
    
    thread.submit({
      messages: [...thread.messages, modificationMessage],
      initial_search_query_count: 3,
      max_research_loops: 3,
      reasoning_model: "gemini-1.5-pro",
    });
  }, [thread]);

  const handleQuickLookup = useCallback(() => {
    // 隐藏 HITL，直接触发后端快速查询路由
    setShowHitlApproval(false);
    setResearchPlan(null);

    const quickLookupMessage: Message = {
      type: "human",
      content: JSON.stringify({
        action: "quick_lookup"
      }),
      id: Date.now().toString(),
    };

    thread.submit({
      messages: [...thread.messages, quickLookupMessage],
      initial_search_query_count: 3,
      max_research_loops: 3,
      reasoning_model: "gemini-1.5-pro",
    });
  }, [thread]);

  return (
    <div className="flex min-h-screen bg-neutral-800 text-neutral-100 font-sans antialiased">
      <main className="h-full w-full max-w-4xl mx-auto">
          {thread.messages.length === 0 ? (
            <WelcomeScreen
              handleSubmit={handleSubmit}
              isLoading={thread.isLoading}
              onCancel={handleCancel}
            />
          ) : showHitlApproval && researchPlan ? (
            <ResearchPlanApproval
              researchPlan={researchPlan}
              onApprove={handleApproveResearchPlan}
              onModify={handleModifyResearchPlan}
              onQuickLookup={handleQuickLookup}
              isLoading={thread.isLoading}
            />
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full">
              <div className="flex flex-col items-center justify-center gap-4">
                <h1 className="text-2xl text-red-400 font-bold">Error</h1>
                <p className="text-red-400">{JSON.stringify(error)}</p>

                <Button
                  variant="destructive"
                  onClick={() => window.location.reload()}
                >
                  Retry
                </Button>
              </div>
            </div>
          ) : (
            <div>
              {showPlanCollapsed && approvedPlan && (
                <div className="px-4 pt-4">
                  <CollapsedResearchPlan researchPlan={approvedPlan} />
                </div>
              )}
              <ChatMessagesView
                messages={thread.messages}
                isLoading={thread.isLoading}
                scrollAreaRef={scrollAreaRef}
                onSubmit={handleSubmit}
                onCancel={handleCancel}
                liveActivityEvents={processedEventsTimeline}
                historicalActivities={historicalActivities}
              />
              {finalReport && (
                <div className="px-4 pb-4">
                  <EnhancedReport 
                    report={finalReport}
                    thinkingProcess={thinkingProcess}
                    sourcesGathered={sourcesGathered}
                  />
                </div>
              )}
            </div>
          )}
      </main>
    </div>
  );
}
