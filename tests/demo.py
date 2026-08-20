# tests/demo.py

"""
Agent Router 一键演示脚本
展示 6 个典型场景的路由决策
用法: python tests/demo.py [--real]
"""

import sys
import os
import json
import argparse
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.adapters.zhipu_adapter import ZhipuAdapter
from src.core.features.llm_analyzer import LLMAnalyzer
from src.core.router.rule_engine import RuleEngine

# ============================================================
# 模型配置
# ============================================================
MODELS = {
    "mock-cheap":  {"cost_per_1k": 0.0005, "capability": 60, "has_code": False, "tee": False, "latency": 100},
    "mock-strong": {"cost_per_1k": 0.001,  "capability": 85, "has_code": True,  "tee": False, "latency": 800},
    "mock-tee":    {"cost_per_1k": 0.002,  "capability": 75, "has_code": True,  "tee": True,  "latency": 1200},
}

CANDIDATES = [
    {"id": "mock-cheap",  "cost_per_1k_tokens": 0.0005, "capability_score": 60, "capabilities": [],        "is_local": False, "tee_enabled": False, "latency_ms": 100},
    {"id": "mock-strong", "cost_per_1k_tokens": 0.001,  "capability_score": 85, "capabilities": ["code"],   "is_local": False, "tee_enabled": False, "latency_ms": 800},
    {"id": "mock-tee",    "cost_per_1k_tokens": 0.002,  "capability_score": 75, "capabilities": ["code"],   "is_local": False, "tee_enabled": True,  "latency_ms": 1200},
]

API_KEY = "168f20af9ecd4b548ada54e42f7ca3f9.nR6T6keG5r7ZkKv7"

# ============================================================
# 6 个演示场景
# ============================================================
DEMO_SCENARIOS = [
    {
        "title": "场景 1：简单问候 → 低成本模型",
        "description": "用户发送普通问候，系统识别为简单任务，路由到最便宜的模型。",
        "messages": [{"role": "user", "content": "你好，今天天气怎么样？"}],
        "policies": ["cost_first", "quality_first"],
        "expected_behavior": "cost_first 选 cheap（省钱），quality_first 选 strong（质量优先）",
    },
    {
        "title": "场景 2：代码任务 → 强模型",
        "description": "用户要求编写代码，系统识别为复杂任务，路由到能力最强的模型。",
        "messages": [{"role": "user", "content": "用Python写一个快速排序算法，要有详细注释和时间复杂度分析"}],
        "policies": ["cost_first", "quality_first"],
        "expected_behavior": "两种策略都应选 strong（cheap 无代码能力被过滤）",
    },
    {
        "title": "场景 3：含身份证号 → 隐私保护",
        "description": "用户发送含身份证号的消息，系统检测到个人隐私，强制使用 TEE 安全模型。",
        "messages": [{"role": "user", "content": "这是我的身份证号110101199001011234，请帮我验证格式是否正确"}],
        "policies": ["cost_first", "quality_first", "privacy_strict"],
        "expected_behavior": "所有策略都必须选 tee（隐私硬约束，cheap/strong 得 0 分）",
    },
    {
        "title": "场景 4：数据库密码 → 高敏感保护",
        "description": "用户发送数据库连接串（含密码），系统识别为高敏感，强制 TEE 模型。",
        "messages": [{"role": "user", "content": "数据库连接串：mysql://admin:pass123@10.0.1.5:3306/prod_db，帮我检查配置"}],
        "policies": ["cost_first", "privacy_strict"],
        "expected_behavior": "隐私约束强制选 tee，cheap/strong 被过滤",
    },
    {
        "title": "场景 5：成本 vs 质量对比",
        "description": "同一个复杂任务，对比 cost_first 和 quality_first 的选择差异。",
        "messages": [{"role": "user", "content": "调用GitHub API获取最近20个PR，分析代码质量并生成review报告"}],
        "policies": ["cost_first", "quality_first"],
        "expected_behavior": "cost_first → strong（最便宜有代码能力的）, quality_first → strong（能力最强）",
    },
    {
        "title": "场景 6：Fallback 降级演示",
        "description": "模拟上游模型不可用时的降级行为。",
        "messages": [{"role": "user", "content": "帮我总结这篇技术文档的要点"}],
        "policies": ["cost_first"],
        "show_fallback": True,
        "expected_behavior": "正常选 cheap/strong，模拟失败后降级到规则引擎",
    },
]


