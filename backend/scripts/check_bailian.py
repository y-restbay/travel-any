"""百炼云知识库连通性自检。

读取 .env 里的 BAILIAN_* 配置，用和正式聊天流完全一致的方式调一次
百炼 Retrieve 检索，把成功/失败原因明确打出来，省得靠走完整聊天流试错。

跑法:
    cd backend && source .venv/bin/activate && python -m scripts.check_bailian
可选自定义查询:
    python -m scripts.check_bailian "北京三日游怎么安排"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings


def _mask(value: str | None) -> str:
    if not value:
        return "<空>"
    if len(value) <= 8:
        return value[0] + "***"
    return f"{value[:4]}***{value[-4:]}"


def _hint(message: str) -> str:
    low = message.lower()
    if "invalidaccesskeyid" in low or "signaturedoesnotmatch" in low:
        return "→ AccessKey ID/Secret 不对。注意要用 LTAI... 的 AK/SK，不是 sk- 开头的 API-Key。"
    if "noworkspacepermission" in low or "no workspace permission" in low:
        return ("→ AK/SK 对应的 RAM 用户无权访问该业务空间。先确认 AK/SK 与 WorkspaceId "
                "属于同一阿里云账号；再在百炼控制台「业务空间管理 → 成员管理」把该 RAM 用户加进去，"
                "并在 RAM 授予 AliyunBailianDataFullAccess。")
    if "forbidden" in low or "nopermission" in low or "not authorized" in low or "no permission" in low:
        return "→ 鉴权通过但没权限。给这个 RAM 用户授权 AliyunBailianDataFullAccess 策略。"
    if "workspace" in low:
        return "→ WorkspaceId 不对。换成业务空间里 llm- 开头的那个 ID 再试（不是 ws-）。"
    if "index" in low and ("notfound" in low or "not found" in low or "invalid" in low or "not exist" in low):
        return "→ IndexId 不对。去知识库详情页取「知识库ID」（CreateIndex 返回的 Data.Id），不是 ws-。"
    if "endpoint" in low or "could not connect" in low or "timed out" in low or "timeout" in low or "name or service" in low:
        return f"→ 连不上。多半是地域/Endpoint 不对，知识库在哪个地域就用对应 endpoint。"
    return "→ 未归类错误，把上面整段贴出来一起看。"


def main() -> int:
    settings = get_settings()
    query = sys.argv[1] if len(sys.argv) > 1 else "连通性测试"

    ak = (settings.bailian_access_key_id or "").strip()
    sk = (settings.bailian_access_key_secret or "").strip()
    workspace_id = (settings.bailian_workspace_id or "").strip()
    index_id = (settings.bailian_index_id or "").strip()
    endpoint = settings.bailian_endpoint

    print("=== 加载到的配置（来自 .env / settings）===")
    print(f"  BAILIAN_ACCESS_KEY_ID     = {_mask(ak)}")
    print(f"  BAILIAN_ACCESS_KEY_SECRET = {_mask(sk)}")
    print(f"  BAILIAN_WORKSPACE_ID      = {workspace_id or '<空>'}")
    print(f"  BAILIAN_INDEX_ID          = {index_id or '<空>'}")
    print(f"  BAILIAN_ENDPOINT          = {endpoint}")
    print()

    missing = [
        name
        for name, val in [
            ("BAILIAN_ACCESS_KEY_ID", ak),
            ("BAILIAN_ACCESS_KEY_SECRET", sk),
            ("BAILIAN_WORKSPACE_ID", workspace_id),
            ("BAILIAN_INDEX_ID", index_id),
        ]
        if not val
    ]
    if missing:
        print(f"[FAIL] 缺少配置: {', '.join(missing)} —— 先在 .env 填全这四项再跑。")
        return 1

    if ak.startswith("sk-"):
        print("[FAIL] AccessKey ID 是 sk- 开头 —— 这是 DashScope API-Key，不是阿里云 AccessKey。")
        print("       Retrieve OpenAPI 只认 LTAI... 形式的 AK/SK，去「AccessKey 管理」重新创建。")
        return 1

    try:
        from alibabacloud_bailian20231229 import models as bailian_models
        from alibabacloud_bailian20231229.client import Client as BailianClient
        from alibabacloud_tea_openapi import models as open_api_models
    except ImportError as exc:
        print(f"[FAIL] 百炼 SDK 未安装: {exc}")
        print("       先跑: pip install -r requirements.txt")
        return 1

    try:
        client = BailianClient(
            open_api_models.Config(
                access_key_id=ak,
                access_key_secret=sk,
                endpoint=endpoint,
                read_timeout=int(settings.bailian_timeout * 1000),
                connect_timeout=int(settings.bailian_timeout * 1000),
            )
        )
        request = bailian_models.RetrieveRequest(index_id=index_id, query=query)
        print(f"=== 调用 Retrieve（query={query!r}）===")
        response = client.retrieve(workspace_id, request)
    except Exception as exc:  # noqa: BLE001  自检脚本要看到所有异常
        message = f"{exc.__class__.__name__}: {exc}"
        print(f"[FAIL] 调用失败: {message}")
        print(_hint(message))
        return 1

    body = getattr(response, "body", None)
    err = body.to_map() if body is not None else {}
    status = err.get("Status")
    if (status and int(status) >= 400) or (err.get("Code") and not err.get("Data")):
        message = f"{err.get('Code')}: {err.get('Message')} (Status={status}, RequestId={err.get('RequestId')})"
        print(f"[FAIL] 网关返回错误（鉴权/权限/参数未通过，并非 0 召回）: {message}")
        print(_hint(f"{err.get('Code', '')} {err.get('Message', '')}"))
        return 1

    data = getattr(body, "data", None)
    nodes = getattr(data, "nodes", None) or []

    print(f"[PASS] 鉴权 + WorkspaceId + IndexId 全部有效，返回 {len(nodes)} 个片段。")
    if not nodes:
        print("       注意: 检索通了但 0 召回——知识库可能还没传文档/还在索引中，或这个 query 无相关内容。")
        return 0

    first = nodes[0]
    text = getattr(first, "text", None) or (first.get("text") if isinstance(first, dict) else "")
    score = getattr(first, "score", None) or (first.get("score") if isinstance(first, dict) else None)
    metadata = getattr(first, "metadata", None) or (first.get("metadata") if isinstance(first, dict) else {})
    preview = str(text).strip().replace("\n", " ")[:120]
    print(f"  首片 score={score} metadata_keys={list((metadata or {}).keys())}")
    print(f"  首片预览: {preview}...")
    print()
    print("如果 metadata 字段名和 cloud_kb.py 里取的对不上，把上面这行 metadata_keys 贴给我校准。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
