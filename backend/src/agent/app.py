# mypy: disable - error - code = "no-untyped-def,misc"
import os
import pathlib
import logging
from fastapi import FastAPI, Response, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
# from agent.configuration import Configuration
# from agent.rag_rest import query_user_projects, query_vendor_projects, query_rag_rest

# Import authentication routes
from src.auth.routes import auth_router
from src.auth.token_validator import TokenValidator

# Define the FastAPI app
app = FastAPI()

# Read authentication configuration from environment
ENABLE_DEFAULT_USER = os.getenv("ENABLE_DEFAULT_USER", "false").lower() == "true"

# Initialize security and token validator
security = HTTPBearer(auto_error=False)  # 设置auto_error=False以便在认证禁用时处理
token_validator = TokenValidator()

# Authentication dependency
async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """验证token的依赖函数"""
    # 默认用户信息
    default_user = {
        "user_id": "default_user",
        "username": "anonymous",
        "email": "anonymous@example.com"
    }
    
    # 始终尝试获取用户信息
    user_info = None
    token = credentials.credentials if credentials else None
    logging.info(f"请求头中的token: {token}")
    
    if token:
        user_info = await token_validator.validate_token_async(token)
        logging.info(f"用户认证信息: {user_info}")

        if user_info:
            # 记录成功获取的用户信息（不包含敏感信息）
            safe_user_info = {
                "user_id": user_info.id,
                "username": user_info.name,
                "email": user_info.email
            }
            logging.info(f"用户认证成功: {safe_user_info}")
    else:
        logging.info("未提供token，将根据ENABLE_DEFAULT_USER设置处理")
    
    # 根据ENABLE_DEFAULT_USER决定返回逻辑
    if not ENABLE_DEFAULT_USER:
        # 启用默认用户模式：始终返回用户信息（优先返回真实用户信息，否则返回默认用户）
        if user_info:
            return user_info
        else:
            logging.info(f"启用默认用户模式，使用默认用户信息: {default_user}")
            return default_user
    else:
        # 严格认证模式：必须有有效token才能通过
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        if not user_info:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_info

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication middleware for stream requests only
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """认证中间件，根据环境变量控制是否启用认证"""
    # 跳过认证路由和静态文件
    if (
        request.url.path.startswith("/api/auth/") or 
        request.url.path.startswith("/app/") or
        request.url.path == "/" or
        request.url.path.startswith("/docs") or
        request.url.path.startswith("/redoc") or
        request.url.path.startswith("/openapi.json")
    ):
        response = await call_next(request)
        return response
    
    # 只对stream相关接口进行token验证
    if "stream" not in request.url.path.lower():
        # 非stream接口直接通过，不进行认证
        response = await call_next(request)
        return response
    
    # 检查Authorization头（仅对stream接口）
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        # 如果启用默认用户模式，即使没有token也继续处理请求
        if not ENABLE_DEFAULT_USER:
            response = await call_next(request)
            return response
        return Response(
            content='{"detail":"缺少认证token"}',
            status_code=401,
            media_type="application/json"
        )
    
    # 获取用户信息逻辑：调用token验证器获取用户信息
    try:
        token = auth_header.split(" ")[1]
        # 调用token验证器获取用户信息
        user_info = await token_validator.validate_token_async(token)
        if user_info:
            # 记录成功获取的用户信息（不包含敏感信息）
            logging.info(f"Stream接口获取到用户信息: 用户ID={user_info.id}, 用户名={user_info.name}, 邮箱={user_info.email}")
            # 将用户信息存储到request.state中供后续使用
            request.state.user = user_info
        else:
            logging.warning(f"Stream接口token验证失败，未获取到用户信息")
            # 根据ENABLE_DEFAULT_USER开关决定处理逻辑
            if ENABLE_DEFAULT_USER:
                return Response(
                    content='{"detail":"token验证失败"}',
                    status_code=401,
                    media_type="application/json"
                )
            else:
                # 启用默认用户模式，设置默认用户信息
                default_user = {"id": "default", "username": "default_user", "email": "default@example.com"}
                request.state.user = default_user
                logging.info(f"启用默认用户模式，使用默认用户信息")
    except Exception as e:
        logging.warning(f"Stream接口token验证异常: {str(e)}")
        # 根据ENABLE_DEFAULT_USER开关决定处理逻辑
        if ENABLE_DEFAULT_USER:
            return Response(
                content='{"detail":"token验证异常"}',
                status_code=401,
                media_type="application/json"
            )
        else:
            # 启用默认用户模式，设置默认用户信息
            default_user = {"id": "default", "username": "default_user", "email": "default@example.com"}
            request.state.user = default_user
            logging.info(f"启用默认用户模式，忽略token验证异常，使用默认用户信息")
    
    response = await call_next(request)
    logging.info(f"Stream接口处理完成，响应状态码: {response.status_code}")

    return response

# Register authentication routes
app.include_router(auth_router)

# User info endpoint
@app.get("/user-info")
async def get_user_info(user_info: dict = Depends(verify_token)):
    """获取当前用户信息"""
    return {
        "success": True,
        "data": user_info,
        "message": "用户信息获取成功"
    }


