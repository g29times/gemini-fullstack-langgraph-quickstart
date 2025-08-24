# import os
# import glob
# import re
# import math
# from typing import List, Dict, Tuple
# from collections import Counter, defaultdict

# # Simple TF-IDF over local markdown knowledge base for mocking RAG
# # Corpus default: WIKI/**/*.md at repository root (configurable via caller)

# try:
#     import regex as _rx
#     _TOKEN_RE = _rx.compile(r"[\p{L}\p{N}_]+")
# except Exception:
#     # Fallback: ASCII word tokens using Python's 're'
#     _TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


# def _read_text(path: str) -> str:
#     try:
#         with open(path, "r", encoding="utf-8", errors="ignore") as f:
#             return f.read()
#     except Exception:
#         return ""


# def _tokenize(text: str) -> List[str]:
#     if not text:
#         return []
#     return [t.lower() for t in _TOKEN_RE.findall(text)]


# def _split_into_chunks(text: str, chunk_size: int = 600, overlap: int = 120) -> List[Tuple[int, str]]:
#     # naive sentence-ish split to maintain readability
#     parts = re.split(r"(?<=[。！？.!?])\s+|\n{2,}", text)
#     chunks: List[Tuple[int, str]] = []
#     buf: List[str] = []
#     current = 0
#     for p in parts:
#         if not p:
#             continue
#         if sum(len(x) for x in buf) + len(p) + (len(buf) - 1) > chunk_size:
#             if buf:
#                 chunks.append((current, "\n".join(buf)))
#                 # add overlap by keeping tail
#                 tail = "\n".join(buf)[-overlap:]
#                 buf = [tail]
#                 current += 1
#         buf.append(p)
#     if buf:
#         chunks.append((current, "\n".join(buf)))
#     return chunks


# def _tfidf_rank(query: str, docs: List[Dict]) -> List[Tuple[float, Dict]]:
#     q_toks = _tokenize(query)
#     if not q_toks:
#         return []
#     q_tf = Counter(q_toks)
#     # build idf
#     df = defaultdict(int)
#     for d in docs:
#         toks = set(d.get("_tokens", []))
#         for t in toks:
#             df[t] += 1
#     N = max(1, len(docs))
#     idf = {t: math.log((N + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}

#     # query vector
#     q_vec = {t: (q_tf[t] * idf.get(t, 1.0)) for t in q_tf}

#     # score
#     scored: List[Tuple[float, Dict]] = []
#     for d in docs:
#         dv = d.get("_tfidf", {})
#         # cosine similarity
#         dot = sum(q_vec.get(t, 0.0) * dv.get(t, 0.0) for t in set(q_vec) | set(dv))
#         q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0
#         d_norm = d.get("_norm", 1.0)
#         sim = dot / (q_norm * d_norm)
#         scored.append((sim, d))
#     scored.sort(key=lambda x: x[0], reverse=True)
#     return scored


# def _prepare_docs(corpus_files: List[str]) -> List[Dict]:
#     docs: List[Dict] = []
#     for f in corpus_files:
#         text = _read_text(f)
#         if not text:
#             continue
#         for idx, chunk in _split_into_chunks(text):
#             toks = _tokenize(chunk)
#             if not toks:
#                 continue
#             tf = Counter(toks)
#             docs.append({
#                 "path": f,
#                 "chunk_index": idx,
#                 "text": chunk,
#                 "_tokens": list(tf.keys()),
#                 "_tf": tf,
#             })
#     # compute global idf and per-doc tf-idf
#     df = defaultdict(int)
#     for d in docs:
#         for t in d["_tokens"]:
#             df[t] += 1
#     N = max(1, len(docs))
#     idf = {t: math.log((N + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}
#     for d in docs:
#         tfidf = {t: (d["_tf"][t] * idf.get(t, 1.0)) for t in d["_tokens"]}
#         norm = math.sqrt(sum(v * v for v in tfidf.values())) or 1.0
#         d["_tfidf"] = tfidf
#         d["_norm"] = norm
#     return docs


# def query_rag(query: str, corpus_globs: List[str], top_k: int = 5) -> List[Dict]:
#     """
#     Mock RAG interface: accept query string and return a list of hits in a format
#     suitable for downstream synthesis.

#     Each hit dict contains:
#     - label: short label for citation (file name or stem)
#     - url: a rag-scheme URL identifying the source (rag://<stem>#<chunk_index>)
#     - path: absolute or repo-relative file path
#     - chunk_index: chunk serial number
#     - text: content snippet
#     """
#     # Expand corpus files
#     files: List[str] = []
#     for pattern in corpus_globs or []:
#         files.extend(glob.glob(pattern, recursive=True))
#     files = [f for f in files if os.path.isfile(f)]
#     if not files:
#         return []
#     docs = _prepare_docs(files)
#     ranked = _tfidf_rank(query, docs)
#     hits: List[Dict] = []
#     for score, d in ranked[: max(1, top_k)]:
#         path = d["path"]
#         stem = os.path.splitext(os.path.basename(path))[0]
#         url = f"rag://{stem}#{d['chunk_index']}"
#         hits.append({
#             "label": stem,
#             "url": url,
#             "path": path,
#             "chunk_index": d["chunk_index"],
#             "text": d["text"],
#             "score": float(score),
#         })
#     return hits
