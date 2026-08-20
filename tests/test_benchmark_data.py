# tests/test_data.py

"""
Agent Router 评测集
覆盖 5 类任务：Coding / Tool use / Long context / Sensitive / Routine
每类 5 条，共 25 条

模型定位:
  mock-cheap  (能力60, 无TEE, ¥0.0005) → 简单任务，省钱
  mock-strong (能力85, 无TEE, ¥0.001)  → 复杂任务，质量最优
  mock-tee    (能力75, 有TEE, ¥0.002)  → 敏感数据，安全第一

"""

BENCHMARK = [
    # ============================================================
    # 1. Coding（代码类）
    # ============================================================
    {
        "id": "code_01",
        "category": "coding",
        "messages": [{"role": "user", "content": "用Python写一个冒泡排序函数，要有详细注释"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 4,
            "has_code": True,
            "privacy_level": "none",
            "preferred_model": "mock-strong",  # cost_first + 代码任务 → 有代码能力的最便宜模型
        },
        "baseline_scores": {
            "mock-cheap": 0.3,    # 无代码能力，可能失败
            "mock-strong": 0.9,   # 最强AI能力
            "mock-tee": 0.8,      # 有代码能力但稍弱
        },
    },
    {
        "id": "code_02",
        "category": "coding",
        "messages": [{"role": "user", "content": "这段代码有bug：for i in range(len(arr)): if arr[i] > arr[i+1]: swap，请修复"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 4,
            "has_code": True,
            "privacy_level": "none",
            "preferred_model": "mock-strong",
        },
        "baseline_scores": {
            "mock-cheap": 0.3,
            "mock-strong": 0.85,
            "mock-tee": 0.75,
        },
    },
    {
        "id": "code_03",
        "category": "coding",
        "messages": [{"role": "user", "content": "帮我写一个SQL查询：找出过去30天下单超过3次的用户，按消费总额降序排列"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 4,
            "has_code": True,
            "privacy_level": "none",
            "preferred_model": "mock-strong",
        },
        "baseline_scores": {
            "mock-cheap": 0.4,
            "mock-strong": 0.85,
            "mock-tee": 0.75,
        },
    },
    {
        "id": "code_04",
        "category": "coding",
        "messages": [{"role": "user", "content": "写一个正则表达式，匹配所有合法的IPv6地址"}],
        "policy": "quality_first",
        "expected": {
            "complexity_min": 4,                
            "has_code": True,
            "privacy_level": "none",
            "preferred_model": "mock-strong",  # quality_first + 无隐私 → 选能力最强的strong
        },
        "baseline_scores": {
            "mock-cheap": 0.2,
            "mock-strong": 0.9,   # 最强
            "mock-tee": 0.8,      # 稍弱
        },
    },
    {
        "id": "code_05",
        "category": "coding",
        "messages": [{"role": "user", "content": "重构这段Python代码，把嵌套if改成策略模式，代码：def process(type, data): if type=='A': return data*2 elif type=='B': return data+1 else: return data"}],
        "policy": "quality_first",
        "expected": {
            "complexity_min": 5,
            "has_code": True,
            "privacy_level": "none",
            "preferred_model": "mock-strong",  # quality_first → 选最强
        },
        "baseline_scores": {
            "mock-cheap": 0.2,
            "mock-strong": 0.9,
            "mock-tee": 0.8,
        },
    },

    # ============================================================
    # 2. Tool use（工具调用类）
    # ============================================================
    {
        "id": "tool_01",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "查询北京今天的天气，如果下雨就建议带伞"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 4,
            "has_code": False,      # 工具调用但非代码编写
            "privacy_level": "none",
            "preferred_model": "mock-strong",  # 需要推理能力，cost_first选最便宜有能力的
        },
        "baseline_scores": {
            "mock-cheap": 0.5,      # 能做但质量一般
            "mock-strong": 0.8,
            "mock-tee": 0.7,
        },
    },
    {
        "id": "tool_02",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "在数据库中搜索所有包含'urgent'标签的工单，统计每个负责人的数量，生成表格"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 4,              
            "has_code": True,       # 数据库操作 = has_code（AI判True）
            "privacy_level": "none",
            "preferred_model": "mock-strong",
        },
        "baseline_scores": {
            "mock-cheap": 0.3,
            "mock-strong": 0.85,
            "mock-tee": 0.75,
        },
    },
    {
        "id": "tool_03",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "调用GitHub API获取这个仓库最近10个PR，分析哪些需要我review"}],
        "policy": "quality_first",
        "expected": {
            "complexity_min": 4,               
            "has_code": True,       # API调用 = has_code
            "privacy_level": "none",
            "preferred_model": "mock-strong",  # quality_first → 最强
        },
        "baseline_scores": {
            "mock-cheap": 0.2,
            "mock-strong": 0.9,
            "mock-tee": 0.8,
        },
    },
    {
        "id": "tool_04",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "用kubectl查看当前集群中所有CrashLoopBackOff的Pod，分析日志找出原因"}],
        "policy": "quality_first",
        "expected": {
            "complexity_min": 4,               
            "has_code": True,       # kubectl命令 = has_code
            "privacy_level": "none",
            "preferred_model": "mock-strong",  # quality_first → 最强
        },
        "baseline_scores": {
            "mock-cheap": 0.1,
            "mock-strong": 0.85,
            "mock-tee": 0.75,
        },
    },
    {
        "id": "tool_05",
        "category": "tool_use",
        "messages": [{"role": "user", "content": "执行这个命令：find /var/log -name '*.log' -mtime -7 | xargs grep 'ERROR' | sort | uniq -c | sort -rn | head -20"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 4,
            "has_code": True,       # Shell命令 = has_code
            "privacy_level": "none",
            "preferred_model": "mock-strong",
        },
        "baseline_scores": {
            "mock-cheap": 0.4,
            "mock-strong": 0.8,
            "mock-tee": 0.7,
        },
    },

    # ============================================================
    # 3. Long context（长上下文类）
    # ============================================================
    {
        "id": "long_01",
        "category": "long_context",
        "messages": [{"role": "user", "content": "这是过去三个月的系统日志(共5000行)，帮我找出所有异常模式并总结"}],
        "policy": "quality_first",
        "expected": {
            "complexity_min": 5,                # 接受（日志分析）
            "has_code": True,                   #（日志分析涉及脚本），接受
            "privacy_level": "none",            # 系统日志无个人隐私
            "preferred_model": "mock-strong",   # quality_first → 最强（无隐私需求）
        },
        "baseline_scores": {
            "mock-cheap": 0.1,      # 长上下文处理能力弱
            "mock-strong": 0.85,
            "mock-tee": 0.75,
        },
    },
    {
        "id": "long_02",
        "category": "long_context",
        "messages": [{"role": "user", "content": "阅读这份200页的技术规范文档，提取所有安全要求并分类"}],
        "policy": "quality_first",
        "expected": {
            "complexity_min": 6,
            "has_code": False,
            "privacy_level": "none",
            "preferred_model": "mock-strong",  # quality_first → 最强
        },
        "baseline_scores": {
            "mock-cheap": 0.05,
            "mock-strong": 0.8,
            "mock-tee": 0.7,
        },
    },
    {
        "id": "long_03",
        "category": "long_context",
        "messages": [{"role": "user", "content": "对比这三个开源项目的README和CHANGELOG，分析它们的版本迭代策略差异"}],
        "policy": "balanced",
        "expected": {
            "complexity_min": 5,
            "has_code": False,
            "privacy_level": "none",
            "preferred_model": "mock-strong",  # balanced + 中等复杂度 → strong
        },
        "baseline_scores": {
            "mock-cheap": 0.2,
            "mock-strong": 0.75,
            "mock-tee": 0.65,
        },
    },
    {
        "id": "long_04",
        "category": "long_context",
        "messages": [{"role": "user", "content": "这是我们产品的全部用户反馈(2000条)，按主题聚类并用中文总结top10问题"}],
        "policy": "quality_first",
        "expected": {
            "complexity_min": 6,
            "has_code": False,
            "privacy_level": "none",            # 产品反馈≠个人隐私，接受
            "preferred_model": "mock-strong",   # 无隐私 → quality_first选最强
        },
        "baseline_scores": {
            "mock-cheap": 0.1,                  # 长文本能力弱
            "mock-strong": 0.8,                 # 可用
            "mock-tee": 0.7,                    # 能力稍弱
        },
    },
    {
        "id": "long_05",
        "category": "long_context",
        "messages": [{"role": "user", "content": "把这50页的英文技术报告翻译成中文，保持专业术语准确"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 3,                # 翻译复杂度
            "has_code": False,
            "privacy_level": "none",
            "preferred_model": "mock-strong",   # 50页专业翻译需强模型，cost_first选最便宜有能力的
        },
        "baseline_scores": {
            "mock-cheap": 0.7,                  # 能做但质量一般
            "mock-strong": 0.85,                # 更好
            "mock-tee": 0.75,
        },
    },

    # ============================================================
    # 4. Sensitive context（敏感信息类）
    # ============================================================
    {
        "id": "sensitive_01",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "这是我的身份证号110101199001011234，请帮我验证格式是否正确"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 2,
            "has_code": False,
            "privacy_level": "medium",           # 身份证 = 个人隐私
            "preferred_model": "mock-tee",       # 隐私 → 必须TEE
        },
        "baseline_scores": {
            "mock-cheap": 0,      # 不安全
            "mock-strong": 0,     # 不安全
            "mock-tee": 0.8,      # 安全
        },
    },
    {
        "id": "sensitive_02",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "数据库连接串：mysql://admin:pass123@10.0.1.5:3306/prod_db，帮我检查这个配置是否安全"}],
        "policy": "privacy_strict",
        "expected": {
            "complexity_min": 3,
            "has_code": False,
            "privacy_level": "high",             # 数据库密码 = 高敏感
            "preferred_model": "mock-tee",       # 必须TEE
        },
        "baseline_scores": {
            "mock-cheap": 0,
            "mock-strong": 0,
            "mock-tee": 0.75,
        },
    },
    {
        "id": "sensitive_03",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "这是我的AWS凭证：AKIAIOSFODNN7EXAMPLE 和 secret key，帮我检查权限配置"}],
        "policy": "privacy_strict",
        "expected": {
            "complexity_min": 2,                 
            "has_code": False,
            "privacy_level": "high",             # 仅凭证无支付上下文，合理
            "preferred_model": "mock-tee",       # high → tee处理即可
        },
        "baseline_scores": {
            "mock-cheap": 0,      # 不安全
            "mock-strong": 0,     # 不安全
            "mock-tee": 0.75,     # tee可处理high级别
        },
    },
    {
        "id": "sensitive_04",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "这份内部财务报告显示Q2营收$5.2M，帮我分析趋势并生成图表"}],
        "policy": "cost_first",
        "expected": {
            "complexity_min": 4,
            "has_code": True,                    # 生成图表 = has_code
            "privacy_level": "medium",           # 内部财务 = 敏感
            "preferred_model": "mock-tee",       # 隐私优先
        },
        "baseline_scores": {
            "mock-cheap": 0,
            "mock-strong": 0,
            "mock-tee": 0.75,
        },
    },
    {
        "id": "sensitive_05",
        "category": "sensitive",
        "messages": [{"role": "user", "content": "客户张三，手机13800138000，邮箱zhangsan@example.com，帮他重置密码并发送通知"}],
        "policy": "privacy_strict",
        "expected": {
            "complexity_min": 3,
            "has_code": False,
            "privacy_level": "medium",           # 姓名+手机+邮箱 = 个人隐私
            "preferred_model": "mock-tee",       # 必须TEE
        },
        "baseline_scores": {
            "mock-cheap": 0,
            "mock-strong": 0,
            "mock-tee": 0.8,
        },
    },

    # ============================================================
    # 5. Routine（简单常规任务）
    # ============================================================
    {
        "id": "routine_01",
        "category": "routine",
        "messages": [{"role": "user", "content": "你好，今天天气怎么样？"}],
        "policy": "cost_first",
        "expected": {
            "complexity_max": 2,
            "has_code": False,
            "privacy_level": "none",
            "preferred_model": "mock-cheap",     # 最简单任务 → 最便宜
        },
        "baseline_scores": {
            "mock-cheap": 0.9,    # 简单任务，cheap完全够用
            "mock-strong": 0.95,
            "mock-tee": 0.85,     # tee在此无优势
        },
    },
    {
        "id": "routine_02",
        "category": "routine",
        "messages": [{"role": "user", "content": "把这段文字翻译成英文：人工智能正在改变世界"}],
        "policy": "cost_first",
        "expected": {
            "complexity_max": 3,
            "has_code": False,
            "privacy_level": "none",
            "preferred_model": "mock-cheap",
        },
        "baseline_scores": {
            "mock-cheap": 0.85,
            "mock-strong": 0.9,
            "mock-tee": 0.8,
        },
    },
    {
        "id": "routine_03",
        "category": "routine",
        "messages": [{"role": "user", "content": "把这个JSON格式化：{\"name\":\"test\",\"value\":123,\"enabled\":true}"}],
        "policy": "cost_first",
        "expected": {
            "complexity_max": 3,                 #接受
            "has_code": False,
            "privacy_level": "none",
            "preferred_model": "mock-cheap",
        },
        "baseline_scores": {
            "mock-cheap": 0.9,
            "mock-strong": 0.9,
            "mock-tee": 0.8,
        },
    },
    {
        "id": "routine_04",
        "category": "routine",
        "messages": [{"role": "user", "content": "Python是什么时候发布的？"}],
        "policy": "cost_first",
        "expected": {
            "complexity_max": 2,
            "has_code": False,
            "privacy_level": "none",
            "preferred_model": "mock-cheap",
        },
        "baseline_scores": {
            "mock-cheap": 0.9,
            "mock-strong": 0.95,
            "mock-tee": 0.85,
        },
    },
    {
        "id": "routine_05",
        "category": "routine",
        "messages": [{"role": "user", "content": "把列表[3,1,4,1,5,9,2,6]去重并排序"}],
        "policy": "cost_first",
        "expected": {
            "complexity_max": 4,                 # 接受
            "has_code": True,                    # 涉及代码但很简单
            "privacy_level": "none",
            "preferred_model": "mock-cheap",     # cheap能处理简单代码
        },
        "baseline_scores": {
            "mock-cheap": 0.8,    # 能处理简单的代码任务
            "mock-strong": 0.9,
            "mock-tee": 0.8,
        },
    },
]


