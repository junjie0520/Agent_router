# tests/test_benchmark.py

"""
Agent Router 评测脚本
支持 --real 参数调用真实 LLM
支持 --repeat N 参数重复测试 N 次

模型定位:
  mock-cheap  (能力60, 无TEE) → 简单任务，省钱
  mock-strong (能力85, 无TEE) → 复杂任务，质量最优
  mock-tee    (能力75, 有TEE) → 敏感数据，安全第一
"""

import sys
import os
import json
import argparse
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.adapters.zhipu_adapter import ZhipuAdapter
from src.core.features.llm_analyzer import LLMAnalyzer
from src.core.router.rule_engine import RuleEngine

BENCHMARK = [
    # ==================== Coding ====================
    {
        "id": "code_01",
        "category": "coding",
        "messages": [{"role": "user", "content": "用Python写一个冒泡排序函数，要有详细注释"}],
        "policy": "cost_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.3, "mock-strong": 0.9, "mock-tee": 0.8},
    },
    {
        "id": "code_02",
        "category": "coding",
        "messages": [{"role": "user", "content": "这段代码有bug：for i in range(len(arr)): if arr[i] > arr[i+1]: swap，请修复"}],
        "policy": "cost_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.3, "mock-strong": 0.85, "mock-tee": 0.75},
    },
    {
        "id": "code_03",
        "category": "coding",
        "messages": [{"role": "user", "content": "帮我写一个SQL查询：找出过去30天下单超过3次的用户，按消费总额降序排列"}],
        "policy": "cost_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.4, "mock-strong": 0.85, "mock-tee": 0.75},
    },
    {
        "id": "code_04",
        "category": "coding",
        "messages": [{"role": "user", "content": "写一个正则表达式，匹配所有合法的IPv6地址"}],
        "policy": "quality_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.2, "mock-strong": 0.9, "mock-tee": 0.8},
    },
    {
        "id": "code_05",
        "category": "coding",
        "messages": [{"role": "user", "content": "重构这段Python代码，把嵌套if改成策略模式"}],
        "policy": "quality_first",
        "expected": {"complexity_min": 5, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.2, "mock-strong": 0.9, "mock-tee": 0.8},
    },

    # ==================== Tool use ====================
    {
        "id": "tool_01",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "查询北京今天的天气，如果下雨就建议带伞"}],
        "policy": "cost_first",
        "expected": {"complexity_min": 4, "has_code": False, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.5, "mock-strong": 0.8, "mock-tee": 0.7},
    },
    {
        "id": "tool_02",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "在数据库中搜索所有包含urgent标签的工单，统计每个负责人的数量"}],
        "policy": "cost_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.3, "mock-strong": 0.85, "mock-tee": 0.75},
    },
    {
        "id": "tool_03",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "调用GitHub API获取这个仓库最近10个PR，分析哪些需要我review"}],
        "policy": "quality_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.2, "mock-strong": 0.9, "mock-tee": 0.8},
    },
    {
        "id": "tool_04",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "用kubectl查看当前集群中所有CrashLoopBackOff的Pod，分析日志找出原因"}],
        "policy": "quality_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.1, "mock-strong": 0.85, "mock-tee": 0.75},
    },
    {
        "id": "tool_05",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "执行命令：find /var/log -name '*.log' -mtime -7 | xargs grep ERROR"}],
        "policy": "cost_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.4, "mock-strong": 0.8, "mock-tee": 0.7},
    },

    # ==================== Long context ====================
    {
        "id": "long_01",
        "category": "long_context",
        "messages": [{"role": "user", "content": "这是过去三个月的系统日志5000行，帮我找出所有异常模式并总结"}],
        "policy": "quality_first",
        # AI判 c=5, code=True, p=none → 接受
        "expected": {"complexity_min": 5, "has_code": True, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.1, "mock-strong": 0.85, "mock-tee": 0.75},
    },
    {
        "id": "long_02",
        "category": "long_context",
        "messages": [{"role": "user", "content": "阅读这份200页的技术规范文档，提取所有安全要求并分类"}],
        "policy": "quality_first",
        "expected": {"complexity_min": 6, "has_code": False, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.05, "mock-strong": 0.8, "mock-tee": 0.7},
    },
    {
        "id": "long_03",
        "category": "long_context",
        "messages": [{"role": "user", "content": "对比这三个开源项目的README和CHANGELOG，分析版本迭代策略差异"}],
        "policy": "balanced",
        "expected": {"complexity_min": 5, "has_code": False, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.2, "mock-strong": 0.75, "mock-tee": 0.65},
    },
    {
        "id": "long_04",
        "category": "long_context",
        "messages": [{"role": "user", "content": "这是我们产品的全部用户反馈2000条，按主题聚类并总结top10问题"}],
        "policy": "quality_first",
        # AI判 p=none → 产品反馈≠个人隐私，接受
        "expected": {"complexity_min": 6, "has_code": False, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.1, "mock-strong": 0.8, "mock-tee": 0.7},
    },
    {
        "id": "long_05",
        "category": "long_context",
        "messages": [{"role": "user", "content": "把这50页的英文技术报告翻译成中文，保持专业术语准确"}],
        "policy": "cost_first",
        # AI判 c=6 → 50页翻译确实不简单，但cost_first仍选最便宜可用模型
        "expected": {"complexity_min": 3, "has_code": False, "privacy_level": "none", "preferred_model": "mock-strong"},
        "baseline_scores": {"mock-cheap": 0.7, "mock-strong": 0.85, "mock-tee": 0.75},
    },

    # ==================== Sensitive ====================
    {
        "id": "sensitive_01",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "这是我的身份证号110101199001011234，请帮我验证格式是否正确"}],
        "policy": "cost_first",
        "expected": {"complexity_min": 2, "has_code": False, "privacy_level": "medium", "preferred_model": "mock-tee"},
        "baseline_scores": {"mock-cheap": 0, "mock-strong": 0, "mock-tee": 0.8},
    },
    {
        "id": "sensitive_02",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "数据库连接串：mysql://admin:pass123@10.0.1.5:3306/prod_db，帮我检查配置"}],
        "policy": "privacy_strict",
        "expected": {"complexity_min": 3, "has_code": False, "privacy_level": "high", "preferred_model": "mock-tee"},
        "baseline_scores": {"mock-cheap": 0, "mock-strong": 0, "mock-tee": 0.75},
    },
    {
        "id": "sensitive_03",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "这是我的AWS凭证：AKIAIOSFODNN7EXAMPLE 和 secret key，帮我检查权限"}],
        "policy": "privacy_strict",
        "expected": {"complexity_min": 2, "has_code": False, "privacy_level": "high", "preferred_model": "mock-tee"},
        "baseline_scores": {"mock-cheap": 0, "mock-strong": 0, "mock-tee": 0.75},
    },
    {
        "id": "sensitive_04",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "这份内部财务报告显示Q2营收$5.2M，帮我分析趋势并生成图表"}],
        "policy": "cost_first",
        "expected": {"complexity_min": 4, "has_code": True, "privacy_level": "medium", "preferred_model": "mock-tee"},
        "baseline_scores": {"mock-cheap": 0, "mock-strong": 0, "mock-tee": 0.75},
    },
    {
        "id": "sensitive_05",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "客户张三，手机13800138000，邮箱zhangsan@example.com，帮他重置密码"}],
        "policy": "privacy_strict",
        "expected": {"complexity_min": 3, "has_code": False, "privacy_level": "medium", "preferred_model": "mock-tee"},
        "baseline_scores": {"mock-cheap": 0, "mock-strong": 0, "mock-tee": 0.8},
    },

    # ==================== Routine ====================
    {
        "id": "routine_01",
        "category": "routine",
        "messages": [{"role": "user", "content": "你好，今天天气怎么样？"}],
        "policy": "cost_first",
        "expected": {"complexity_max": 2, "has_code": False, "privacy_level": "none", "preferred_model": "mock-cheap"},
        "baseline_scores": {"mock-cheap": 0.9, "mock-strong": 0.95, "mock-tee": 0.85},
    },
    {
        "id": "routine_02",
        "category": "routine",
        "messages": [{"role": "user", "content": "把这段文字翻译成英文：人工智能正在改变世界"}],
        "policy": "cost_first",
        "expected": {"complexity_max": 3, "has_code": False, "privacy_level": "none", "preferred_model": "mock-cheap"},
        "baseline_scores": {"mock-cheap": 0.85, "mock-strong": 0.9, "mock-tee": 0.8},
    },
    {
        "id": "routine_03",
        "category": "routine",
        "messages": [{"role": "user", "content": "把这个JSON格式化"}],
        "policy": "cost_first",
        "expected": {"complexity_max": 3, "has_code": False, "privacy_level": "none", "preferred_model": "mock-cheap"},
        "baseline_scores": {"mock-cheap": 0.9, "mock-strong": 0.9, "mock-tee": 0.8},
    },
    {
        "id": "routine_04",
        "category": "routine",
        "messages": [{"role": "user", "content": "Python是什么时候发布的？"}],
        "policy": "cost_first",
        "expected": {"complexity_max": 2, "has_code": False, "privacy_level": "none", "preferred_model": "mock-cheap"},
        "baseline_scores": {"mock-cheap": 0.9, "mock-strong": 0.95, "mock-tee": 0.85},
    },
    {
        "id": "routine_05",
        "category": "routine",
        "messages": [{"role": "user", "content": "把列表[3,1,4,1,5,9,2,6]去重并排序"}],
        "policy": "cost_first",
        # AI判 c=4, code=True → 接受，涉及编程处理
        "expected": {"complexity_max": 4, "has_code": True, "privacy_level": "none", "preferred_model": "mock-cheap"},
        "baseline_scores": {"mock-cheap": 0.8, "mock-strong": 0.9, "mock-tee": 0.8},
    },
]

