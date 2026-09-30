import os
from pathlib import Path

# 專案路徑設定
BASE_DIR = Path(__file__).resolve().parent.parent
PDF_PATH = BASE_DIR / "公寓大廈管理條例.pdf"
CHROMA_PERSIST_DIR = BASE_DIR / "chroma_db_condo"
COLLECTION_NAME = "condo_regulations"

# Agent 參數設定
MAX_REFLECTION_RETRIES = 2       # 反思與改寫關鍵字最大重試次數
TOP_K_LOCAL_SEARCH = 3           # 本地向量資料庫召回條文數
TOP_K_WEB_SEARCH = 3             # 網路檢索結果召回數
RELEVANCE_THRESHOLD = 0.5        # 檢索相關性通過門檻

# 路由判定關鍵字清單
WEB_SEARCH_INDICATORS = [
    "最新判例", "法院判決", "判決", "判例", "裁判書", "大法官",
    "新聞", "近期案例", "營建署函釋", "國土署函釋", "行政函釋", "內政部解釋",
    "外面社區", "其他社區", "新聞報導", "實務見解", "訴訟", "提告"
]

LOCAL_DOC_INDICATORS = [
    "條例", "第幾條", "規定", "法定", "規約", "大廈", "公設", "專有部分", "共用部分",
    "管委會", "區權會", "防墜", "鞋櫃", "走廊", "冷氣", "充電樁", "管理費",
    "催繳", "寵物", "修繕", "主委", "財委", "監委", "會議", "門檻", "住戶"
]
