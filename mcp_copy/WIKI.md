# MCP 服务器开发文档
## 安装环境
conda create -n mcp python=3.11 或 使用IDE自动创建
conda activate M:\AIGC\LLM_backend\MCP\Demo\.conda
pip install google-genai mcp "mcp[cli]"

## 开发
todo_server.py
    `mcp.run(transport="["stdio", "sse", "streamable-http"]")`
### 三种运行模式
1 本地输入输出流（个人电脑开发用，不支持互联网）STDIO
2 SSE模式
3 流模式

## 运行/调试
首先确认conda环境已激活
`conda info`
(M:\WorkSpace\AI\LLM_backend\MCP\Demo\.conda) 
### 服务端
本地模式(开发)
    mcp run todo_server.py
sse模式(部署)
    `M:/AIGC/LLM_backend/MCP/Demo/.conda/python M:/AIGC/LLM_backend/MCP/Demo/todo_server.py`

### 客户端
mcp dev todo_server.py
访问地址：http://127.0.0.1:6274/#tools
    本地
        Transport Type: STDIO
        Command: uv
        Args: run --with mcp mcp run ./todo_server.py
    SSE
        Transport Type: SSE
        URL: http://localhost:8000/sse
windsurf/codieum:
    本地
        "command": "M:/AIGC/LLM_backend/MCP/Demo/.conda/python",
        "args": ["M:/AIGC/LLM_backend/MCP/Demo/todo_server.py"]
    SSE
        "serverUrl": "http://localhost:8000/sse"

## 部署

## 参考文档
官方
https://modelcontextprotocol.io/quickstart/client#troubleshooting
主要入门参考
https://www.ridgerun.ai/post/how-to-write-your-mcp-server-in-python
进阶参考（如何调试 dev）
https://scrapfly.io/blog/how-to-build-an-mcp-server-in-python-a-complete-guide/

### 生产级MCP服务示例
mem0
https://app.mem0.ai/dashboard/requests?page=1
https://docs.mem0.ai/core-concepts/memory-operations#adding-memories
https://docs.mem0.ai/integrations/mcp-server
https://docs.mem0.ai/examples/multimodal-demo
https://github.com/mem0ai/mem0-mcp/blob/main/node/mem0/README.md
本地部署 https://docs.mem0.ai/openmemory/quickstart#getting-started

google
https://cloud.google.com/blog/products/ai-machine-learning/build-mcp-servers-using-vibe-coding-with-gemini-2-5-pro
主要参考：https://medium.com/google-cloud/model-context-protocol-mcp-with-google-gemini-llm-a-deep-dive-full-code-ea16e3fac9a3

Ollama webui MCP集成
https://docs.openwebui.com/openapi-servers/mcp/#-quickstart-running-the-proxy-locally