def create_frontend_router(build_dir="../frontend/dist"):
    """Creates a router to serve the React frontend.

    Args:
        build_dir: Path to the React build directory relative to this file.

    Returns:
        A Starlette application serving the frontend.
    """
    build_path = pathlib.Path(__file__).parent.parent.parent / build_dir

    if not build_path.is_dir() or not (build_path / "index.html").is_file():
        print(
            f"WARN: Frontend build directory not found or incomplete at {build_path}. Serving frontend will likely fail."
        )
        # Return a dummy router if build isn't ready
        from starlette.routing import Route

        async def dummy_frontend(request):
            return Response(
                "Frontend not built. Run 'npm run build' in the frontend directory.",
                media_type="text/plain",
                status_code=503,
            )

        return Route("/{path:path}", endpoint=dummy_frontend)

    return StaticFiles(directory=build_path, html=True)


# Mount the frontend under /app to not conflict with the LangGraph API routes
app.mount(
    "/app",
    create_frontend_router(),
    name="frontend",
)


# # Simple REST endpoint to fetch vendor projects from local mock/REST-backed RAG (backward compatible)
# @app.get("/api/vendor-projects")
# async def get_vendor_projects(vendor: str, top_k: int = 3):
#     """Return top-K recent projects for a given vendor username. Backward compatible alias.

#     Query params:
#     - vendor: 供应商/用户名称（必填，支持部分匹配）
#     - top_k: 返回项目数量（默认3）
#     """
#     if not vendor or not vendor.strip():
#         raise HTTPException(status_code=400, detail="Query parameter 'vendor' is required")

#     configurable = Configuration.from_runnable_config()
#     local_json = getattr(configurable, "rag_rest_local_json", "backend/examples/vendor_projects.json")
#     # call new API under the hood for consistency
#     items = query_user_projects(user_name=vendor, local_json=local_json, top_k=top_k)
#     return items


# # New canonical endpoint for user projects
# @app.get("/api/user-projects")
# async def get_user_projects(user: str | None = None, top_k: int = 3, name: str | None = None, vendor: str | None = None):
#     """Return top-K recent projects for a given user name.

#     Query params (兼容旧字段):
#     - user/name/vendor: 用户/供应商名称（至少提供一个）
#     - top_k: 返回项目数量（默认3）
#     """
#     q = (user or name or vendor or "").strip()
#     if not q:
#         raise HTTPException(status_code=400, detail="One of 'user', 'name', or 'vendor' query params is required")

#     configurable = Configuration.from_runnable_config()
#     local_json = getattr(configurable, "rag_rest_local_json", "backend/examples/vendor_projects.json")
#     items = query_user_projects(user_name=q, local_json=local_json, top_k=top_k)
#     return items


# # --- Quick lookup: combine (REST/local) RAG hits with a lightweight Gemini synthesis ---
# def _gemini_quick_answer(question: str, hits: list[dict], model_name: str) -> str:
#     """Generate a brief answer using Gemini with provided local/REST RAG hits as context.

#     Returns empty string if GEMINI_API_KEY is missing or generation fails (best-effort, non-blocking).
#     """
#     try:
#         api_key = os.environ.get("GEMINI_API_KEY", "").strip()
#         if not api_key:
#             return ""
#         # Normalize model name for the google-genai SDK
#         model = model_name or "models/gemini-2.5-flash-lite"
#         if not model.startswith("models/"):
#             model = f"models/{model}"

#         try:
#             from google import genai  # lazy import to avoid import-time errors if package missing
#         except Exception:
#             return ""

#         client = genai.Client(api_key=api_key)
#         ctx_lines = []
#         for h in hits[:5]:
#             # keep context concise
#             ctx_lines.append(f"- {h.get('text','')}")
#         context = "\n".join(ctx_lines)
#         user_prompt = (
#             "你是一个快速直查助手。请基于以下内部RAG线索，结合常识，用简洁要点回答用户问题；"
#             "若信息不足请如实说明，不要虚构来源。\n\n"
#             f"[问题]\n{question}\n\n[内部线索]\n{context}\n"
#         )
#         resp = client.models.generate_content(
#             model=model,
#             contents=[{"role": "user", "parts": [{"text": user_prompt}]}],
#         )
#         text = getattr(resp, "text", None)
#         return text or ""
#     except Exception:
#         return ""


# @app.get("/api/quick-lookup")
# async def quick_lookup(q: str, top_k: int = 3):
#     """Direct lookup endpoint that bypasses research/HITL.

#     - Retrieves top-K hits via RAG REST if configured, otherwise falls back to local JSON mock.
#     - Optionally synthesizes a concise answer with Gemini using the hits as context.
#     """
#     if not q or not q.strip():
#         raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

#     cfg = Configuration.from_runnable_config()
#     endpoint = getattr(cfg, "rag_rest_endpoint", None)
#     api_key = getattr(cfg, "rag_rest_api_key", None)
#     timeout = int(getattr(cfg, "rag_rest_timeout", 8) or 8)
#     local_json = getattr(cfg, "rag_rest_local_json", "backend/examples/vendor_projects.json")

#     # Always use query_rag_rest: it will fallback to local JSON if endpoint is missing or fails
#     hits = query_rag_rest(
#         query=q,
#         endpoint=endpoint,
#         api_key=api_key,
#         timeout=timeout,
#         local_json=local_json,
#         top_k=top_k,
#     )

#     # Best-effort LLM synthesis (non-blocking if missing)
#     model_for_answer = getattr(cfg, "answer_model", "models/gemini-2.5-flash-lite")
#     answer = _gemini_quick_answer(q, hits, model_for_answer)

#     return {
#         "question": q,
#         "hits": hits,
#         "answer": answer,
#         "model": (f"models/{model_for_answer}" if not str(model_for_answer).startswith("models/") else model_for_answer),
#         "source": {"rest": endpoint or None, "local_json": local_json},
#     }
