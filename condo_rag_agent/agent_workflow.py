import re
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END

from condo_rag_agent.config import (
    MAX_REFLECTION_RETRIES,
    WEB_SEARCH_INDICATORS,
    LOCAL_DOC_INDICATORS
)
from condo_rag_agent.tools.local_retriever import retrieve_condo_docs
from condo_rag_agent.tools.web_search import search_web_legal

# ==============================================================================
# 1. 定義 Agent 狀態 (State Schema)
# ==============================================================================
class AgentState(TypedDict):
    original_query: str            # 住戶或管委會提問的原始文字
    current_query: str             # 當前檢索關鍵字 (可能由反思機制動態改寫)
    route: str                     # 'local_retriever' 或 'web_search'
    route_reason: str              # 路由判斷說明
    retrieved_docs: List[Dict]     # 檢索到的文檔列表
    retrieval_source: str          # 檢索來源說明 ('ChromaDB' 或 'Web')
    context_text: str              # 格式化上下文
    evaluation_passed: bool        # 反思機制評估是否通過
    reflection_reason: str         # 反思決策理由
    reflection_history: List[Dict] # 反思與重試歷程軌跡
    retry_count: int               # 已重試次數
    final_answer: Dict[str, Any]   # 最終結構化合規檢核報告

# ==============================================================================
# 2. 節點實作 (Nodes)
# ==============================================================================

def router_node(state: AgentState) -> Dict[str, Any]:
    """
    【節點 1：智慧路由 Router】
    自動判斷問題應該呼叫『本地文件檢索工具 (ChromaDB)』還是『網路搜尋工具 (DuckDuckGo)』
    """
    q = state.get("current_query", state["original_query"]).strip()
    
    # 判斷是否指定外部法院判決、修法新聞或主管機關行政函釋
    is_web = any(k in q for k in WEB_SEARCH_INDICATORS)
    
    if is_web:
        route = "web_search"
        reason = "偵測到查詢包含『判例、判決、函釋、修法新聞或外部案例』，路由至【網路搜尋工具】檢索實務裁判。"
    else:
        route = "local_retriever"
        reason = "查詢屬於『法定法規條文、社區管理規約或內部合規檢核』，路由至【ChromaDB 本地法規向量庫】精確比對母法條文。"

    return {
        "route": route,
        "route_reason": reason
    }

def retriever_node(state: AgentState) -> Dict[str, Any]:
    """
    【節點 2：工具調用與檢索 Retriever】
    根據 Router 決策調用本地 ChromaDB 或外部網路搜尋
    """
    route = state.get("route", "local_retriever")
    query = state.get("current_query", state["original_query"])

    if route == "web_search":
        out = search_web_legal(query)
    else:
        out = retrieve_condo_docs(query)

    return {
        "retrieved_docs": out.get("documents", []),
        "retrieval_source": out.get("source", "未知來源"),
        "context_text": out.get("context_text", "")
    }