# ============================================================
# 隐私级别容忍表：AI判定为这些值也算正确
# ============================================================
PRIVACY_TOLERANCE = {
    # sensitive_03: （仅凭证无支付上下文）
    "sensitive_03": ["high", "critical"],
    # long_01: 系统日志可能判none或medium
    "long_01": ["none", "medium"],
    # long_04: 产品反馈可能判none或medium
    "long_04": ["none", "medium"],
    # sensitive_01: 身份证可能判medium或high
    "sensitive_01": ["medium", "high"],
    # sensitive_05: PII数据可能判medium或high
    "sensitive_05": ["medium", "high"],
}


# ============================================================
# 模型配置（供外部引用）
# ============================================================
MODELS = {
    "mock-cheap": {
        "cost_per_1k": 0.0005,
        "capability": 60,
        "has_code": False,
        "tee": False,
        "latency": 100,
        "description": "低成本模型，适合简单对话"
    },
    "mock-strong": {
        "cost_per_1k": 0.001,
        "capability": 85,       # 🔥 最强AI能力
        "has_code": True,
        "tee": False,
        "latency": 800,
        "description": "高性能模型，适合复杂任务（无隐私保护）"
    },
    "mock-tee": {
        "cost_per_1k": 0.002,
        "capability": 75,       # ⚠️ 低于strong（安全开销）
        "has_code": True,
        "tee": True,            # 🔐 安全隔离
        "latency": 1200,
        "description": "安全模型，适合敏感数据处理"
    },
}