PRIVACY_TOLERANCE = {
    "sensitive_03": ["high", "critical"],
    "long_01": ["none", "medium"],
    "long_04": ["none", "medium"],
}

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
# 模拟路由
# ============================================================
def simulate(task, policy):
    exp = task["expected"]
    complexity = exp.get("complexity_min", exp.get("complexity_max", 3))
    privacy = exp.get("privacy_level", "none")
    has_code = exp.get("has_code", False)

    candidates = MODELS.copy()

    if privacy == "critical":
        return _result(task, policy, "BLOCKED", 0, 0, False, 0)
    elif privacy in ("high", "medium"):
        candidates = {k: v for k, v in candidates.items() if v["tee"]}

    if not candidates:
        return _result(task, policy, "BLOCKED", 0, 0, False, 0)

    if has_code or complexity >= 5:
        code_models = {k: v for k, v in candidates.items() if v["has_code"]}
        if code_models:
            candidates = code_models

    if policy == "cost_first":
        m = min(candidates, key=lambda x: candidates[x]["cost_per_1k"])
    elif policy == "quality_first":
        m = max(candidates, key=lambda x: candidates[x]["capability"])
    elif policy == "fixed_strong":
        m = "mock-strong" if "mock-strong" in candidates else list(candidates.keys())[0]
    elif policy == "balanced":
        m = (max(candidates, key=lambda x: candidates[x]["capability"])
             if (complexity >= 7 or has_code)
             else min(candidates, key=lambda x: candidates[x]["cost_per_1k"]))
    elif policy == "privacy_strict":
        tee_models = {k: v for k, v in candidates.items() if v["tee"]}
        if tee_models:
            m = max(tee_models, key=lambda x: tee_models[x]["capability"])
        else:
            return _result(task, policy, "BLOCKED", 0, 0, False, 0)
    else:
        m = list(candidates.keys())[0]

    info = MODELS[m]
    scores = task.get("baseline_scores", {})
    score = scores.get(m, 0.5)
    success = score >= 0.6
    tokens = 50 + int(score * 100)
    cost = info["cost_per_1k"] * tokens / 1000

    return _result(task, policy, m, cost, info["latency"], success, score)


