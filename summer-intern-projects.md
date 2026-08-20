# 隐私可信大模型系统 2026 暑期实习项目说明

> 面向三位暑期实习生。本文定义项目目标、最终交付物和验收标准；具体实现路线、技术选型细节和时间安排由实习生在调研后自行规划。

---

## 1. 项目背景

实验室长期关注大模型系统中的隐私保护、可信验证、Agent 工程和安全基础设施。随着大模型和 Agent 被用于代码、办公、财务、法务、科研和自动化任务，系统不再只是“把 prompt 发给模型再返回答案”，而是需要回答更复杂的问题：

- 用户或应用发送给模型的上下文中是否包含敏感信息？
- 敏感信息应该被允许、脱敏、阻断，还是要求人工确认？
- Agent 任务应该使用哪个模型，如何在质量、成本、延迟和隐私风险之间做权衡？
- 可信执行环境（TEE）和远程证明（attestation）到底证明了什么，如何让普通开发者理解和验证？
- 当系统从单节点变成集群后，如何判断每个节点当前是否可信？
- 如何把一次任务执行背后的隐私处理、模型路由、可信环境选择和验证结果沉淀成可审计证据？

本次暑期实习围绕三个方向展开：

| 项目 | 研究/工程问题 | 一句话目标 |
|------|---------------|------------|
| Agent 模型路由机制研究与优化 | 如何为不同 Agent 任务选择合适模型 | 做一个可评测、可解释的 Agent 模型路由原型。 |
| Agent 隐私过滤插件 | 如何在 Agent 上下文发给模型前拦截敏感信息 | 做一个本地隐私过滤插件或代理，让用户看到并控制模型实际接收的内容。 |
| TEE 集群 Attestation | 如何管理和验证一个可运行多种负载的 TEE pool | 做一个通用 TEE pool 的远程证明、状态管理与展示原型。 |

这三个项目既有工程属性，也有科研训练价值。每位同学主负责一个项目，但三者可以共享合成数据、评测脚本、receipt schema、展示材料和最终联合 demo。

---


## 2. 项目总原则

这三个项目不是课堂作业，也不是只写调研报告。最终需要做出可以运行、可以演示、可以复现的成果。

我们更看重：

- 是否把一个真实的大模型安全问题拆清楚。
- 是否做出了最小可运行原型。
- 是否有清晰的输入、输出、接口和失败行为。
- 是否有可复现测试数据、benchmark 或 demo script。
- 是否能说明设计取舍，而不是只堆功能。
- 是否能形成对外科研传播材料，例如技术博客、实验报告、开源 README 或 workshop demo。

本文不会规定具体实现路线和时间表。每位实习生需要在项目启动后自行调研，并提交一份简短项目方案，至少回答：

- 准备采用哪条实现路线，为什么？
- 依赖哪些开源项目、公开文档、模型服务、云资源或硬件环境？
- 最小可运行版本是什么？
- 如何评测结果是否有效？
- 最大技术风险是什么？如果主路线走不通，备选方案是什么？
- 计划如何安排时间和阶段性里程碑？

---

## 3. 所有项目的共同交付物

每个项目都需要交付以下内容。具体形式可以根据项目特点调整，但不能只交付代码或只交付文档。

### 3.1 可运行原型

- 有清晰入口，例如 CLI、Web demo、本地代理、SDK 示例、mock server 或 K8s demo。
- 支持本地或测试环境复现，不能只能在某个人电脑上运行。
- README 中包含从零启动 demo 的步骤。
- 代码结构清楚，后续同学能读懂并继续修改。

### 3.2 设计文档

设计文档至少包括：

- 项目背景和用户场景。
- 系统边界和非目标。
- 关键接口、数据结构或配置格式。
- 安全 / 隐私 / 信任模型。
- 主要失败模式和处理策略。
- 当前原型的局限性。
- 后续研究或工程扩展方向。

### 3.3 测试与评测

需要提供：

- 可复现测试样例或 fixture。
- 自动化测试脚本，至少覆盖核心路径和失败路径。
- 项目相关指标，例如质量、成本、延迟、误报率、漏报率、验证成功率、启动开销等。
- 一份评测报告，说明实验设置、结果、局限和下一步改进方向。