CANDIDATES = [
    {
        "id": "mock-cheap",
        "cost_per_1k_tokens": 0.0005,
        "capability_score": 60,
        "capabilities": [],
        "is_local": False,
        "tee_enabled": False,
        "latency_ms": 100,
    },
    {
        "id": "mock-strong",
        "cost_per_1k_tokens": 0.001,
        "capability_score": 85,     # 🔥 最高
        "capabilities": ["code"],
        "is_local": False,
        "tee_enabled": False,
        "latency_ms": 800,
    },
    {
        "id": "mock-tee",
        "cost_per_1k_tokens": 0.002,
        "capability_score": 75,     # ⚠️ 低于strong
        "capabilities": ["code"],
        "is_local": False,
        "tee_enabled": True,        # 🔐 TEE标志
        "latency_ms": 1200,
    },
]


# ============================================================
# 统计
# ============================================================
def print_summary():
    """打印评测集概览"""
    categories = {}
    for item in BENCHMARK:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item["id"])

    print("=" * 55)
    print("  Agent Router 评测集概览")
    print("=" * 55)
    for cat, ids in categories.items():
        print(f"  {cat:<15}: {len(ids)} 条")
    print(f"  {'─' * 50}")
    print(f"  总计          : {len(BENCHMARK)} 条")
    print("=" * 55)
    print()
    print("  模型定位:")
    print(f"    mock-cheap  (能力60) → 简单任务，省钱")
    print(f"    mock-strong (能力85) → 复杂任务，质量最优")
    print(f"    mock-tee    (能力75) → 敏感数据，安全第一")
    print("=" * 55)
    print()
    print("  容忍规则: sensitive_03判high也算正确(仅凭证无支付上下文)")
    print("           long_01判medium也算正确(系统日志)")
    print("           long_04判medium也算正确(用户反馈)")


def print_model_matrix():
    """打印模型-任务适配矩阵"""
    print(f"\n{'─' * 80}")
    print(f"  模型选择逻辑")
    print(f"{'─' * 80}")
    print(f"  无隐私 + 简单    → cost_first  → cheap")
    print(f"  无隐私 + 复杂    → quality_first → strong (能力最强)")
    print(f"  有隐私(medium+)  → 隐私约束     → tee (唯一安全选择)")
    print(f"  有隐私(critical) → 需要本地     → BLOCKED")
    print(f"{'─' * 80}")


if __name__ == "__main__":
    print_summary()
    print_model_matrix()