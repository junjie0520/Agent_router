# Agent Router — 面向 Agent 场景的智能模型路由系统

> **一句话描述**：根据任务复杂度、隐私等级和成本策略，自动为 Agent 任务选择最优模型。

---

## 📋 目录

- [项目背景](#项目背景)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [路由策略](#路由策略)
- [评测体系](#评测体系)
- [API 文档](#api-文档)
- [项目结构](#项目结构)
- [设计文档](#设计文档)
- [局限性](#局限性)
- [后续方向](#后续方向)

---

## 项目背景

Agent 任务和普通聊天不同。一个 Agent 可能会读代码、改文件、调用工具、跑测试、总结长文档、分析日志、处理表格或执行多步工作流。不同任务对模型的要求差异很大：

| 任务类型 | 特点 | 模型需求 |
|---------|------|---------|
| 简单问答 | 低成本即可 | 便宜模型 |
| 代码修改 | 需要代码能力 | 强模型 |
| 敏感数据 | 隐私优先 | TEE/本地模型 |
| 长上下文 | 需要大窗口 | 强模型 |
| 工具调用 | 可能不稳定 | 中等+ |

**核心问题**：如果所有任务固定使用同一个模型，要么成本过高，要么复杂任务效果不足。

**解决方案**：Agent Router 在隐私和可信约束下，根据任务特征、成本、延迟和风险，自动选择合适模型。

---

## 系统架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Agent Router                               │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │   用户请求    │───▶│  FeatureExtractor │───▶│   LLMAnalyzer    │  │
│  │  (messages)  │    │  (关键词/正则)    │    │  (GLM-4-Flash)   │  │
│  └──────────────┘    └──────────────────┘    └────────┬─────────┘  │
│                                                       │             │
│                                          complexity, privacy,      │
│                                          has_code, reasoning       │
│                                                       │             │
│                                                       ▼             │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │ RouteReceipt │◀───│    RuleEngine    │◀───│   隐私 + 能力     │  │
│  │  (审计证据)  │    │   (规则查表)     │    │     过滤          │  │
│  └──────────────┘    └──────────────────┘    └──────────────────┘  │
│         │                                                          │
│         │  selected_model, reason, cost, signature                 │
│         ▼                                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    候选模型池                                 │  │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐               │  │
│  │  │  cheap   │    │  strong  │    │   tee    │               │  │
│  │  │ 能力:60  │    │ 能力:85  │    │ 能力:75  │               │  │
│  │  │ ¥0.0005  │    │ ¥0.001   │    │ ¥0.002   │               │  │
│  │  │ 无TEE ❌ │    │ 无TEE ❌ │    │ TEE ✅   │               │  │
│  │  └──────────┘    └──────────┘    └──────────┘               │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 决策流程

```
用户请求
  │
  ├─ LLM 分析 → complexity, privacy_level, has_code
  │
  ├─ privacy = critical? ──是──▶ BLOCKED
  │
  ├─ privacy = medium/high? ──是──▶ 过滤非TEE模型
  │
  ├─ has_code 或 complexity≥5? ──是──▶ 过滤无代码能力模型
  │
  └─ 策略路由
       ├─ cost_first → 最便宜
       ├─ quality_first → 能力最强
       ├─ fixed_strong → 固定strong
       └─ privacy_strict → 安全+最强
            │
            └─ RouteReceipt（完整决策证据）
```

### 核心组件

| 组件 | 职责 | 技术 |
|------|------|------|
| **FeatureExtractor** | 提取文本特征 | 关键词匹配 + 正则 |
| **LLMAnalyzer** | 分析复杂度/隐私/代码 | GLM-4-Flash |
| **RuleEngine** | 策略路由决策 | 规则查表（0ms） |
| **RouteReceipt** | 可审计证据 | JSON + 签名 |

### 候选模型

| 模型 | 能力 | 成本 | TEE | 定位 |
|------|------|------|-----|------|
| **mock-cheap** | 60 | ¥0.0005/1k | ❌ | 简单任务，省钱 |
| **mock-strong** | 85 | ¥0.001/1k | ❌ | 复杂任务，质量最优 |
| **mock-tee** | 75 | ¥0.002/1k | ✅ | 敏感数据，安全第一 |

### Demo 演示

```bash
# 一键运行 6 个典型场景
python tests/demo.py --real
```

场景覆盖：简单问候 → cheap | 代码任务 → strong | 身份证 → tee | 数据库密码 → tee | 成本vs质量对比 | fallback 降级

---

## 快速开始

### 环境要求

- Python 3.10+
- GLM-4-Flash API Key（[智谱AI开放平台](https://open.bigmodel.cn/)）

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd agent-router

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

### 配置

```bash
# 设置 API Key（Windows PowerShell）
$env:GLM_API_KEY="your-api-key-here"

# Linux/Mac
export GLM_API_KEY="your-api-key-here"
```

### 启动服务

```bash
uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```

访问 Swagger 文档：http://localhost:8000/docs

### 运行评测

```bash
# 模拟模式（快速验证路由逻辑）
python tests/test_benchmark.py

# 真实 LLM 模式
python tests/test_benchmark.py --real

# 重复测试（稳定性评估）
python tests/test_benchmark.py --real --repeat 3

# 单个任务测试
python tests/test_benchmark.py --real --task sensitive_03
```

---

## 路由策略

### 4 种策略

| 策略 | 逻辑 | 适用场景 |
|------|------|---------|
| **cost_first** | 选最便宜的可行模型 | 简单任务、成本敏感 |
| **quality_first** | 选能力最强的模型 | 复杂任务、质量要求高 |
| **fixed_strong** | 固定选 mock-strong | 基准对比 |
| **privacy_strict** | 必须 TEE 模型 | 敏感数据处理 |

### 隐私硬约束

```
privacy = none    → 所有模型可用
privacy = medium  → 仅 tee 模型
privacy = high    → 仅 tee 模型
privacy = critical → 需要本地模型（当前架构 BLOCKED）
```

---

## 评测体系

### 评测集

25 条任务，覆盖 5 类 Agent 场景：

| 分类 | 数量 | 示例 |
|------|------|------|
| **Coding** | 5 | 冒泡排序、bug修复、SQL、IPv6正则、策略模式重构 |
| **Tool use** | 5 | 天气查询、数据库搜索、GitHub API、kubectl、shell管道 |
| **Long context** | 5 | 日志分析、文档提取、版本对比、用户反馈聚类、翻译 |
| **Sensitive** | 5 | 身份证、数据库密码、AWS凭证、财务报告、客户PII |
| **Routine** | 5 | 问候、翻译、JSON格式化、知识问答、列表处理 |

### 评测结果

| 策略 | 成本/任务 | 成功率 | 质量 |
|------|-----------|--------|------|
| cost_first | ¥0.000154 | 96.0% | 0.82 |
| fixed_strong | ¥0.000154 | 96.0% | 0.82 |
| privacy_strict | ¥0.000253 | **100.0%** | 0.76 |
| quality_first | ¥0.000169 | **100.0%** | **0.84** |

### LLM 分析准确率

| 指标 | 准确率 |
|------|--------|
| has_code 检测 | **96.0%** |
| privacy_level 检测 | **100.0%** |

### 核心结论

- ✅ **简单任务** → cost_first → cheap（省钱，质量不降）
- ✅ **复杂任务** → quality_first → strong（AI能力最强）
- ✅ **敏感数据** → 自动选 tee（安全第一）
- ⚠️ **critical数据** → 需要本地模型，当前架构会 BLOCKED

---

## API 文档

### POST /route

路由单个请求

```json
// 请求
{
  "messages": [
    {"role": "user", "content": "用Python写一个冒泡排序函数"}
  ],
  "policy": "quality_first"
}

// 响应
{
  "selected_model": "mock-strong",
  "decision_reason": "质量优先：选择能力最强",
  "candidate_models": ["mock-cheap", "mock-strong", "mock-tee"],
  "complexity_score": 4,
  "privacy_level": "none",
  "has_code": true,
  "pii_detected": false,
  "estimated_cost": 0.00014,
  "llm_analysis": {
    "complexity": 4,
    "privacy_level": "none",
    "has_code": true,
    "reasoning": "编写函数涉及代码生成..."
  },
  "signature": "..."
}
```

### POST /route/batch

批量路由

```json
{
  "requests": [...],
  "policy": "cost_first"
}
```

### GET /health

健康检查

---

## 项目结构

```
agent-router/
├── src/
│   ├── api/
│   │   ├── server.py              # FastAPI 服务入口
│   │   └── routes.py              # API 端点
│   ├── core/
│   │   ├── router/
│   │   │   ├── engine.py          # 顶层调度
│   │   │   ├── decision_maker.py  # 决策中枢
│   │   │   ├── rule_engine.py     # 规则查表（0ms）
│   │   │   └── feature_extractor.py
│   │   ├── features/
│   │   │   └── llm_analyzer.py    # LLM 分析器
│   │   ├── adapters/
│   │   │   ├── llm_adapter.py     # 适配器基类
│   │   │   └── zhipu_adapter.py   # 智谱适配器
│   │   ├── audit/                 # 审计日志
│   │   └── schemas/               # 数据模型
│   └── config/
├── docs/
│   └── design.md                  # 详细设计文档
├── tests/
│   ├── demo.py                    # 6场景演示脚本
│   ├── test_benchmark.py          # 评测主脚本
│   ├── test_data.py               # 25条评测数据集
│   ├── test_e2e_full.py           # 端到端测试
│   └── test_zhipu_connection.py
├── storage/
│   └── benchmark_results_real.json
├── README.md
└── requirements.txt
```

---

## 设计文档

完整设计文档见 [`docs/design.md`](docs/design.md)，包含：

| 章节 | 内容 |
|------|------|
| 项目背景与用户场景 | 3 个典型场景分析 |
| 系统架构 | 架构图 + 决策流程图 |
| 系统边界 | 做什么 / 不做什么 |
| 关键接口 | API 端点 + RouteReceipt Schema |
| 安全/隐私/信任模型 | 隐私等级 + 信任假设 + 威胁模型 |
| 失败模式 | 5 种失败场景及处理策略 |
| 局限性 | 6 项已知局限 |
| 后续方向 | 7 个扩展方向（按优先级排列） |

### 核心设计原则

| 原则 | 实现 |
|------|------|
| **隐私硬约束** | RuleEngine 强制执行，LLM 误判不影响安全 |
| **可解释决策** | RouteReceipt 记录完整决策链路 |
| **降级容错** | LLM 失败 → 规则兜底，上游不可用 → fallback |
| **策略可对比** | 同一任务集多策略评测 |

---

## 局限性

1. **mock 模型**：当前使用 mock 模型评分，未接入真实模型调用
2. **LLM 依赖**：分析准确率 96%，仍有 4% 误判可能
3. **无本地模型**：critical 隐私级别会被 BLOCKED
4. **单次路由**：不支持多模型级联或投票
5. **静态策略**：未根据历史效果动态调整

---

## 后续方向

| 优先级 | 方向 | 说明 |
|--------|------|------|
| 🟡 | 接入真实模型 | 替换 mock 评分为真实调用 |
| 🟡 | 本地模型支持 | 解除 critical 级别的 BLOCKED |
| 🟡 | 动态策略 | 根据历史成功率自适应调整 |
| 🟢 | 多模型级联 | 支持 fallback 链 |
| 🟢 | 缓存优化 | 相同任务复用分析结果 |
| 🟢 | Dashboard | 可视化路由决策和统计 |

---