# config/settings.py
import os
import yaml
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass


# ============================================================
# 环境变量 & 基础配置
# ============================================================

class Settings:
    """全局配置"""
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    
    # 策略选择（通过环境变量切换）
    ROUTING_POLICY: str = os.getenv("ROUTING_POLICY", "cost_first")
    
    # 模型注册表路径
    MODEL_REGISTRY_PATH: Path = PROJECT_ROOT / "config" / "models" / "registry.yaml"
    
    # 数据集路径
    DATASET_DIR: Path = PROJECT_ROOT / "datasets"
    
    # 日志级别
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()


# ============================================================
# 模型注册表
# ============================================================

@dataclass
class ModelSpec:
    """模型规格"""
    id: str
    name: str
    provider: str
    cost_per_1k_input_tokens: float
    cost_per_1k_output_tokens: float
    latency_ms: float
    capabilities: List[str]
    supports_tee: bool
    is_local: bool
    privacy_compliant: bool
    
    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities
    
    def estimate_cost(self, input_tokens: int, output_tokens: int = 0) -> float:
        input_cost = (input_tokens / 1000) * self.cost_per_1k_input_tokens
        output_cost = (output_tokens / 1000) * self.cost_per_1k_output_tokens
        return round(input_cost + output_cost, 6)


class ModelRegistry:
    """模型注册表"""
    
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = settings.MODEL_REGISTRY_PATH
        
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        
        self.models: List[ModelSpec] = [
            ModelSpec(**m) for m in raw["models"]
        ]
        self._model_map = {m.id: m for m in self.models}
    
    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        return self._model_map.get(model_id)
    
    def list_models(self) -> List[ModelSpec]:
        return self.models
    
    def filter_by_capabilities(
        self,
        required: Optional[List[str]] = None,
        preferred: Optional[List[str]] = None,
    ) -> List[ModelSpec]:
        results = self.models
        if required:
            results = [m for m in results if all(m.has_capability(c) for c in required)]
        if preferred and results:
            preferred_matches = [m for m in results if any(m.has_capability(c) for c in preferred)]
            if preferred_matches:
                results = preferred_matches
        return results
    
    def filter_by_privacy(
        self,
        privacy_compliant: Optional[bool] = None,
        tee_required: bool = False,
        local_only: bool = False,
    ) -> List[ModelSpec]:
        results = self.models
        if privacy_compliant is not None:
            results = [m for m in results if m.privacy_compliant == privacy_compliant]
        if tee_required:
            results = [m for m in results if m.supports_tee]
        if local_only:
            results = [m for m in results if m.is_local]
        return results
    
    def get_default_model(self) -> ModelSpec:
        return min(self.models, key=lambda m: m.cost_per_1k_input_tokens)


# 全局单例
_model_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry()
    return _model_registry