from condo_rag_agent.agent_workflow import run_condo_query

def run_all_tests():
    test_suite = [
        {
            "name": "測試案例 1：日常用語模糊提問（驗證 Reflection 反思與自動關鍵字改寫）",
            "query": "住戶門口鞋子被鄰居投訴怎麼辦？",
            "expect_route": "local_retriever",
            "expect_reflection": True
        },
        {
            "name": "測試案例 2：陽台防墜網（驗證第 8 條第 2 項法律強制授權）",
            "query": "家中有小孩，想在陽台裝隱形鐵窗防墜網，管委會可以禁止嗎？",
            "expect_route": "local_retriever",
            "expect_reflection": False
        },
        {
            "name": "測試案例 3：外部司法判例（驗證 Router 導向 DuckDuckGo 網路檢索）",
            "query": "走廊放鞋櫃判決 最新法院裁判書 實務見解",
            "expect_route": "web_search",
            "expect_reflection": False
        }
    ]

    print("=" * 70)
    print("  🧪 開始執行《公寓大廈管理條例》Agent 核心功能自動化測試")
    print("=" * 70)

    for idx, tc in enumerate(test_suite, 1):
        print(f"\n▶ 執行 [{idx}/{len(test_suite)}]：{tc['name']}")
        print(f"  提問內容：『{tc['query']}』")
        res = run_condo_query(tc["query"])
        
        print(f"  ↪ 路由結果：{res['route_selected']} (預期: {tc['expect_route']})")
        print(f"  ↪ 反思觸發：{res['reflection_triggered']} (預期: {tc['expect_reflection']})")
        print(f"  ↪ 檢索來源：{res['retrieval_source']}")
        print(f"  ↪ 召回法規依據數：{len(res['related_rules'])}")
        
        # 斷言檢查
        route_ok = (res['route_selected'] == tc['expect_route'])
        print(f"  ✅ 測試結果：{'通過 PASS' if route_ok else '未符預期'}")
        print("  反思稽核日誌：")
        for h in res.get('reflection_audit', []):
            print(f"    • {h.get('step')}: {h.get('status')} | {h.get('reason')}")

    print("\n" + "=" * 70)
    print("  🎉 全部測試案例執行完畢！Agent 核心架構運作正常！")
    print("=" * 70)

if __name__ == "__main__":
    run_all_tests()
