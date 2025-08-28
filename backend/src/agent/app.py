# mypy: disable - error - code = "no-untyped-def,misc"
import os
import pathlib
from fastapi import FastAPI, Response, HTTPException
from fastapi.staticfiles import StaticFiles
# from agent.configuration import Configuration
# from agent.rag_rest import query_user_projects, query_vendor_projects, query_rag_rest

# Define the FastAPI app
app = FastAPI()


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