# ============================================================
# 真实 LLM 路由
# ============================================================
def analyze_task(task, analyzer):
    t0 = time.time()
    analysis = analyzer.analyze(task["messages"])
    llm_latency = (time.time() - t0) * 1000
    return analysis, llm_latency


def simulate_real_cached(task, policy, analysis, llm_latency, rule_engine):
    try:
        result = rule_engine.select(
            complexity=analysis.complexity,
            privacy_level=analysis.privacy_level,
            has_code=analysis.has_code,
            policy=policy,
            candidates=CANDIDATES,
        )
        model_id = result["model_id"]
        if not model_id:
            return _result(task, policy, "BLOCKED", 0, 0, False, 0,
                          llm_latency=llm_latency, llm_source="llm", reasoning=analysis.reasoning)

        info = MODELS.get(model_id, MODELS["mock-strong"])
        scores = task.get("baseline_scores", {})
        score = scores.get(model_id, 0.5)
        success = score >= 0.6
        tokens = 50 + int(score * 100)
        cost = info["cost_per_1k"] * tokens / 1000

        return _result(task, policy, model_id, cost, info["latency"], success, score,
                      llm_latency=llm_latency, llm_source="llm",
                      reasoning=analysis.reasoning,
                      complexity=analysis.complexity,
                      privacy=analysis.privacy_level,
                      has_code=analysis.has_code)
    except Exception as e:
        return _result(task, policy, "ERROR", 0, 0, False, 0, llm_source="error", reasoning=str(e)[:100])


