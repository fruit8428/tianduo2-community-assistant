import re
from typing import List, Dict, Any
from condo_rag_agent.config import TOP_K_LOCAL_SEARCH
from condo_rag_agent.pdf_indexer import build_or_get_chroma_collection

_collection = None

def get_chroma_collection():
    global _collection
    if _collection is None:
        _collection = build_or_get_chroma_collection(force_rebuild=False)
    return _collection

def retrieve_condo_docs(query: str, top_k: int = TOP_K_LOCAL_SEARCH) -> Dict[str, Any]:
    """
    本地文件檢索工具 (ChromaDB Vector Store Retriever)
    結合語意向量檢索與法規條號精確匹配（Hybrid Search）
    """
    col = get_chroma_collection()
    clean_q = query.strip()

    # 1. 檢查是否有特定條號指定（例如：第16條、§16、16條、第四十九條）
    exact_matches = []
    art_nums = re.findall(r'(?:第|§)?\s*(\d+(?:-\d+)?)\s*條?', clean_q)
    
    # 支援中文數字轉換 (例如第四十九條、第八條)
    cn_num_map = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5', '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
                  '十一': '11', '十二': '12', '十三': '13', '十四': '14', '十五': '15', '十六': '16', '十七': '17', '十八': '18',
                  '十九': '19', '二十': '20', '二十一': '21', '二十二': '22', '二十三': '23', '三十一': '31', '四十九': '49'}
    for cn_k, ar_v in cn_num_map.items():
        if f"第{cn_k}條" in clean_q or f"{cn_k}條" in clean_q:
            art_nums.append(ar_v)

    if art_nums:
        for num in set(art_nums):
            try:
                item = col.get(ids=[f"condo_art_{num}"])
                if item and item.get("documents") and len(item["documents"]) > 0:
                    exact_matches.append({
                        "id": item["ids"][0],
                        "title": item["metadatas"][0].get("title", f"第 {num} 條"),
                        "chapter": item["metadatas"][0].get("chapter", "法定規範"),
                        "keywords": item["metadatas"][0].get("keywords", ""),
                        "content": item["documents"][0],
                        "score": 1.0,
                        "match_type": "exact_article"
                    })
            except Exception:
                pass

    # 2. 語意向量檢索 (Semantic Vector Query)
    res = col.query(
        query_texts=[clean_q],
        n_results=top_k
    )

    semantic_matches = []
    if res and res.get("documents") and len(res["documents"]) > 0:
        docs = res["documents"][0]
        metas = res["metadatas"][0] if res.get("metadatas") else [{}] * len(docs)
        ids = res["ids"][0] if res.get("ids") else [""] * len(docs)
        distances = res["distances"][0] if res.get("distances") else [0.0] * len(docs)

        for doc, meta, doc_id, dist in zip(docs, metas, ids, distances):
            # 轉換距離為相似度指標 (距離越小相似度越高)
            similarity = max(0.0, min(1.0, 1.0 - (dist / 2.0)))
            # 避免與完全匹配重複
            if not any(em["id"] == doc_id for em in exact_matches):
                semantic_matches.append({
                    "id": doc_id,
                    "title": meta.get("title", ""),
                    "chapter": meta.get("chapter", ""),
                    "keywords": meta.get("keywords", ""),
                    "content": doc,
                    "score": round(similarity, 3),
                    "match_type": "semantic"
                })

    all_docs = exact_matches + semantic_matches

    # 組合格式化 context
    context_blocks = []
    for idx, d in enumerate(all_docs, 1):
        context_blocks.append(
            f"【條文依據 {idx}】{d['title']} ({d['chapter']}) [匹配模式: {d['match_type']}, 相關性評分: {d['score']}]\n{d['content']}"
        )

    context_text = "\n\n".join(context_blocks)

    return {
        "query": clean_q,
        "source": "ChromaDB 本地法規向量庫",
        "documents": all_docs,
        "context_text": context_text,
        "is_empty": len(all_docs) == 0,
        "top_score": all_docs[0]["score"] if all_docs else 0.0
    }

if __name__ == "__main__":
    test_q = "住戶可以在梯廳放鞋架或鞋櫃嗎？"
    out = retrieve_condo_docs(test_q)
    print(f"Query: {test_q}")
    print(f"Retrieved {len(out['documents'])} docs. Top score: {out['top_score']}")
    print(out["context_text"][:300] + "...")
