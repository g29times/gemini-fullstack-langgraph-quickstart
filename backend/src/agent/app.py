# mypy: disable - error - code = "no-untyped-def,misc"
import json
import os
import pathlib
import logging
import httpx
from fastapi import FastAPI, Response, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
# from agent.configuration import Configuration
# from agent.rag_rest import query_user_projects, query_vendor_projects, query_rag_rest

# Import authentication routes
from src.auth.routes import auth_router
from src.auth.token_validator import TokenValidator
import requests
from bs4 import BeautifulSoup

# Define the FastAPI app
app = FastAPI()

# Hardcoded authentication configuration
ENABLE_DEFAULT_USER = False
DEFAULT_INSTITUTION_ID = 1

# Initialize security and token validator
security = HTTPBearer(auto_error=False)  # 设置auto_error=False以便在认证禁用时处理
token_validator = TokenValidator()

# Authentication dependency
async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """验证token的依赖函数"""
    # 默认用户信息
    default_user = {
        "user_id": "anonymous",
        "username": "anonymous",
        "email": "anonymous@example.com"
    }
    
    # 始终尝试获取用户信息
    user_info = None
    token = credentials.credentials if credentials else None
    logging.info(f"请求头中的token: {token}")
    
    if token:
        user_info = await token_validator.validate_token_async(token)
        logging.info(f"用户认证信息: {json.dumps(user_info)}")

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

# Custom middleware to inject user info into LangGraph configurable parameters
class UserInfoMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 先处理请求，让认证中间件设置用户信息
        response = await call_next(request)
        return response

# Add the user info middleware
app.add_middleware(UserInfoMiddleware)

# Authentication and user info injection middleware
@app.middleware("http")
async def auth_and_user_info_middleware(request: Request, call_next):
    """认证中间件，同时处理用户信息注入到LangGraph请求"""
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
    
    # 获取用户信息（对所有请求）
    user_id = None
    user_name = None
    user_institution = None
    # 检查Authorization头
    auth_header = request.headers.get("authorization")
    # 当前机构id存储到request.state中
    request.state.user_institution = request.headers.get("institution-identification", DEFAULT_INSTITUTION_ID)

    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            # 调用token验证器获取用户信息
            user_info = await token_validator.validate_token_async(token)
            if user_info:
                user_id = user_info.id
                user_name = user_info.name
                user_institution = request.state.user_institution
                logging.info(f"获取到用户信息: token={token}, 用户ID={user_id}, 用户名={user_name}, 机构={user_institution}")
                # 将用户信息存储到request.state中
                request.state.user_id = user_id
                request.state.user_name = user_name
                request.state.token = token
            else:
                logging.warning("token验证失败，未获取到用户信息")
        except Exception as e:
            logging.warning(f"token验证异常: {str(e)}")
    
    # 如果没有获取到用户信息，使用默认用户（当ENABLE_DEFAULT_USER=False时）
    if not user_id and not ENABLE_DEFAULT_USER:
        user_id = "default"
        user_name = "default_user"
        token = os.getenv("RAG_REST_API_KEY")
        request.state.user_id = user_id
        request.state.user_name = user_name
        request.state.token = token
        logging.info(f"使用默认用户信息: token={token}, user_id={user_id}, user_name={user_name}")
    
    # 检查是否是LangGraph API请求，如果是则注入用户信息
    if (
        "stream" in request.url.path.lower()
    ):
        if user_id or user_name:
            # 读取请求体
            body = await request.body()
            
            if body:
                try:
                    # 解析JSON请求体
                    data = json.loads(body.decode('utf-8'))
                    
                    # 注入用户信息到configurable
                    if 'config' not in data:
                        data['config'] = {}
                    if 'configurable' not in data['config']:
                        data['config']['configurable'] = {}
                    
                    # 添加用户信息到configurable
                    user_info_dict = {}
                    if token:
                        user_info_dict['token'] = token
                    if user_id:
                        user_info_dict['id'] = user_id
                    if user_name:
                        user_info_dict['name'] = user_name
                    if user_institution:
                        user_info_dict['institution'] = user_institution
                    
                    data['config']['configurable']['user_info'] = user_info_dict
                    
                    # 修改请求体
                    modified_body = json.dumps(data).encode('utf-8')
                    request._body = modified_body
                    
                    logging.info(f"注入用户信息到LangGraph请求: token={token}, user_id={user_id}, user_name={user_name}")
                    
                except json.JSONDecodeError:
                    logging.warning("无法解析LangGraph请求体JSON")
                except Exception as e:
                    logging.error(f"处理LangGraph请求时出错: {str(e)}")
    
    # 对stream接口进行额外的认证检查
    if "stream" in request.url.path.lower():
        if not auth_header or not auth_header.startswith("Bearer "):
            if ENABLE_DEFAULT_USER:
                return Response(
                    content='{"detail":"缺少认证token"}',
                    status_code=401,
                    media_type="application/json"
                )
        
        if not user_id and ENABLE_DEFAULT_USER:
            return Response(
                content='{"detail":"token验证失败"}',
                status_code=401,
                media_type="application/json"
            )
    
    response = await call_next(request)
    return response

# Register authentication routes
app.include_router(auth_router)


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


class CheckURL:
    def get_context(self,url):
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }

        cookies = {
            "JIDENTITY": "71101c5d-89b9-484c-a727-1fbfcd66c43a",
            "_site_id_cookie": "1",
            "Hm_lvt_ddd51655888df4f02c24c55810416e80": "1760333757,1760348386",
            "HMACCOUNT": "2C207121D0F343AB",
            "Hm_lpvt_ddd51655888df4f02c24c55810416e80": "1760421929",
            "JSESSIONID": "50B6A9C45B284BE76E8CA02CAAD31865"
        }

        response = requests.get(url, headers=headers, cookies=cookies)

        res = response.text

        soup = BeautifulSoup(res, 'html.parser')

        content_div = soup.select_one("div.content")

        if content_div:
            # 获取纯文本，strip=True 去掉多余空格和换行
            text = content_div.get_text(separator="\n", strip=True).replace("\n", "    ")
            return text


    def main(self,url):
        if "https://www.shggzy.com" in url:
            context = self.get_context(url)
            if context==None:
                return "https://www.shggzy.com/jyxxgc"
            else:
                return url
        else:
            return url



@app.post("/checkurl")
async def checkurl(req: dict):
    try:
        res=CheckURL().main(req['url'])
        return {
            "status_code": 0,
            "data":res
        }
    except Exception as e:
        print(e)
        return {
            "status_code": 1,
            "error": e,
        }