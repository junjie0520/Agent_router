"""
审计凭证工具
RouteReceipt 的签名、验证、导入导出
"""
import json
import hmac
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from src.core.schemas.receipt import RouteReceipt


# ============================================================
# 签名 & 验证
# ============================================================

def sign_receipt(receipt: RouteReceipt, secret: str, algorithm: str = "sha256") -> RouteReceipt:
    """
    对 RouteReceipt 进行 HMAC 签名，防篡改

    Args:
        receipt: 路由凭证
        secret: 签名密钥
        algorithm: 哈希算法 (sha256 / sha512)

    Returns:
        已签名的凭证（原地修改 + 返回）
    """
    payload = _receipt_to_canonical_json(receipt)

    if algorithm == "sha512":
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha512).hexdigest()
    else:
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    receipt.signature = sig
    receipt.signature_algorithm = f"hmac-{algorithm}"
    return receipt


def verify_receipt(receipt: RouteReceipt, secret: str) -> bool:
    """
    验证 RouteReceipt 签名

    Args:
        receipt: 路由凭证
        secret: 签名密钥

    Returns:
        True 表示签名有效
    """
    if not receipt.signature:
        return False

    alg = receipt.signature_algorithm or "hmac-sha256"
    hash_name = alg.replace("hmac-", "")

    payload = _receipt_to_canonical_json(receipt)
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        getattr(hashlib, hash_name, hashlib.sha256),
    ).hexdigest()

    return hmac.compare_digest(receipt.signature, expected)


def _receipt_to_canonical_json(receipt: RouteReceipt) -> str:
    """转为规范 JSON（排除签名字段）"""
    data = json.loads(receipt.model_dump_json())
    data.pop("signature", None)
    data.pop("signature_algorithm", None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


# ============================================================
# 文件导入导出
# ============================================================

def export_receipt(receipt: RouteReceipt, filepath: Path) -> Path:
    """
    导出单个凭证到 JSON 文件

    Args:
        receipt: 路由凭证
        filepath: 目标文件路径

    Returns:
        写入的文件路径
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(receipt.model_dump_json(indent=2, ensure_ascii=False))

    return filepath


def import_receipt(filepath: Path) -> RouteReceipt:
    """
    从 JSON 文件加载凭证

    Args:
        filepath: JSON 文件路径

    Returns:
        RouteReceipt 实例

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: JSON 格式无效
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"凭证文件不存在: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return RouteReceipt(**data)


def export_receipts_batch(receipts: List[RouteReceipt], filepath: Path) -> Path:
    """
    批量导出凭证到 JSON Lines 文件

    Args:
        receipts: 凭证列表
        filepath: JSONL 文件路径

    Returns:
        写入的文件路径
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        for r in receipts:
            f.write(r.model_dump_json(ensure_ascii=False) + "\n")

    return filepath


def import_receipts_batch(filepath: Path) -> List[RouteReceipt]:
    """
    从 JSON Lines 文件批量加载凭证

    Args:
        filepath: JSONL 文件路径

    Returns:
        凭证列表
    """
    filepath = Path(filepath)
    receipts = []

    if not filepath.exists():
        return receipts

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            receipts.append(RouteReceipt(**json.loads(line)))

    return receipts


# ============================================================
# 审计摘要
# ============================================================

def summarize_receipt(receipt: RouteReceipt) -> dict:
    """
    生成凭证的审计摘要（单行可搜索格式）

    Returns:
        扁平化摘要字典，适合写入结构化日志
    """
    return {
        "receipt_id": receipt.receipt_id,
        "request_id": receipt.request_id,
        "trace_id": receipt.trace_id,
        "timestamp": receipt.timestamp.isoformat(),
        "selected_model": receipt.selected_model,
        "decision_reason": receipt.decision_reason.value,
        "task_type": receipt.task_type.value,
        "privacy_level": receipt.privacy_level.value,
        "complexity_score": receipt.complexity_score,
        "estimated_cost_usd": receipt.estimated_cost.total_cost,
        "actual_cost_usd": receipt.actual_cost.total_cost if receipt.actual_cost else None,
        "estimated_latency_ms": receipt.estimated_latency_ms,
        "actual_latency_ms": receipt.actual_latency_ms,
        "is_fallback": receipt.is_fallback,
        "fallback_depth": len(receipt.fallback_chain),
        "privacy_passed": receipt.privacy_checks_passed,
        "pii_detected": ",".join(receipt.pii_detected) if receipt.pii_detected else "",
        "error_count": len(receipt.errors),
        "warning_count": len(receipt.warnings),
        "signed": receipt.signature is not None,
    }


def diff_receipts(a: RouteReceipt, b: RouteReceipt) -> dict:
    """
    比较两个凭证的差异

    Returns:
        {field: (value_a, value_b), ...} 仅返回不同的字段
    """
    da = json.loads(a.model_dump_json())
    db = json.loads(b.model_dump_json())

    diffs = {}
    all_keys = set(da.keys()) | set(db.keys())

    for key in sorted(all_keys):
        va = da.get(key)
        vb = db.get(key)
        if va != vb:
            diffs[key] = (va, vb)

    return diffs

""""
============================================================
函数速查表
============================================================

签名/验证:
  sign_receipt(receipt, secret, algorithm="sha256") -> RouteReceipt
  verify_receipt(receipt, secret) -> bool

导入/导出:
  export_receipt(receipt, filepath) -> Path
  import_receipt(filepath) -> RouteReceipt
  export_receipts_batch(receipts, filepath) -> Path
  import_receipts_batch(filepath) -> List[RouteReceipt]

摘要/对比:
  summarize_receipt(receipt) -> dict
  diff_receipts(a, b) -> dict

============================================================
"""