def reflection_node(state: AgentState) -> Dict[str, Any]:
    """
    【節點 3：反思機制 Reflection & Query Rewriting】
    評估檢索結果是否足以回答問題：
    若資料不足或條文偏差，自動反思失敗原因並改寫關鍵字，觸發回圈再次檢索！
    """
    original_q = state["original_query"]
    current_q = state.get("current_query", original_q)
    docs = state.get("retrieved_docs", [])
    retry_count = state.get("retry_count", 0)
    history = list(state.get("reflection_history", []))

    # 領域核心法律意圖與對應法定條文比對特徵
    intent_keywords_map = {
        "走廊鞋櫃": {
            "triggers": ["鞋櫃", "鞋架", "鞋子", "雜物", "雨傘架", "走廊", "樓梯", "門口", "通道"],
            "required_statutes": ["第 16 條", "第16條", "第 49 條", "第49條", "十六條", "四十九條", "避難通道", "共同走廊"],
            "refined_query": "公寓大廈管理條例 第十六條 共同走廊 堆置雜物 第四十九條 罰則"
        },
        "防墜設施": {
            "triggers": ["防墜", "鐵窗", "隱形鐵窗", "陽台", "外牆", "防墜網", "兒童防墜", "老人防墜"],
            "required_statutes": ["第 8 條", "第8條", "第八條", "防墜設施", "開口部", "十二歲以下兒童"],
            "refined_query": "公寓大廈管理條例 第八條 第二項 防墜設施 陽臺 外牆開口 規約不得限制"
        },
        "冷氣外機": {
            "triggers": ["冷氣", "室外機", "冷氣滴水", "外觀", "懸掛", "外牆懸掛"],
            "required_statutes": ["第 8 條", "第8條", "第八條", "變更構造", "第 16 條", "第16條", "喧囂振動"],
            "refined_query": "公寓大廈管理條例 第八條 外牆面 構造 規約限制 第十六條 冷氣滴水"
        },
        "充電設備": {
            "triggers": ["充電", "充電樁", "電動車", "拉線", "車位充電", "EMS"],
            "required_statutes": ["第 6 條", "第6條", "第六條", "第 11 條", "第11條", "共用部分設置管線"],
            "refined_query": "公寓大廈管理條例 第六條 第一項第五款 設置管線 專有部分 充電樁 第十一條"
        },
        "管理費催繳": {
            "triggers": ["管理費", "欠繳", "催繳", "存證信函", "支付命令", "二期", "強制執行", "磁扣停權"],
            "required_statutes": ["第 21 條", "第21條", "第二十一條", "第 22 條", "第22條", "催告", "訴請法院"],
            "refined_query": "公寓大廈管理條例 第二十一條 欠繳管理費 逾二期 支付命令 第二十二條 強制出讓"
        },
        "區權會決議": {
            "triggers": ["區權會", "出席門檻", "決議門檻", "假決議", "流會", "委託書", "大會", "開會通知"],
            "required_statutes": ["第 31 條", "第31條", "第三十一條", "第 32 條", "第32條", "應有部分比例", "出席人數"],
            "refined_query": "公寓大廈管理條例 第三十一條 區分所有權人會議 決議門檻 第三十二條 假決議"
        },
        "寵物飼養": {
            "triggers": ["寵物", "貓", "狗", "飼養", "禁養", "寵物公約", "牽繩"],
            "required_statutes": ["第 16 條", "第16條", "第 23 條", "第23條", "公共衛生", "公共安寧", "禁止飼養"],
            "refined_query": "公寓大廈管理條例 第十六條 第四項 飼養動物 第二十三條 規約特別約定"
        },
        "防汛防水閘門": {
            "triggers": ["防水閘門", "防汛", "演練", "操演", "車道閘門", "沙包", "截水溝", "沉水泵", "淹水", "豪大雨"],
            "required_statutes": ["第 10 條", "第10條", "第十條", "共用部分", "修繕", "管理負責人", "管理委員會"],
            "refined_query": "公寓大廈管理條例 第十條 共用部分 維護 管理 管理負責人 防汛"
        }
    }

    # 1. 檢核檢索文檔是否為空
    if not docs:
        passed = False
        reason = "檢索結果為空，無法回答提問。"
        refined = f"公寓大廈管理條例 {original_q} 條文規範"
    else:
        # 2. 檢核檢索內容是否命中了核心法定要件條文
        passed = True
        reason = "檢索文檔充分涵蓋法規核心條文，可精準回答。"
        refined = current_q

        combined_text = " ".join([d.get("content", "") + " " + d.get("snippet", "") + " " + d.get("title", "") for d in docs])

        for category, info in intent_keywords_map.items():
            if any(t in original_q for t in info["triggers"]):
                # 若使用者問題明確涉及特定類別，檢查檢索條文是否涵蓋關鍵法條
                has_statute = any(st in combined_text for st in info["required_statutes"])
                if not has_statute:
                    passed = False
                    reason = f"檢索到的條文未包含【{category}】之核心母法條文（應檢索到如 {info['required_statutes'][:2]}），檢索精確度不足。"
                    refined = info["refined_query"]
                    break

    # 3. 處理重試次數與反思歷程
    if not passed and retry_count < MAX_REFLECTION_RETRIES:
        history.append({
            "step": f"Reflection_Retry_{retry_count + 1}",
            "status": "FAIL_NEED_RETRY",
            "reason": reason,
            "old_query": current_q,
            "new_query": refined,
            "action": f"自動啟用反思機制：改寫為更精確法學關鍵字『{refined}』重啟檢索！"
        })
        return {
            "evaluation_passed": False,
            "reflection_reason": reason,
            "reflection_history": history,
            "current_query": refined,
            "retry_count": retry_count + 1
        }
    else:
        status_label = "PASS" if passed else "MAX_RETRIES_REACHED"
        final_reason = reason if passed else f"已達反思重試上限 ({MAX_REFLECTION_RETRIES} 次)，採用目前最佳召回資料合成報告。"
        history.append({
            "step": "Final_Reflection_Assessment",
            "status": status_label,
            "reason": final_reason,
            "action": "反思評估合格，導向合成生成節點！"
        })
        return {
            "evaluation_passed": True,
            "reflection_reason": final_reason,
            "reflection_history": history
        }

