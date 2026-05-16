"""百炼云知识库「文件在但 0 召回」专项诊断。

check_bailian 证明鉴权/WorkspaceId/IndexId 都有效但 0 召回时，用这个脚本
直接列出该 IndexId 下的文档及其导入状态，区分到底是：
  - 索引里压根没文档（文件只是传到了数据中心，没加进这个知识库）
  - 文档在但状态不是 FINISH（还在解析 / 导入失败）
  - 文档都 FINISH 却仍 0 召回（→ 地域 endpoint 或检索参数问题）

跑法:
    cd backend && .venv/bin/python -m scripts.diag_bailian_docs
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings


def main() -> int:
    s = get_settings()
    ws = (s.bailian_workspace_id or "").strip()
    index_id = (s.bailian_index_id or "").strip()

    from alibabacloud_bailian20231229 import models as bm
    from alibabacloud_bailian20231229.client import Client as BailianClient
    from alibabacloud_tea_openapi import models as om

    client = BailianClient(
        om.Config(
            access_key_id=(s.bailian_access_key_id or "").strip(),
            access_key_secret=(s.bailian_access_key_secret or "").strip(),
            endpoint=s.bailian_endpoint,
            read_timeout=int(s.bailian_timeout * 1000),
            connect_timeout=int(s.bailian_timeout * 1000),
        )
    )

    print(f"=== ListIndexDocuments  workspace={ws}  index={index_id}  endpoint={s.bailian_endpoint} ===")
    try:
        req = bm.ListIndexDocumentsRequest(index_id=index_id, page_number=1, page_size=50)
        resp = client.list_index_documents(ws, req)
    except Exception as exc:  # noqa: BLE001  诊断脚本要看到原始异常
        print(f"[FAIL] {exc.__class__.__name__}: {exc}")
        return 1

    body = getattr(resp, "body", None)
    err = body.to_map() if body is not None else {}
    status = err.get("Status")
    if (status and int(status) >= 400) or (err.get("Code") and not err.get("Data")):
        print(f"[FAIL] 网关错误（不是没文档）: {err.get('Code')}: {err.get('Message')} "
              f"(Status={status}, RequestId={err.get('RequestId')})")
        if "workspacepermission" in str(err.get("Code", "")).lower():
            print("→ RAM 用户无权访问该业务空间。确认 AK/SK 与 WorkspaceId 同属一个阿里云账号，"
                  "并在百炼「业务空间管理 → 成员管理」把该 RAM 用户加入、RAM 授予 AliyunBailianDataFullAccess。")
        return 1

    data = getattr(body, "data", None)
    docs = getattr(data, "documents", None) or []
    total = getattr(data, "total_count", None)
    print(f"success={getattr(body, 'success', None)}  total_count={total}  本页 {len(docs)} 条")

    if not docs:
        print("[结论] 这个 IndexId 里没有任何文档 —— 文件可能只传到了「数据管理」，"
              "没有被「导入到这个知识库」。去控制台把文件加入该知识库并等待索引完成。")
        return 0

    from collections import Counter
    status_count = Counter()
    for d in docs:
        name = getattr(d, "name", None) or getattr(d, "document_name", None) or "?"
        status = getattr(d, "status", None) or getattr(d, "document_status", None) or "?"
        code = getattr(d, "code", None)
        msg = getattr(d, "message", None)
        status_count[str(status)] += 1
        line = f"  - {name}  status={status}"
        if code or msg:
            line += f"  code={code} msg={msg}"
        print(line)

    print(f"[状态汇总] {dict(status_count)}")
    print("FINISH/成功 之外的状态（RUNNING=还在跑, *ERROR/FAILED=导入失败）就是 0 召回的原因。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