### 3.4 对外展示材料

每个项目都要能帮助实验室形成可展示的科研工程成果，因此需要准备至少两类展示材料：

- 一段 3-5 分钟 demo 视频或可现场演示的脚本。
- 一篇技术博客草稿、实验报告或开源项目 README。
- 一组架构图、流程图或截图，便于放到实验室主页、GitHub、组会汇报或学术交流材料中。


---

## 4. 项目一：Agent 模型路由机制研究与优化

### 4.1 背景

Agent 任务和普通聊天不同。一个 Agent 可能会读代码、改文件、调用工具、跑测试、总结长文档、分析日志、处理表格或执行多步工作流。不同任务对模型的要求差异很大：

- 简单问答可能适合低成本模型。
- 代码修改、复杂推理和长上下文任务可能需要更强模型。
- 包含敏感信息的任务需要优先走更严格的隐私保护链路。
- 工具调用不稳定时，模型能力、延迟和重试成本会被放大。
- 上游模型可能限流、降级、价格变化或临时不可用。

如果所有任务都固定使用同一个模型，要么成本过高，要么复杂任务效果不足。这个项目希望探索面向 Agent 的模型路由机制：在隐私和可信约束下，如何根据任务特征、历史效果、成本、延迟和风险，选择合适模型或模型组合。

### 4.2 项目目标

做出一个面向 Agent 场景的 `Agent Router` 独立原型。它不依赖任何私有代码仓库，但需要能够证明：

- 路由决策可以被记录、解释和复现。
- 路由结果在质量、成本或延迟上优于简单 baseline。
- 路由机制可以表达隐私等级、模型白名单、预算约束、fallback 和审计信息。
- 评测框架可以复用到未来其他 Agent 系统中。

### 4.3 最终交付物

#### 交付物 A：Agent 任务评测集（也可以调研现有的评测集）

需要构建一套可复现的 Agent 任务集合，至少覆盖以下几类任务中的三类：

- Coding：代码理解、bug 修复、测试生成、重构建议。
- Tool use：需要函数调用、搜索、数据库查询或命令执行的任务。
- Long context：长文档总结、跨文件问答、日志分析。
- Sensitive context：包含 PII、secret、内部配置或合成财务/法务数据的任务。
- Low-stakes routine：普通问答、格式转换、短文本分类等低成本任务。

评测集需要包含输入、期望行为、判分方式和样例输出。判分可以是自动化指标、规则检查、单元测试、人工 rubric 或混合方式，但必须可复现。

#### 交付物 B：路由原型

需要实现一个可运行路由原型，支持：

- 接收 OpenAI-compatible chat completion 请求，或接收可 replay 的 Agent trace。
- 支持多个候选模型、mock model adapter 或录制好的模型响应。
- 输出路由决策，包括选择的模型、候选模型、触发规则或特征、预估成本、隐私等级和 fallback 信息。
- 支持至少三种 baseline / policy 对比，例如固定强模型、固定便宜模型、规则路由、预算约束路由、质量优先路由或学习型路由。
- 记录每次请求的结构化日志，便于后续审计和分析。

原型可以是独立服务、离线 replay harness、CLI 工具或本地 proxy。具体路线由实习生调研决定。

#### 交付物 C：路由证据格式

设计一份 `routing receipt` 或 `route decision record` schema，用来描述一次路由为什么发生。它至少需要表达：

- request id / trace id。
- 用户请求的模型或策略。
- 实际调用的模型。
- 候选模型集合。
- 关键路由特征或策略版本。
- 隐私等级和是否要求可信执行。
- 成本、延迟、token 数等元数据。
- fallback / retry / error 信息。
- 可选签名字段，为后续可信审计预留。

这份 schema 不一定要做到密码学完整，但要能作为未来可信模型调用报告的一部分。

#### 交付物 D：评测报告

需要用同一套任务集比较路由策略和 baseline，至少回答：

