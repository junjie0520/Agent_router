# src/api/server.py

"""
FastAPI 服务器
"""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================
# 全局单例（延迟初始化）
# ============================================================

_engine = None
_audit_logger = None
_tracer = None


def init_engine(use_audit: bool = True, use_tracer: bool = True):
    """初始化引擎及审计/追踪模块"""
    global _engine, _audit_logger, _tracer

    from src.core.router.engine import RouterEngine, EngineConfig
    from src.core.router.feature_extractor import FeatureExtractor
    from src.core.router.decision_maker import DecisionMaker
    from src.core.features.llm_analyzer import LLMAnalyzer
    from src.core.router.rule_engine import RuleEngine
    from src.utils.validators import RoutingValidator
    from src.core.adapters.zhipu_adapter import ZhipuAdapter
    from config.settings import get_model_registry

    # 模型注册表
    registry = get_model_registry()
    model_dict = {
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "pricing": {
                    "input_per_1k": m.cost_per_1k_input_tokens,
                    "output_per_1k": m.cost_per_1k_output_tokens,
                },
                "latency_ms": m.latency_ms,
                "capability_score": 0.9 if "code" in m.capabilities else 0.5,
                "capabilities": m.capabilities,
                "is_local": m.is_local,
                "tee_enabled": m.supports_tee,
                "privacy_compliant": m.privacy_compliant,
            }
            for m in registry.list_models()
        ]
    }

    # 智谱 AI（免费 glm-4-flash）
    api_key = os.getenv("GLM_API_KEY", "your-glm-api-key")
    llm = ZhipuAdapter(
        api_key=api_key,
        model="glm-4-flash",
    )

    # LLM 分析器 + 规则引擎
    llm_analyzer = LLMAnalyzer(llm)
    rule_engine = RuleEngine()

    # 决策器
    decision_maker = DecisionMaker(
        llm_analyzer=llm_analyzer,
        rule_engine=rule_engine,
        model_registry=model_dict,
        validator=RoutingValidator(),
    )

    # 审计 & 追踪
    if use_audit:
        from src.core.audit.logger import AuditLogger
        _audit_logger = AuditLogger(log_dir="storage/audit", console=True)

    if use_tracer:
        from src.core.audit.tracer import Tracer
        _tracer = Tracer(log_dir="storage/traces", console=True)

    # 引擎
    _engine = RouterEngine(
        decision_maker=decision_maker,
        model_adapter=None,
        feature_extractor=FeatureExtractor(),
        validator=RoutingValidator(),
        config=EngineConfig(),
        audit_logger=_audit_logger,
        tracer=_tracer,
    )


def get_engine():
    global _engine
    if _engine is None:
        init_engine()
    return _engine


def get_audit_logger():
    global _audit_logger
    return _audit_logger


def get_tracer():
    global _tracer
    return _tracer


# ============================================================
# 应用生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine(use_audit=True, use_tracer=True)
    yield


# ============================================================
# 创建 FastAPI 应用
# ============================================================

app = FastAPI(
    title="Agent Router",
    description="智能路由网关 - 根据任务特征自动选择最优模型",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.routes import router
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": "Agent Router",
        "version": "0.1.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )