import re
import os
from pathlib import Path
import pypdf
import chromadb
from condo_rag_agent.config import PDF_PATH, CHROMA_PERSIST_DIR, COLLECTION_NAME

def extract_articles_from_pdf(pdf_path: Path):
    """
    從《公寓大廈管理條例.pdf》解析所有章節與條文，保留結構化元數據
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"找不到指定的法規 PDF: {pdf_path}")

    reader = pypdf.PdfReader(str(pdf_path))
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    # 章節標記對照
    chapter_map = {
        1: "第 一 章 總則",
        2: "第 二 章 住戶之權利義務",
        3: "第 三 章 管理組織",
        4: "第 四 章 管理服務人",
        5: "第 五 章 罰則",
        6: "第 六 章 附則"
    }

    # 依「第 X 條」切分條文
    raw_articles = re.split(r'\n(?=第\s*\d+(?:-\d+)?\s*條)', full_text)
    documents = []

    current_chapter = "第 一 章 總則"
    for part in raw_articles:
        lines = [l.strip() for l in part.strip().split('\n') if l.strip()]
        if not lines:
            continue

        # 檢查章節更換
        for ch_num, ch_title in chapter_map.items():
            if ch_title.replace(" ", "") in part.replace(" ", ""):
                current_chapter = ch_title

        # 條號匹配
        m = re.match(r'^第\s*(\d+(?:-\d+)?)\s*條', lines[0])
        if not m:
            continue

        art_num = m.group(1)
        art_title = f"第 {art_num} 條"
        content = "\n".join(lines)

        # 提煉條文核心關鍵字（加強語意檢索特徵）
        keywords = []
        if any(w in content for w in ["走廊", "樓梯", "雜物", "通道", "門扉", "柵欄", "防火"]):
            keywords.extend(["走廊雜物", "鞋櫃", "避難通道", "防空避難"])
        if any(w in content for w in ["防墜", "外牆", "開口部", "陽臺", "老人", "兒童"]):
            keywords.extend(["防墜設施", "兒童防墜", "老人防墜", "隱形鐵窗"])
        if any(w in content for w in ["冷氣", "構造", "顏色", "外觀", "廣告物", "滴水"]):
            keywords.extend(["冷氣外機", "大樓外觀", "外牆懸掛"])
        if any(w in content for w in ["管理費", "公共基金", "繳納", "催討", "存證信函", "支付命令"]):
            keywords.extend(["管理費催繳", "欠繳二期", "強制執行", "規約罰則"])
        if any(w in content for w in ["區分所有權人會議", "開會", "出席", "決議", "表決權"]):
            keywords.extend(["區權會門檻", "假決議", "會議程序", "委託書"])
        if any(w in content for w in ["管委會", "管理委員會", "主任委員", "管理負責人"]):
            keywords.extend(["管委會權限", "主委職責", "修繕管理"])
        if any(w in content for w in ["罰鍰", "處罰", "主管機關", "改善"]):
            keywords.extend(["主管機關裁罰", "四萬至二十萬", "連續處罰"])

        doc_text = f"【公寓大廈管理條例 {art_title}】\n章節：{current_chapter}\n內容：{content}"

        documents.append({
            "id": f"condo_art_{art_num}",
            "article_num": art_num,
            "chapter": current_chapter,
            "title": art_title,
            "content": content,
            "full_document": doc_text,
            "keywords": ", ".join(keywords) if keywords else "法定規範"
        })

    return documents

def build_or_get_chroma_collection(force_rebuild: bool = False):
    """
    建立或取得 ChromaDB 向量庫，確保持久化存在
    """
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))

    if force_rebuild:
        try:
            client.delete_collection(name=COLLECTION_NAME)
        except Exception:
            pass

    col = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "中華民國《公寓大廈管理條例》法定法規向量知識庫"}
    )

    # 檢查是否已建置
    if col.count() == 0 or force_rebuild:
        print(f"[*] 正在從 PDF 解析《公寓大廈管理條例》全文：{PDF_PATH}")
        articles = extract_articles_from_pdf(PDF_PATH)
        print(f"[*] 解析完成，共獲得 {len(articles)} 條法律條文，開始向量化索引至 ChromaDB...")

        ids = [doc["id"] for doc in articles]
        docs = [doc["full_document"] for doc in articles]
        metadatas = [{
            "article_num": doc["article_num"],
            "chapter": doc["chapter"],
            "title": doc["title"],
            "keywords": doc["keywords"],
            "source": "公寓大廈管理條例.pdf"
        } for doc in articles]

        col.add(
            ids=ids,
            documents=docs,
            metadatas=metadatas
        )
        print(f"[+] 向量庫建立完成！目前 ChromaDB 收錄條文總數: {col.count()} 筆")
    else:
        print(f"[+] ChromaDB 向量庫已就緒，收錄條文數: {col.count()} 筆")

    return col

if __name__ == "__main__":
    col = build_or_get_chroma_collection(force_rebuild=True)
    print("Test retrieval:")
    res = col.query(query_texts=["走廊能放鞋櫃嗎？"], n_results=2)
    for i, (doc, meta) in enumerate(zip(res['documents'][0], res['metadatas'][0])):
        print(f"[{i+1}] {meta['title']} ({meta['chapter']}):\n{doc[:120]}...\n")