- 路由是否降低了成本？
- 路由是否降低了延迟？
- 路由是否保持或提升了任务成功率？
- 哪些任务被错误路由？为什么？
- 如果引入隐私等级或可信执行约束，路由策略会如何变化？
- 哪些指标最适合进入长期实验监控？

#### 交付物 E：可展示 Demo

需要准备一个清晰 demo，例如：

```text
同一个 Agent 任务入口
  ├── 简单任务 → 路由到低成本模型
  ├── 复杂代码任务 → 路由到强模型
  ├── 含敏感信息任务 → 强制走隐私保护策略
  └── 上游失败 → 自动 fallback，并记录 route receipt
```

Demo 中应展示任务输入、路由决策、模型输出、成本/延迟对比和 route receipt。

### 4.4 验收标准

最低完成标准：

- 有一个可运行路由原型。
- 有一套可 replay 的 Agent 任务集。
- 至少比较三种路由策略或 baseline。
- 有结构化 route decision record。
- 有评测报告和 demo 脚本。

优秀标准：

- 能处理真实或接近真实的 Agent trace，而不仅是单轮 prompt。
- 能通过 mock adapter 稳定复现结果，不依赖私有服务。
- 评测结果能明确说明成本、质量、延迟之间的 tradeoff。
- route receipt 可以自然扩展为可信调用证据。
- 对外报告能讲清楚“Agent 为什么需要模型路由，而不是固定模型”。

### 4.5 非目标

- 不要求训练新的大模型。
- 不要求实现完整通用 Agent 框架。
---

## 5. 项目二：Agent 隐私过滤插件

### 5.1 背景

Agent 类工具正在读取越来越多本地上下文，包括代码仓库、终端输出、日志、配置文件、会议纪要、表格、工单、合同和截图 OCR 文本。用户经常不知道哪些内容会被发送给外部模型，也很难在发送前判断是否包含敏感信息。

典型风险包括：

- `.env`、API key、access token、数据库连接串、云厂商凭据。
- 姓名、电话、邮箱、地址、身份证件、银行卡、合同编号。
- 项目名单、报价、内部项目代号、未公开实验规划。
- 代码中的内部域名、私有 endpoint、密钥路径、日志中的用户信息。
- Agent 自动读取的上下文比用户显式输入更多。

这个项目希望做一个面向 Agent 的本地隐私过滤插件或代理：在内容离开用户机器、进入外部模型或远程服务之前，先完成扫描、预览、脱敏、阻断和审计。

### 5.2 项目目标

做出一个 `Agent Privacy Guard` 独立原型。它需要至少支持一个主流 Agent 或 Agent-like 工具，例如 Claude Code、Codex、WorkBuddy 或其他可调研工具。若目标工具的插件机制不稳定，也可以通过本地 OpenAI-compatible proxy、MCP server、CLI wrapper、hook 或 sidecar 的方式实现同等保护边界。

目标不是做一个完美 DLP 系统，而是证明：

- Agent 发送上下文前，可以被用户可见、可控地过滤。
- 敏感内容处理策略可以场景化配置。
- 隐私过滤不会严重破坏 Agent 的正常工作流。
- 过滤模块可以作为独立工具被其他 Agent 或应用复用。

### 5.3 最终交付物

#### 交付物 A：目标 Agent 集成

需要选择一个主 Agent 或一种代理方式作为主线，并说明为什么选择它。交付物需要包含：

- 集成方式说明，例如 hook、plugin、proxy、wrapper、MCP server 或本地 sidecar。
- 安装和启用步骤。
- 一条完整演示路径：用户使用 Agent 完成任务，Privacy Guard 在发送前拦截并处理上下文。
- 如果目标 Agent 无法稳定集成，需要提供等价 proxy demo，并在文档中说明限制。

建议优先选择能清楚拦截输入上下文的集成点，而不是为了追求覆盖多个工具而牺牲 demo 完整性。

#### 交付物 B：敏感内容检测与策略引擎

需要实现一个可配置策略引擎，至少覆盖：