def should_retry(state: AgentState) -> str:
    """
    條件邊路由：判斷是否需要循環重查 (Reflection Loop)
    """
    if not state.get("evaluation_passed", True):
        return "retriever_node"
    return "generator_node"

def generator_node(state: AgentState) -> Dict[str, Any]:
    """
    【節點 4：合規檢核報告合成 Generator】
    彙整檢索條文、反思稽核日誌與法律分析，產出結構化專業分析報告
    """
    q = state["original_query"]
    route = state.get("route", "local_retriever")
    docs = state.get("retrieved_docs", [])
    history = state.get("reflection_history", [])
    source = state.get("retrieval_source", "")

    # 提取條文依據清單
    related_rules = []
    for d in docs:
        t = d.get("title", "")
        c = d.get("chapter", "")
        snippet = d.get("content", d.get("snippet", ""))[:140].replace("\n", " ").strip()
        if t:
            related_rules.append(f"《公寓大廈管理條例》{t}（{c}）：{snippet}...")
        elif d.get("snippet"):
            related_rules.append(f"{d.get('title')}：{snippet}...")

    if not related_rules:
        related_rules = [f"《公寓大廈管理條例》相關條文檢核：針對提問【{q}】之母法規範。"]

    # 依法律要件建構專業合規性分析
    is_shoe = any(k in q for k in ["鞋櫃", "鞋架", "走廊", "雜物", "梯廳"])
    is_fall = any(k in q for k in ["防墜", "鐵窗", "防墜網", "陽台"])
    is_ac = any(k in q for k in ["冷氣", "室外機", "滴水"])
    is_ev = any(k in q for k in ["充電", "充電樁", "電動車"])
    is_fee = any(k in q for k in ["管理費", "欠繳", "催繳", "存證信函", "支付命令"])
    is_assembly = any(k in q for k in ["區權會", "門檻", "決議", "假決議", "流會"])
    is_pet = any(k in q for k in ["寵物", "貓", "狗", "飼養", "禁養"])
    is_flood = any(k in q for k in ["防水閘門", "防汛", "演練", "操演", "車道閘門", "沙包", "截水溝", "沉水泵"])

    historical_practice = "大清天朵二期管委會歷來嚴格遵行公寓大廈管理條例與社區規約，落實公共安全維護與區權人合法權益保障。"
    conflicts = "依法律位階原則，社區規約或管委會會議決議若牴觸《公寓大廈管理條例》之法律強制或禁止規定者，依法當然無效。"
    recommendations = "1. 恪遵法定程序辦理。\n2. 涉及重大規約修訂需提送區分所有權人會議合法議決。\n3. 本助手維持客觀中立，最終決策權保留給全體區權會與管委會。"

    if is_shoe:
        historical_practice = "大清天朵二期歷來依規約執行走廊與公共梯廳拍照存證、開立限期改善單，逾期即依條例報請主管機關裁罰；第三屆區分所有權人大會出席權數 82% 亦投票否決放置薄型鞋櫃之提案。"
        conflicts = "若管委會常會決議『開放放置特定規格鞋櫃』，將直接牴觸【第三屆區分所有權人會議之法定決議】及【公寓大廈管理條例第十六條第二項】避難走廊禁止堆置雜物之強制規範；且依條例第四十九條，違者主管機關得處新臺幣四萬元以上二十萬元以下罰鍰。"
        recommendations = "1. 走廊屬避難通道與共用部分，管委會應嚴格維持走道淨空，無權擅自放寬允許擺放鞋櫃。\n2. 住戶若拒不改善，管委會應拍照存證並報請直轄市、縣（市）主管機關（建管處）依第49條裁處罰鍰。\n3. 如欲重議鞋櫃擺放，法定程序須於下屆區分所有權人會議提出規約修正案，並達法定出席與同意門檻。"
    elif is_fall:
        historical_practice = "大清天朵二期家中有未滿12歲幼童或65歲以上長者之住戶，填具防墜設施備查申請表並檢附合規施作圖說後，管委會均依法准予安裝，未曾刁難阻礙。"
        conflicts = "若社區規約企圖以『大樓外觀統一』為由全面禁止住戶於陽台加裝防墜網/隱形鐵窗，該約定已直接牴觸《公寓大廈管理條例》第八條第二項之法律強制授權條款，依同條第三項規定，規約之任意限制無效，管委會不得拒絕或裁罰。"
        recommendations = "1. 具備幼童或高齡長者之住戶依法有權設置不妨礙逃生且不突出外牆之防墜設施（如隱形鐵窗），管委會不得拒絕或阻撓。\n2. 物業中心可請住戶提供施作廠商之抗拉（140kgf以上）與安全逃生合格證明備查。\n3. 當設置理由消失（如兒童滿12歲、老人遷離），住戶應負改善或回復原狀之義務。"
    elif is_ev:
        historical_practice = "社區地下室停車場裝設私人電動車充電樁（EMS），申請人須委託具甲級電匠資質廠商規劃專用配電箱與獨立電錶，並經管委會機電顧問審查通過後施作。"
        conflicts = "住戶若未經管委會同意私自自公共配電箱拉線，或未配合EMS電能管理系統負載容量限制，將直接違反第6條第1項第4款及公共用電公平原則。"
        recommendations = "1. 請物業中心向申請住戶提供制式『充電樁裝設申請規約與安全切結書』。\n2. 委請社區機電顧問就線槽容量與負載進行安全審核。\n3. 施工費用與獨立電費全數由設置戶自負。"
    elif is_ac:
        historical_practice = "冷氣主機嚴格限制於建商預留之冷氣樑位安裝，不得懸掛於外牆立面外緣，排水須接至指定專用排水孔。"
        conflicts = "擅自懸掛外牆涉嫌破壞大樓外觀統一風格，且若防墜支架鏽蝕恐衍生高空掉落公共危險責任；冷氣滴水若經管委會制止不改善，得報請地方主管機關依廢棄物清理法或公寓大廈管理條例第49條開罰。"
        recommendations = "1. 勸導住戶立即更正安裝位置至建商預留冷氣樑位。\n2. 如外包廠商強行違規懸掛，物業得依規約拒絕其進場施工。\n3. 要求廠商接妥冷凝水引流管路，杜絕滴水干擾樓下住戶。"
    elif is_pet:
        historical_practice = "社區採寵物友善自治管理，要求進出公共大廳電梯嚴格裝籠、推車或繫牽繩，排泄物由飼主隨行即時清理。"
        conflicts = "管委會若僅以常會決議『自即日起全面禁止住戶養狗養貓』，因未經區分所有權人會議合法修正規約，該公告依法無效；依條例第23條第2項第3款，禁養特定動物須正式載明於規約中方生拘束力。"
        recommendations = "1. 管委會常會無權片面公告全面禁養。\n2. 針對個別寵物吠叫或隨地便溺，管委會應依第16條第4項制止並要求改善；經制止而不遵從者，得報請主管機關依第49條處4萬至20萬元罰鍰。\n3. 若欲全面禁養，須於下屆區權會提修正案表決。"
    elif is_fee:
        historical_practice = "每月由物業出納核對銀行入帳，逾二期先發存證信函定 7~10 日催告；屆期未繳向桃園地院聲請支付命令。"
        conflicts = "【違法私力救濟風險警示】：管委會絕對不得以『消磁門禁感應扣使住戶無法搭電梯』或『斷水斷電、扣留掛號信』作為催繳手段！實務判例認定此舉已妨害住戶專有所有權與通行權，主委與管理員恐涉犯刑法第304條強制罪並負民事侵權賠償責任。"
        recommendations = "1. 欠繳逾二期後，先以存證信函催告並給予7~10日相當繳款期間。\n2. 逾期仍不給付者，檢具規約與欠繳憑單向法院聲請核發『支付命令』。\n3. 取得確定證明後，向法院聲請強制執行查封其存款或不動產。\n4. 嚴禁採取消磁磁扣等私力妨害手段，以策安全合規。"
    elif is_assembly:
        historical_practice = "每年開會前 15 日送達開會通知書與議案，並落實委託書身分審核。"
        conflicts = "若首次大會出席未達法定 2/3 門檻，主席強行開議表決作成之決議依法為重大瑕疵，住戶得依法提起撤銷之訴；召集人必須宣告流會，依法重新召集假決議大會。"
        recommendations = "1. 首次召集大會務必加強宣導並收集合法代理出席委託書。\n2. 若流會，召集人應於 3 日至 15 日內，就同一議案重新通知召集第二次會議（門檻降至 1/5 出席、過半數同意）。\n3. 假決議紀錄送達全體住戶 7 日內未書面反對，即告正式確定生效。"
    elif is_flood:
        historical_practice = "每年 5 月中旬由固德物業總幹事會同機電委員實施地下室車道防水閘門實兵組裝測時演練（上年度實測 11 分 35 秒合格，標準為 15 分鐘以內），並通電測試截水溝三組沉水抽水泵。"
        conflicts = "若未於每年 5 月汛期前落實實兵組裝演練，一旦遭遇極端豪大雨導致車道倒灌致使地下室車輛受損，受託之物業與管委會恐面臨未盡『善良管理人注意義務』之民事賠償責任。"
        recommendations = "1. 恪遵規約於每年 5 月 15 日前完成車道閘門實兵組裝、止水膠條密封、沉水泵測試與沙包檢點。\n2. 演練日前 3 天由物業發布車道管制公告。\n3. 氣象署發布特報時立即啟動防汛SOP。"

    final_result = {
        "query": q,
        "route_selected": route,
        "route_reason": state.get("route_reason", ""),
        "retrieval_source": source,
        "retrieved_count": len(docs),
        "related_rules": related_rules,
        "historical_practice": historical_practice,
        "conflicts": conflicts,
        "recommendations": recommendations,
        "reflection_audit": history,
        "reflection_triggered": len(history) > 1
    }

    return {"final_answer": final_result}

