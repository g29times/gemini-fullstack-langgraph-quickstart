# Gemini Fullstack LangGraph 项目报告

## 📋 项目概述

这是一个基于 **Google Gemini** 和 **LangGraph** 的全栈智能研究助手项目，展示了如何构建一个能够进行深度网络研究的对话式AI应用。

## 🏗️ 项目架构

### **前端 (React)**
- **技术栈**: React 19 + TypeScript + Vite + Tailwind CSS 4.x
- **UI组件**: Shadcn UI + Radix UI
- **核心功能**: 
  - 实时流式对话界面
  - 研究过程可视化时间线
  - 多种研究强度设置（低/中/高）
  - 响应式设计

### **后端 (Python)**
- **核心框架**: LangGraph + FastAPI
- **AI模型**: Google Gemini 2.0/2.5 Flash, Gemini 2.5 Pro
- **主要依赖**:
  - `langgraph>=0.2.6` - 状态图工作流
  - `langchain-google-genai` - Gemini集成
  - `google-genai` - 原生Google AI客户端

## 🤖 智能代理工作流程

项目的核心是一个基于LangGraph的多步骤研究代理，工作流程如下：

### 1. **查询生成** ([generate_query](cci:1://file:///m:/WorkSpace/AI/Agents/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:43:0-80:41))
- 基于用户问题生成多个优化的搜索查询
- 使用Gemini 2.0 Flash进行结构化输出

### 2. **并行网络研究** ([web_research](cci:1://file:///m:/WorkSpace/AI/Agents/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:94:0-135:5))
- 使用Google Search API进行并行搜索
- 每个查询独立执行，提高效率
- 自动解析URL并提取引用信息

### 3. **反思分析** ([reflection](cci:1://file:///m:/WorkSpace/AI/Agents/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:138:0-179:5))
- 分析搜索结果，识别知识缺口
- 决定是否需要进一步研究
- 生成后续查询建议

### 4. **迭代优化** ([evaluate_research](cci:1://file:///m:/WorkSpace/AI/Agents/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:182:0-216:9))
- 根据配置的最大循环次数控制研究深度
- 动态决定继续搜索或结束研究

### 5. **答案合成** ([finalize_answer](cci:1://file:///m:/WorkSpace/AI/Agents/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:219:0-264:5))
- 整合所有研究结果
- 生成带有准确引用的最终答案

## 🛠️ 技术特点

### **LangGraph状态管理**
- 使用`OverallState`统一管理整个工作流状态
- 支持并行节点执行和条件路由
- 状态持久化到PostgreSQL

### **多模型支持**
- 查询生成: Gemini 2.0 Flash (高速)
- 反思推理: Gemini 2.5 Pro (深度思考)
- 答案合成: 可配置模型选择

### **实时流式处理**
- 前端使用`@langchain/langgraph-sdk/react`
- 支持实时显示研究进度
- WebSocket连接保持状态同步

## 🚀 部署方案

### **开发环境**
```bash
# 后端
cd backend && langgraph dev

# 前端  
cd frontend && npm run dev

# 或使用Makefile
make dev
```

### **生产环境**
- **容器化**: 多阶段Docker构建
- **数据库**: PostgreSQL (状态存储) + Redis (消息队列)
- **服务编排**: Docker Compose
- **API端点**: 统一在8123端口提供服务

## 📁 项目结构

```
├── frontend/          # React前端应用
│   ├── src/
│   │   ├── components/    # UI组件
│   │   └── App.tsx       # 主应用组件
│   └── package.json
├── backend/           # Python后端
│   ├── src/agent/        # 核心代理逻辑
│   │   ├── graph.py      # LangGraph工作流定义
│   │   ├── state.py      # 状态模型
│   │   └── prompts.py    # 提示词模板
│   └── examples/         # CLI示例
└── docker-compose.yml    # 生产部署配置
```

## 🎯 核心优势

1. **智能研究能力**: 自动识别知识缺口并迭代优化搜索
2. **实时交互体验**: 流式显示研究过程，用户体验流畅
3. **高度可配置**: 支持调整研究深度、模型选择等参数
4. **生产就绪**: 完整的容器化部署方案
5. **可扩展架构**: 基于LangGraph的模块化设计

## 💡 使用场景

- 学术研究辅助
- 市场调研分析  
- 技术文档整理
- 新闻事件追踪
- 产品竞品分析

这个项目展示了现代AI应用开发的最佳实践，结合了最新的LLM技术、工作流编排和全栈开发技术，是学习和构建智能研究助手的优秀参考案例。