- PII 检测：姓名、电话、邮箱、地址、证件号等。
- Secret scanning：API key、token、私钥、数据库 URL、云凭据等。
- 文件与路径规则：例如 `.env`、`id_rsa`、`credentials.json`、`node_modules`、大型二进制文件、内部配置目录。
- 代码和日志规则：内部 endpoint、cookie、authorization header、错误堆栈中的用户信息。

策略动作至少包括：

- `allow`：允许发送。
- `mask`：替换为占位符或安全摘要。
- `block`：阻断发送。

策略配置需要可读、可版本化，例如 YAML、JSON 或 TOML。不同场景可以有不同模板。

#### 交付物 C：发送前预览界面

需要提供一种用户可理解的预览方式，展示：

- Agent 原本准备发送什么。
- Privacy Guard 检测到了哪些敏感项。
- 模型实际会看到什么。
- 哪些内容被阻断、脱敏或需要确认。
- 用户是否进行了 override，以及 override 理由。

预览界面可以是 Web UI、终端 TUI、桌面窗口、浏览器页面或 Agent 内消息。重点是可理解和可演示。

#### 交付物 D：场景模板

至少提供三类场景模板：

- Coding：保护代码仓库、secret、日志、内部 endpoint。
- Office / Support：保护邮件、会议纪要、表格、工单、联系方式。
- Finance / Legal：保护合同、发票、报销、账号、金额上下文中的敏感字段。

每个模板需要包含：

- 策略配置。
- 样例输入。
- 期望处理结果。
- 适用边界和可能误报。

#### 交付物 E：评测集与效果报告

需要构建一套合成测试语料，覆盖正常内容、敏感内容和边界情况。报告至少包含：

- secret 命中率和误报样例。
- PII 命中率和误报样例。
- 平均处理延迟。
- 对 Agent 正常任务完成的影响。
- 误报 / 漏报最常见来源。
- 哪些策略适合做成通用插件能力，哪些只适合特定场景。

#### 交付物 F：可展示 Demo

需要准备至少三个 demo 场景：

- Coding Agent 试图读取 `.env` 或日志，插件阻断 secret 泄露。
- Agent 总结合成联系人资料，插件脱敏姓名、邮箱、电话等 PII。
- Agent 处理合成财务或法务文本，插件在保留任务语义的同时隐藏敏感字段。

Demo 要能展示“原始上下文”和“模型实际看到的上下文”的差异。

### 5.4 验收标准

最低完成标准：

- 至少集成一个 Agent 或提供等价本地代理。
- 能对真实文件和合成上下文执行 allow / mask / block。
- 有发送前预览。
- 有三类策略模板。
- 有测试语料、评测报告和 demo 脚本。

优秀标准：

- 能以 OpenAI-compatible proxy、MCP server 或 CLI wrapper 的方式被多个工具复用。
- 能覆盖多轮 Agent 上下文，而不是只处理单条 prompt。
- 能处理文件读取、终端输出、diff、日志片段等 Agent 常见输入。
- 用户体验足够自然，不会让正常 Agent 工作流无法使用。
- 对外报告能讲清楚“Agent 隐私泄露通常发生在用户看不见的上下文层”。

### 5.5 非目标

- 不要求替代企业 DLP 系统。
- 不要求保证零漏报。
- 不要求同时支持所有 Agent。
---

## 6. 项目三：TEE Pool Attestation 与可信资源管理

### 6.1 背景

可信执行环境和远程证明是可信 AI 系统里的关键技术，但它们本身不应该和某一种具体工作负载绑定。TEE 可以运行大模型推理，也可以运行 PII 检测、密钥管理、数据库查询、RAG 检索、日志审计、策略执行、数据清洗或任意需要隔离保护的服务。

因此，这个项目是要做一个通用 TEE pool。Pool 中有一组可被验证的 TEE 资源，外部系统可以根据策略选择一个可信资源来运行某种 workload。远程验证层负责回答“这个 TEE 是否可信、状态是否新鲜、是否符合策略”；workload 层负责回答“在这个 TEE 里实际运行什么任务”。两者需要解耦。

真实系统通常会遇到这些问题：