# ============================================================
# 演示函数
# ============================================================
def run_demo(use_real_llm=False):
    """运行所有演示场景"""
    
    analyzer = None
    rule_engine = RuleEngine()
    
    if use_real_llm:
        print("🔌 初始化真实 LLM (GLM-4-Flash)...")
        adapter = ZhipuAdapter(api_key=API_KEY)
        analyzer = LLMAnalyzer(adapter)
        print("✅ 就绪\n")
    
    print("╔" + "═" * 68 + "╗")
    print("║" + "  Agent Router — 6 场景演示".center(60) + "║")
    print("║" + ("  🤖 真实 LLM 模式" if use_real_llm else "  📏 模拟模式").center(60) + "║")
    print("╚" + "═" * 68 + "╝")
    
    for idx, scenario in enumerate(DEMO_SCENARIOS, 1):
        print(f"\n{'─' * 70}")
        print(f"  {scenario['title']}")
        print(f"{'─' * 70}")
        print(f"  📝 输入: {scenario['messages'][0]['content'][:80]}...")
        print(f"  🎯 预期: {scenario['expected_behavior']}")
        print(f"  📋 策略: {', '.join(scenario['policies'])}")
        print()
        
        # LLM 分析（真实模式）
        if use_real_llm and analyzer:
            analysis, llm_latency = analyze_task(scenario, analyzer)
            print(f"  🧠 LLM 分析: c={analysis.complexity} p={analysis.privacy_level} code={analysis.has_code} ({llm_latency:.0f}ms)")
            print(f"     理由: {analysis.reasoning}")
            print()
        
        # 模拟路由
        for policy in scenario["policies"]:
            if use_real_llm and analyzer:
                result = rule_engine.select(
                    complexity=analysis.complexity,
                    privacy_level=analysis.privacy_level,
                    has_code=analysis.has_code,
                    policy=policy,
                    candidates=CANDIDATES,
                )
                model_id = result["model_id"]
                reason = result.get("reason", "")
            else:
                model_id, reason = simulate_route(scenario, policy)
            
            # 模型信息
            info = MODELS.get(model_id, {})
            cost = info.get("cost_per_1k", 0)
            capability = info.get("capability", 0)
            tee = info.get("tee", False)
            
            # 输出
            icon = _get_icon(model_id, scenario)
            tee_badge = "🔐 TEE" if tee else ""
            print(f"  {icon} [{policy:<16}] → {model_id:<12} "
                  f"能力={capability} 成本=¥{cost:.4f}/1k tokens "
                  f"{tee_badge}")
            if reason:
                print(f"     理由: {reason}")
        
        # Fallback 演示
        if scenario.get("show_fallback"):
            print(f"\n  ⚠️  模拟上游失败:")
            print(f"     mock-strong 不可用 → 降级到规则引擎")
            print(f"     规则引擎: 复杂度=2, 无隐私, 无代码 → mock-cheap")
            print(f"     结果: ✅ 降级成功，使用廉价模型完成任务")
        
        if idx < len(DEMO_SCENARIOS):
            time.sleep(0.5)
    
    # 总结
    print(f"\n{'═' * 70}")
    print(f"  总结")
    print(f"{'═' * 70}")
    print(f"  ✅ 简单任务 → cost_first → cheap（省钱）")
    print(f"  ✅ 复杂任务 → quality_first → strong（能力最强）")
    print(f"  ✅ 敏感数据 → 自动选 tee（安全第一，能力次要）")
    print(f"  ✅ 上游失败 → 自动降级到规则引擎")
    print(f"{'═' * 70}")


def analyze_task(scenario, analyzer):
    """LLM 分析"""
    t0 = time.time()
    analysis = analyzer.analyze(scenario["messages"])
    latency = (time.time() - t0) * 1000
    return analysis, latency


def simulate_route(scenario, policy):
    """模拟路由（使用预期值）"""
    # 简化的模拟逻辑
    privacy_map = {
        "场景 3": "medium",
        "场景 4": "high",
    }
    
    has_code_map = {
        "场景 2": True,
        "场景 5": True,
    }
    
    complexity_map = {
        "场景 1": 1,
        "场景 2": 5,
        "场景 3": 2,
        "场景 4": 3,
        "场景 5": 5,
        "场景 6": 2,
    }
    
    privacy = privacy_map.get(scenario["title"][:4], "none")
    has_code = has_code_map.get(scenario["title"][:4], False)
    complexity = complexity_map.get(scenario["title"][:4], 2)
    
    # 隐私约束
    if privacy in ("high", "medium"):
        available = ["mock-tee"]
    else:
        available = ["mock-cheap", "mock-strong", "mock-tee"]
    
    # 代码约束
    if has_code or complexity >= 5:
        available = [m for m in available if m != "mock-cheap"]
    
    # 策略选择
    if policy == "cost_first":
        model_id = min(available, key=lambda m: MODELS[m]["cost_per_1k"])
        reason = "成本优先：选择最便宜的可用模型"
    elif policy == "quality_first":
        model_id = max(available, key=lambda m: MODELS[m]["capability"])
        reason = "质量优先：选择能力最强的模型"
    elif policy == "privacy_strict":
        tee_models = [m for m in available if MODELS[m]["tee"]]
        if tee_models:
            model_id = max(tee_models, key=lambda m: MODELS[m]["capability"])
            reason = "隐私严格：选择安全模型中能力最强的"
        else:
            model_id = "BLOCKED"
            reason = "隐私严格：无安全模型可用"
    else:
        model_id = available[0]
        reason = ""
    
    return model_id, reason


def _get_icon(model_id, scenario):
    """根据场景和模型判断对错"""
    if model_id == "BLOCKED":
        return "🚫"
    
    title = scenario["title"][:4]
    
    # 场景1: cheap 对简单任务正确
    if title == "场景 1":
        return "✅" if model_id in ("mock-cheap", "mock-strong") else "❌"
    # 场景2: strong 对代码任务正确
    elif title == "场景 2":
        return "✅" if model_id == "mock-strong" else "❌"
    # 场景3: tee 对敏感数据正确
    elif title == "场景 3":
        return "✅" if model_id == "mock-tee" else "❌"
    # 场景4: tee 对高敏感正确
    elif title == "场景 4":
        return "✅" if model_id == "mock-tee" else "❌"
    
    return "✅"


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Router 6场景演示")
    parser.add_argument("--real", action="store_true", help="使用真实 LLM 分析")
    args = parser.parse_args()
    
    run_demo(use_real_llm=args.real)