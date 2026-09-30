import sys
from condo_rag_agent.agent_workflow import run_condo_query

def print_banner():
    print("=" * 68)
    print("  🏛️  《公寓大廈管理條例》Agentic RAG 智能法規檢核系統")
    print("  技術框架: LangGraph StateGraph + ChromaDB 向量庫 + DuckDuckGo Web")
    print("  核心能力: 智慧路由 (Router) + 自我反思改寫重查 (Reflection)")
    print("=" * 68)

def format_terminal_output(res: dict):
    print("\n" + "─" * 68)
    print(f"🎯【使用者提問】：{res.get('query')}")
    print(f"🔀【路由決策 Router】：{res.get('route_selected')} ➔ {res.get('route_reason')}")
    print(f"📡【檢索來源 Source】：{res.get('retrieval_source')} (召回 {res.get('retrieved_count')} 筆依據)")
    
    print("\n🔄【反思機制稽核 Reflection Audit】：")
    if res.get('reflection_triggered'):
        print("  ⚠️ 初次檢索資料不夠充分，已自動觸發反思機制進行關鍵字重寫！")
    else:
        print("  ✅ 檢索內容一次通過法學要件檢視！")

    for step in res.get('reflection_audit', []):
        st = step.get('status')
        tag = "🔴 [需反思改寫]" if "FAIL" in st else "🟢 [反思通過]"
        print(f"  • {tag} {step.get('step')}: {step.get('reason')}")
        if step.get('new_query'):
            print(f"    ↪ 自動改寫關鍵字：『{step.get('new_query')}』")

    print("\n📜【適用法令條文依據】：")
    for r in res.get('related_rules', []):
        print(f"  • {r}")

    print("\n🏛️【社區歷史慣例與權限邊界】：")
    print(f"  {res.get('historical_practice')}")

    print("\n⚠️【法律位階與衝突風險分析】：")
    print(f"  {res.get('conflicts')}")

    print("\n💡【合規處理處置建議】：")
    for line in res.get('recommendations', '').split('\n'):
        if line.strip():
            print(f"  {line}")
    print("─" * 68 + "\n")

def run_interactive():
    print_banner()
    print("請輸入您想檢核的規約或法律問題（輸入 q 或 exit 離開）：\n")
    demo_cases = [
        "走廊能放鞋櫃嗎？",
        "陽台能裝防墜網嗎？",
        "社區可以全面禁養寵物嗎？",
        "管委會可以因為欠繳管理費消磁住戶電梯卡嗎？",
        "走廊放鞋架 2026 最新法院判決"
    ]
    print("常見提問範例：")
    for i, c in enumerate(demo_cases, 1):
        print(f"  {i}. {c}")
    print()

    while True:
        try:
            user_in = input("👉 請輸入問題或按 Enter 選擇預設範例 [1]: ").strip()
            if user_in.lower() in ['q', 'exit', 'quit']:
                print("👋 感謝使用《公寓大廈管理條例》AI 助手！")
                break
            if not user_in:
                user_in = demo_cases[0]
            elif user_in.isdigit() and 1 <= int(user_in) <= len(demo_cases):
                user_in = demo_cases[int(user_in) - 1]

            print(f"\n[*] 正在由 Agent 分析問題並啟動 RAG 檢索...")
            res = run_condo_query(user_in)
            format_terminal_output(res)
        except (KeyboardInterrupt, EOFError):
            print("\n👋 離開系統。")
            break

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="《公寓大廈管理條例》Agentic RAG 智能法規檢核系統")
    parser.add_argument("--query", "-q", type=str, help="直接指定提問內容進行法規分析")
    args = parser.parse_args()

    if args.query:
        print_banner()
        print(f"[*] 接收到命令列提問：『{args.query}』，正在啟動 RAG 檢索...")
        res = run_condo_query(args.query)
        format_terminal_output(res)
    else:
        run_interactive()