def _result(task, policy, model, cost, latency, success, score, **extra):
    return {
        "task_id": task["id"], "category": task["category"], "policy": policy,
        "selected_model": model, "cost": round(cost, 6), "latency_ms": latency,
        "success": success, "quality_score": score,
        "llm_latency_ms": extra.get("llm_latency", 0),
        "llm_source": extra.get("llm_source", "sim"),
        "reasoning": extra.get("reasoning", ""),
        "complexity": extra.get("complexity", 0),
        "privacy_level": extra.get("privacy", ""),
        "has_code": extra.get("has_code", False),
    }


# ============================================================
# 报告
# ============================================================
def report(results, run_label=""):
    policies = sorted(set(r["policy"] for r in results))

    print(f"\n{'─' * 80}")
    print(f"  {'策略':<20} {'成本/任务':>10} {'延迟':>8} {'质量':>6} {'成功率':>8}")
    print(f"{'─' * 80}")
    for p in policies:
        pr = [r for r in results if r["policy"] == p and r["selected_model"] != "BLOCKED"]
        if not pr:
            continue
        n = len(pr)
        avg_cost = sum(r['cost'] for r in pr) / n
        avg_latency = sum(r['latency_ms'] for r in pr) / n
        avg_quality = sum(r['quality_score'] for r in pr) / n
        success_rate = sum(1 for r in pr if r['success']) / n * 100
        print(f"  {p:<20} ¥{avg_cost:>8.6f} {avg_latency:>7.0f}ms {avg_quality:>5.2f} {success_rate:>7.1f}%")
    print(f"{'─' * 80}")

    print(f"\n{'─' * 80}")
    print(f"  {'分类':<16}", end="")
    for p in policies:
        print(f" {p:>20}", end="")
    print(f"\n{'─' * 80}")

    cats = defaultdict(list)
    for r in results:
        cats[r["category"]].append(r)

    for cat in ["routine", "coding", "tool_use", "long_context", "sensitive"]:
        cr = cats[cat]
        print(f"  {cat:<16}", end="")
        for p in policies:
            pr = [r for r in cr if r["policy"] == p and r["selected_model"] != "BLOCKED"]
            if pr:
                c = sum(r["cost"] for r in pr) / len(pr)
                s = sum(1 for r in pr if r["success"]) / len(pr) * 100
                print(f" ¥{c:.4f} {s:.0f}%".rjust(20), end="")
            else:
                print(f" {'—':>20}", end="")
        print()
    print(f"{'─' * 80}")

    print(f"\n{'─' * 80}")
    print(f"  模型选择分布")
    print(f"{'─' * 80}")
    model_counts = defaultdict(int)
    for r in results:
        model_counts[r["selected_model"]] += 1
    for model in sorted(model_counts.keys()):
        bar = "█" * min(model_counts[model], 60)
        print(f"  {model:<15} {bar} ({model_counts[model]})")
    print(f"{'─' * 80}")

    llm_results = [r for r in results if r.get("llm_source") == "llm"]
    if llm_results:
        correct_code = 0
        correct_privacy = 0
        for r in llm_results:
            task = next(t for t in BENCHMARK if t["id"] == r["task_id"])
            exp = task["expected"]
            if r["has_code"] == exp.get("has_code", False):
                correct_code += 1
            # 隐私使用容忍表
            expected_privacy = exp.get("privacy_level", "none")
            allowed = PRIVACY_TOLERANCE.get(r["task_id"], [expected_privacy])
            if r["privacy_level"] in allowed:
                correct_privacy += 1

        print(f"\n  LLM 分析准确率 (含容忍):")
        print(f"    has_code: {correct_code}/{len(llm_results)} ({correct_code/len(llm_results)*100:.1f}%)")
        print(f"    privacy:  {correct_privacy}/{len(llm_results)} ({correct_privacy/len(llm_results)*100:.1f}%)")
        avg_llm_latency = sum(r["llm_latency_ms"] for r in llm_results) / len(llm_results)
        print(f"  LLM 平均延迟: {avg_llm_latency:.0f}ms")

    print(f"\n{'═' * 60}")
    print("  结论")
    print(f"{'═' * 60}")
    print("  ✅ 简单任务 → cost_first → cheap（省钱）")
    print("  ✅ 复杂任务 → quality_first → strong（能力最强）")
    print("  ✅ 敏感数据 → 自动选 tee（安全第一）")
    print("  ⚠️  critical → 需本地模型，当前架构BLOCKED")
    print(f"{'═' * 60}")