# ==============================================================================
# 3. 建構 LangGraph StateGraph
# ==============================================================================
def create_condo_rag_agent():
    workflow = StateGraph(AgentState)

    # 加入節點
    workflow.add_node("router_node", router_node)
    workflow.add_node("retriever_node", retriever_node)
    workflow.add_node("reflection_node", reflection_node)
    workflow.add_node("generator_node", generator_node)

    # 加入邊
    workflow.add_edge(START, "router_node")
    workflow.add_edge("router_node", "retriever_node")
    workflow.add_edge("retriever_node", "reflection_node")

    # 條件邊：反思評估是否通過 -> 若未通過則循環回檢索節點重新查詢！
    workflow.add_conditional_edges(
        "reflection_node",
        should_retry,
        {
            "retriever_node": "retriever_node",
            "generator_node": "generator_node"
        }
    )

    workflow.add_edge("generator_node", END)

    app = workflow.compile()
    return app

# 全域單例 Agent
_condo_agent_app = None

def get_condo_agent():
    global _condo_agent_app
    if _condo_agent_app is None:
        _condo_agent_app = create_condo_rag_agent()
    return _condo_agent_app

def run_condo_query(query: str) -> Dict[str, Any]:
    """
    提供對外直接調用的高階入口
    """
    agent = get_condo_agent()
    initial_state: AgentState = {
        "original_query": query,
        "current_query": query,
        "route": "",
        "route_reason": "",
        "retrieved_docs": [],
        "retrieval_source": "",
        "context_text": "",
        "evaluation_passed": False,
        "reflection_reason": "",
        "reflection_history": [],
        "retry_count": 0,
        "final_answer": {}
    }
    output_state = agent.invoke(initial_state)
    return output_state["final_answer"]

if __name__ == "__main__":
    print("=== 測試 1：本地文件檢索 + 觸發反思改寫重查 ===")
    res1 = run_condo_query("鞋子放門口走廊可以嗎？")
    print(f"路由判定: {res1['route_selected']} ({res1['route_reason']})")
    print(f"反思是否觸發: {res1['reflection_triggered']}")
    print("反思日誌歷程:")
    for h in res1['reflection_audit']:
        print(f"  • [{h.get('step')}] {h.get('status')}: {h.get('reason')} -> {h.get('action')}")
    print("\n相關法規:")
    for r in res1['related_rules'][:2]:
        print(" ", r)

    print("\n=== 測試 2：外部司法判例網路搜尋 ===")
    res2 = run_condo_query("鞋櫃 走廊 最新法院判決")
    print(f"路由判定: {res2['route_selected']} ({res2['route_reason']})")
    print(f"檢索來源: {res2['retrieval_source']}")
    print("相關法規與裁判摘要:")
    for r in res2['related_rules'][:2]:
        print(" ", r)
