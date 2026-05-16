"""阿里云百炼云知识库检索。

只调用百炼 ``Retrieve`` 纯检索接口：召回与重排（``EnableReranking`` 服务端默认 true）
都在云端完成，本模块拿到的就是云端重排后的 Top-N 切片，直接注入本系统的大模型。
**绝不调用百炼应用 / Assistant 等会返回"生成好答案"的接口。**

返回结构与本地 RAG 的 :class:`RetrieveResult` 完全一致，因此 chat_service
的上下文注入与 meta 逻辑无需任何改动即可复用。

容错策略：未配置凭证、缺少 SDK、或调用失败时，都返回空 RetrieveResult
而不抛异常——前端表现为"云知识库本轮无召回"，本地知识库路径不受影响。

v1 仅处理文本切片，``Metadata.image_url`` 等图文字段暂不注入（二期）。
"""

import logging
from typing import Any, List

from app.core.config import get_settings
from app.rag.schemas import QueryAnalysis, RetrievedContext, RetrieveResult

logger = logging.getLogger(__name__)

# 云知识库走单独一路，沿用 QueryAnalysis 结构让 meta/debug 面板照常展示。
_CLOUD_ANALYSIS = QueryAnalysis(
    routes=["cloud"],
    reasoning="云知识库（阿里云百炼）检索，召回与重排均在云端完成",
    route_weights={"cloud": 1.0},
    decision_source="cloud",
)


def _empty(query: str) -> RetrieveResult:
    return RetrieveResult(query=query, analysis=_CLOUD_ANALYSIS, contexts=[], context_block="")


def _format_context_block(contexts: List[RetrievedContext]) -> str:
    if not contexts:
        return ""
    lines = [
        "以下是云知识库（阿里云百炼）召回并重排后的参考资料，请优先基于这些资料回答，并在不确定时说明："
    ]
    for index, context in enumerate(contexts, start=1):
        filename = context.metadata.get("filename", "unknown")
        text = context.text.strip()
        if len(text) > 700:
            text = f"{text[:700]}..."
        lines.append(f"[{index}] source={context.source} score={context.score:.3f} file={filename}\n{text}")
    return "\n\n".join(lines)


def _node_attr(node: Any, *names: str, default: Any = None) -> Any:
    """百炼 SDK node 字段在不同版本下可能是属性或 dict key，统一兜底取值。"""
    for name in names:
        value = getattr(node, name, None)
        if value is None and isinstance(node, dict):
            value = node.get(name)
        if value is not None:
            return value
    return default


def retrieve_cloud_context(query: str, top_k: int = 5) -> RetrieveResult:
    settings = get_settings()
    access_key_id = (settings.bailian_access_key_id or "").strip()
    access_key_secret = (settings.bailian_access_key_secret or "").strip()
    workspace_id = (settings.bailian_workspace_id or "").strip()
    index_id = (settings.bailian_index_id or "").strip()

    if not (access_key_id and access_key_secret and workspace_id and index_id):
        logger.info("云知识库未配置（缺 AK/SK/WorkspaceId/IndexId），跳过云端检索")
        return _empty(query)

    try:
        from alibabacloud_bailian20231229 import models as bailian_models
        from alibabacloud_bailian20231229.client import Client as BailianClient
        from alibabacloud_tea_openapi import models as open_api_models
    except ImportError as exc:  # SDK 未安装时优雅降级
        logger.warning("缺少百炼 SDK（alibabacloud-bailian20231229），跳过云知识库：%s", exc)
        return _empty(query)

    try:
        client = BailianClient(
            open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                endpoint=settings.bailian_endpoint,
                read_timeout=int(settings.bailian_timeout * 1000),
                connect_timeout=int(settings.bailian_timeout * 1000),
            )
        )
        # 只传必填项；EnableReranking 服务端默认 true、RerankTopN 默认 5，
        # 与本系统 top_k=5 一致，无需显式覆盖（少传少踩 SDK 版本差异）。
        request = bailian_models.RetrieveRequest(index_id=index_id, query=query)
        response = client.retrieve(workspace_id, request)
    except Exception as exc:  # 网络/鉴权/参数等任何异常都不向上抛
        logger.warning("云知识库检索失败：%s: %s", exc.__class__.__name__, exc)
        return _empty(query)

    body = getattr(response, "body", None)
    data = getattr(body, "data", None)
    nodes = getattr(data, "nodes", None) or []

    contexts: List[RetrievedContext] = []
    for idx, node in enumerate(nodes[:top_k]):
        text = _node_attr(node, "text", "Text", default="")
        if not str(text).strip():
            continue
        metadata = _node_attr(node, "metadata", "Metadata", default={}) or {}
        filename = (
            metadata.get("doc_name")
            or metadata.get("title")
            or metadata.get("file_path")
            or "云知识库"
        )
        contexts.append(
            RetrievedContext(
                chunk_id=str(metadata.get("doc_id") or f"cloud:{idx}"),
                text=str(text),
                metadata={
                    "filename": filename,
                    "title": metadata.get("title"),
                    "doc_id": metadata.get("doc_id"),
                    "knowledge_source": "cloud",
                },
                source="cloud",
                score=float(_node_attr(node, "score", "Score", default=0.0) or 0.0),
            )
        )

    return RetrieveResult(
        query=query,
        analysis=_CLOUD_ANALYSIS,
        contexts=contexts,
        context_block=_format_context_block(contexts),
    )