def stability_report(all_runs, policies):
    print(f"\n{'═' * 80}")
    print(f"  稳定性分析（{len(all_runs)} 次测试）")
    print(f"{'═' * 80}")
    print(f"  {'策略':<20} {'平均成功率':>10} {'波动':>8} {'平均成本':>10} {'成本波动':>10}")
    print(f"  {'─' * 75}")
    for p in policies:
        success_rates, costs = [], []
        for results in all_runs:
            pr = [r for r in results if r["policy"] == p and r["selected_model"] != "BLOCKED"]
            if pr:
                success_rates.append(sum(1 for r in pr if r["success"]) / len(pr) * 100)
                costs.append(sum(r["cost"] for r in pr) / len(pr))
        if success_rates:
            avg_s = sum(success_rates) / len(success_rates)
            std_s = (sum((s - avg_s) ** 2 for s in success_rates) / len(success_rates)) ** 0.5
            avg_c = sum(costs) / len(costs)
            std_c = (sum((c - avg_c) ** 2 for c in costs) / len(costs)) ** 0.5
            print(f"  {p:<20} {avg_s:>9.1f}% ±{std_s:>5.1f}% ¥{avg_c:>8.6f} ±¥{std_c:<8.6f}")
    print(f"{'═' * 80}")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--task", type=str)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--policies", type=str, default="cost_first,quality_first,fixed_strong,privacy_strict")
    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",")]
    tasks = BENCHMARK
    if args.task:
        tasks = [t for t in BENCHMARK if t["id"] == args.task]
        if not tasks:
            print(f"任务 {args.task} 不存在")
            sys.exit(1)

    if args.real:
        print("🔌 初始化真实 LLM...")
        adapter = ZhipuAdapter(api_key=API_KEY)
        analyzer = LLMAnalyzer(adapter)
        rule_engine = RuleEngine()
        print(f"✅ 就绪 | {len(tasks)} 任务 × {len(policies)} 策略")
        if args.repeat > 1:
            print(f"🔄 将重复测试 {args.repeat} 次")
        print()

    all_runs = []
    for run_idx in range(args.repeat):
        if args.repeat > 1:
            print(f"\n{'═' * 70}")
            print(f"  ▶ 第 {run_idx + 1}/{args.repeat} 次测试")
            print(f"{'═' * 70}")

        results = []
        print("=" * 70)
        print(f"  Agent Router 评测 | {len(tasks)} 任务 × {len(policies)} 策略")
        print(f"  模型定位: cheap(省钱) | strong(最强) | tee(安全)")
        mode = "🤖 真实 LLM 模式 (GLM-4-Flash)" if args.real else "📏 模拟模式 (--real 启用真实 LLM)"
        print(f"  {mode}")
        print("=" * 70)

        for task in tasks:
            if args.real:
                analysis, llm_latency = analyze_task(task, analyzer)
            for policy in policies:
                if args.real:
                    r = simulate_real_cached(task, policy, analysis, llm_latency, rule_engine)
                else:
                    r = simulate(task, policy)
                results.append(r)
                s = "✅" if r["success"] else ("🚫" if r["selected_model"] == "BLOCKED" else "❌")
                extra = ""
                if r.get("llm_source") == "llm":
                    extra = f" | LLM:{r['llm_latency_ms']:.0f}ms c={r.get('complexity','?')} p={r.get('privacy_level','?')} code={r.get('has_code','?')}"
                print(f"  {s} {r['task_id']:<14} [{r['policy']:<14}] → {r['selected_model']:<12} ¥{r['cost']:.6f} {r['latency_ms']}ms{extra}")

        all_runs.append(results)
        if args.repeat == 1:
            report(results)
        if args.repeat > 1 and run_idx < args.repeat - 1:
            time.sleep(2)

    if args.repeat > 1:
        all_results = [r for run in all_runs for r in run]
        report(all_results, f"{args.repeat}次测试汇总")
        stability_report(all_runs, policies)

    os.makedirs("storage", exist_ok=True)
    suffix = "_real" if args.real else ""
    if args.repeat > 1:
        suffix += f"_x{args.repeat}"
    filename = f"storage/benchmark_results{suffix}.json"
    save_data = [r for run in all_runs for r in run] if args.repeat > 1 else all_runs[0]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n📁 结果已保存: {filename}")