- 多个 TEE 节点或 Pod 组成资源池，同时承载不同 workload。
- 节点会注册、下线、滚动升级、扩缩容和重启。
- 不同节点可能处于不同 attestation 状态。
- 不同 workload 对 TEE 类型、measurement、镜像版本、资源规格和新鲜度要求不同。
- 调度器需要知道哪些 TEE 当前可用、可信、适合运行某类任务。
- 用户或上层系统不仅想知道“有 TEE 存在”，还想知道“这个任务被分配到了哪个可信 TEE，验证结果是什么”。

### 6.2 项目目标

做出一个 `TEE Pool Attestation` 独立原型，围绕通用 TEE 资源池的注册、验证、状态管理、策略匹配和展示展开。它需要回答：

- 一个 TEE pool 中的节点身份、能力和 attestation 状态如何表示？
- 远程验证结果如何从具体 workload 中解耦出来？
- 不同 workload 如何声明自己需要什么样的可信执行环境？
- Pool 如何根据 attestation result、resource metadata 和 policy 选择合适节点？
- 节点滚动升级、measurement 变化、证明过期、节点降级时系统应该如何表现？
- 哪些信息应该公开给 workload 使用方，哪些只适合内部实验记录？

项目可以基于 mock attestation、CoCo AS sample mode、TDX fixture 或真实 TDX 环境。是否接入真实硬件由实习生调研资源后决定，但必须保证 mock / fixture 路径可稳定复现。

### 6.3 推荐系统抽象

项目原型建议至少包含以下抽象。具体接口和实现路线由实习生调研后确定。

```text
Workload Request
    ├── workload_type: llm-inference / pii-scan / key-service / rag / generic
    ├── trust_policy: required TEE type, measurement allowlist, freshness
    └── resource_request: cpu / memory / gpu / network / labels
        ↓
TEE Pool Controller
    ├── node registry
    ├── attestation verifier
    ├── policy matcher
    ├── scheduler / allocator
    └── receipt generator
        ↓
TEE Pool
    ├── tee-node-a: verified, measurement M1, supports workload A/B
    ├── tee-node-b: degraded, proof expired
    └── tee-node-c: failed, measurement mismatch
```

这里的 `llm-inference` 只是一种 workload 示例，不是 TEE pool 的核心假设。一个设计良好的 TEE pool 应该可以换成其他 workload，而 attestation、状态管理和策略匹配逻辑基本不变。

### 6.4 最终交付物

#### 交付物 A：TEE Pool 信任模型文档

需要写清楚至少以下内容：

- TEE pool、TEE node、workload、policy、verifier、scheduler / allocator 的职责边界。
- 远程验证层和 workload 执行层如何解耦。
- 单节点 attestation、pool-level inventory、per-allocation receipt、per-request binding 的区别。
- `no-ra`、`sample/mock`、`tdx` 等模式分别证明了什么、没有证明什么。
- 平台 attestation 和 workload measurement / image digest / runtime config 的区别。
- 证明 freshness、证书轮换、measurement allowlist、撤销和降级策略。
- 简化实验模型和严格零信任模型之间的差异。

这份文档需要避免“证明了一切”的表述，必须明确每种方案的信任边界。尤其要说明：验证某个 TEE 节点可信，不等于自动证明任意 workload 的业务逻辑正确；证明 workload 镜像或 measurement，也不等于证明其输出一定正确。

#### 交付物 B：TEE Pool Controller 原型

需要实现一个可运行原型，用来管理多个 TEE 节点的注册、证明状态和可分配能力。它可以是 CLI、Web dashboard、mock controller service 或独立 verifier service。

原型至少需要支持：

- 注册或发现多个 TEE 节点。
- 为每个节点记录 attestation 类型、measurement、image digest 或 mock equivalent、证书状态、最近验证时间、过期时间、资源标签和支持的 workload 类型。
- 输出节点状态：`verified`、`degraded`、`expired`、`failed`、`unknown`。
- 支持 workload policy 匹配，例如“只允许 verified TDX 节点运行高隐私 workload”“必须匹配 measurement allowlist”“证明必须在 N 分钟内新鲜”。
- 支持简单 allocator，从符合条件的节点中选择一个可用节点。
- 提供 JSON 输出或 HTTP API，便于其他原型系统集成。

#### 交付物 C：Workload Policy 与 Node Metadata Schema

需要设计两类 schema。

`node metadata` 至少需要表达：

- node id / pool id。
- TEE type，例如 mock、TDX、SEV-SNP、SGX。
- attestation status 和验证时间。
- measurement / image digest / runtime config digest。
- supported workload types。
- resource labels，例如 CPU、memory、GPU、region、实验标签。
- certificate / identity 信息。
- status freshness 和过期时间。

`workload policy` 至少需要表达：

- workload id / workload type。
- required tee type。
- required attestation level。
- measurement 或 image allowlist。
- freshness requirement。
- resource requirement。
- fallback policy，例如是否允许 degraded 节点、是否允许 no-ra mock。

#### 交付物 D：TEE Allocation / Attestation Receipt Schema

需要设计一份 `tee allocation receipt` 或 `attestation receipt` schema，用来描述一次 workload allocation 所依赖的可信证明。它至少需要包含：

- allocation id / trace id。
- workload id / workload type。
- pool id / node id。
- node attestation type。
- node measurement / image digest / policy id。
- policy evaluation result。
- verification result。
- verifier identity 和验证时间。
- receipt 生成时间和有效期。
- 签名字段或未来签名扩展位。

这份 receipt 的核心语义是“某个 workload 被分配到某个符合策略的 TEE 节点”，而不是“某次大模型推理一定正确”。如果和项目一联动，可以额外包含 route decision id，但不能把 TEE pool 设计成只服务模型路由。

#### 交付物 E：多 Workload Demo

需要准备一个可以演示的 TEE pool 场景，至少包含三类节点或状态：

- 正常 verified 节点。
- measurement 不在 allowlist 或模拟篡改的 failed 节点。
- 证明过期、未启用 RA 或 mock degraded 节点。

同时至少包含两类不同 workload，例如：

- `llm-inference`：模拟大模型推理服务。
- `pii-scan`：模拟隐私检测服务。
- `key-service`：模拟密钥签发或解密服务。
- `rag-index`：模拟检索或索引服务。
- `generic-job`：任意批处理任务。

Demo 需要展示：

- 系统如何发现不同节点状态。
- 不同 workload 如何声明不同 trust policy。
- Pool 如何为不同 workload 选择不同可信节点。
- 节点滚动升级后 measurement 改变时如何处理。
- failed / degraded 节点如何被排除、降级使用或要求人工确认。
- 用户或管理员如何看到验证结果和 allocation receipt。

#### 交付物 F：测试与评测报告

需要提供：

- mock evidence / fixture。
- 验证成功、验证失败、过期、allowlist mismatch、签名错误等测试。
- workload policy 匹配和 allocator 测试。
- pool 规模变化时的验证开销估算。
- 节点注册、状态刷新、分配决策的延迟评估。
- 安全分析：当前原型能防什么，不能防什么。

#### 交付物 G：可视化或开发者工具

需要提供一种对外展示方式，例如：

- `tee-pool status` CLI。
- `tee-pool allocate workload.yaml` CLI。
- `tee-pool verify receipt.json` CLI。
- Web 页面展示 pool inventory、trust chain、policy match 和 allocation receipt。
- Dashboard 展示 TEE pool 节点可信状态。
- 可嵌入文档的验证报告截图。

重点是让非 TEE 专家也能理解“这个 pool 里有哪些可信资源、它们能运行哪些负载、为什么某个 workload 被分配到某个节点”。

### 6.5 验收标准

最低完成标准：

- 有 TEE pool 信任模型文档。
- 有可运行 pool controller / verifier / dashboard / CLI 原型。
- 有 node metadata、workload policy 和 allocation receipt schema。
- 有至少三类节点状态 demo。
- 有至少两类 workload demo，不能只演示大模型推理一种负载。
- 有 fixture、测试和评测报告。

优秀标准：

- 能通过 mock API、sample mode 或 fixture 稳定复现完整验证链路。
- 能支持 CoCo AS sample mode 或真实 TDX evidence。
- 能清楚展示 attestation 层、pool 管理层和 workload 执行层的解耦。
- 能把 workload policy、node metadata、attestation result 和 allocation receipt 串成完整链路。
- 能清楚展示“只证明硬件 TEE”“证明 workload measurement”“证明某次 allocation 符合策略”之间的差异。
- 对外报告能讲清楚“TEE pool 是可验证可信资源池，而不是某个具体业务服务的附属模块”。

### 6.6 非目标

- 不要求自研 DCAP verifier。
- 不要求完成正式部署级别的 KBS / HSM / KMS。
- 不要求覆盖所有 TEE 平台。
- 不要求证明所有 Kubernetes 控制面安全问题。
- 不要求实现真实大模型推理、真实 PII 服务或真实密钥服务。
- 不要求接入任何私有集群或长期运行环境。

---

## 7. 三个项目的联合 Demo（大背景，选做）

虽然三位同学各自负责一个项目，但最终最好能形成一条统一故事线：

```text
开发者使用 Agent 处理一个包含敏感上下文的任务
    ↓
Agent Privacy Guard 在本地发现 secret / PII，进行阻断或脱敏
    ↓
请求进入一个 mock 模型服务入口
    ↓
Agent Router 根据任务复杂度、隐私等级、预算和模型状态选择模型
    ↓
Mock 模型服务把 `llm-inference` 作为一种 workload 提交给 TEE Pool
    ↓
TEE Pool 根据 workload policy 选择符合条件的可信节点，并生成 allocation / attestation receipt
    ↓
用户看到模型回答，同时可以查看：
    ├── 模型实际看到了什么
    ├── 为什么路由到这个模型
    └── 这个 workload 被分配到哪个可信节点，证明和策略匹配是否有效
```

这个联合 demo 的价值是对外讲清楚一条完整研究链路：

- 发送前有隐私控制。
- 调用中有智能路由。
- 执行时有可验证的 TEE pool 分配。
- 调用后有可信证据和 allocation receipt。

如果三个项目都完成到可串联状态，可以沉淀为实验室的教学 demo、组会展示、技术博客系列或开源样例仓库。

---

## 8. 项目方案模板

每位实习生启动项目后，需要提交自己的项目方案。建议结构如下：

```markdown
# 项目名称

## 1. 我理解的问题

## 2. 用户场景和最终 demo

## 3. 技术路线候选

## 4. 我选择的路线和原因

## 5. 最小可运行版本定义

## 6. 关键交付物

## 7. 评测方法

## 8. 风险和备选方案

## 9. 时间安排

## 10. 需要导师或团队提供的资源
```

---

## 9. 评审标准

最终评审不只看功能数量，而看项目是否形成可复用资产。

| 维度 | 关注点 |
|------|--------|
| 工程完成度 | 原型是否可运行、可复现、边界清楚、失败路径可处理。 |
| 研究相关性 | 是否能增强对隐私保护、可信验证或模型路由问题的理解。 |
| 评测严谨性 | 是否有测试数据、baseline、指标和可解释结果。 |
| 展示效果 | 是否能在 3-5 分钟内讲清楚价值并现场演示。 |
| 沉淀价值 | 是否留下代码、schema、接口、文档、数据集或后续研究建议。 |
| 对外传播 | 是否适合写成博客、README、组会材料、workshop demo 或开源样例。 |

---

## 10. 建议阅读关键词

大模型系统与 Agent：

- OpenAI-compatible API
- Agent routing / LLM routing / model cascade
- Tool-use agent evaluation
- Agent trace replay
- Cost-quality-latency tradeoff

隐私过滤：

- Secret scanning
- PII detection
- Data loss prevention
- Named Entity Recognition
- Policy engine
- MCP / local proxy / CLI wrapper / hooks

可信执行与远程证明：

- Trusted Execution Environment
- Remote Attestation
- IETF RATS architecture
- Confidential Containers / CoCo Trustee Attestation Service
- Intel TDX / AMD SEV-SNP
- Evidence, endorsement, measurement, attestation result

