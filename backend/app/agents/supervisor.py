"""WanderBot 多智能体 supervisor 主图。

布局:
    START → supervisor (react agent: handoff tools + 通用工具)
              ├→ flight_agent ─┐
              ├→ hotel_agent ─┤
              ├→ car_agent ─┤→ 跑完回 supervisor
              └→ trip_agent ─┘
            supervisor 不再调工具时 END

特性:
- 单例 MemorySaver:跨 SSE 请求保留对话(thread_id = conversation_id),
  顺便解决我们之前讨论过的"跨流失忆"问题。
- 通用工具直接挂在 supervisor 上:天气、路线、行程整合、行程导出、可选的
  Firecrawl 搜索 / 抓取。把数据库类工作交给 specialist,把 LLM-only 类
  工作留给 supervisor 自己。
- interrupt():由 sensitive 工具内部触发,LangGraph 自动 checkpoint;
  resume 时用 ``Command(resume=...)`` 重入。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool as langchain_tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import create_react_agent

from app.agents.handoffs import create_handoff_tool
from app.agents.specialists import SPECIALIST_DEFINITIONS, build_specialists


# 进程内单例 checkpointer。多个 LLM 配置共享同一实例,
# thread_id (conversation_id) 隔离不同会话。
_CHECKPOINTER = MemorySaver()


def get_checkpointer() -> MemorySaver:
    return _CHECKPOINTER


def build_supervisor_graph(
    model,
    *,
    generic_tools: Optional[List[Any]] = None,
    supervisor_prompt: str,
):
    """编译并返回一张 supervisor 图。

    每次 chat 请求都会调用一次(LLM 配置可能变),共享同一个 _CHECKPOINTER。
    """
    specialists = build_specialists(model)

    handoff_tools = [
        create_handoff_tool(d["name"], d["handoff_description"])
        for d in SPECIALIST_DEFINITIONS
    ]

    supervisor_agent = create_react_agent(
        model=model,
        tools=handoff_tools + list(generic_tools or []),
        prompt=supervisor_prompt,
        name="supervisor",
    )

    builder = StateGraph(MessagesState)
    builder.add_node("supervisor", supervisor_agent)
    for name, agent in specialists.items():
        builder.add_node(name, agent)
        builder.add_edge(name, "supervisor")
    builder.add_edge(START, "supervisor")

    return builder.compile(checkpointer=_CHECKPOINTER)


def supervisor_prompt_from_system(base_prompt: str) -> str:
    """在用户的 system prompt 上追加 supervisor 模式的协作守则 + 末尾风格重申。"""
    return (
        base_prompt
        + "\n\n## 多智能体协作模式\n"
        "你现在是 WanderBot 主助理 (supervisor),管理 4 个专业子 agent:\n"
        "- flight_agent:航班查询 / 改签 / 退票\n"
        "- hotel_agent:酒店库存查询 / 预订 / 改期 / 取消\n"
        "- car_agent:租车查询 / 预订 / 改期 / 取消\n"
        "- trip_agent:景点门票 / 旅游产品 库存预订\n\n"
        "**何时 handoff**:用户的请求需要查询或操作某类业务数据库时,用 transfer_to_<agent_name> 工具委派。\n"
        "**何时直接回答**:通用旅游问题(天气、路线、行程整合、行程导出、城市推荐)由你自己用挂在你身上的通用工具完成。\n"
        "**handoff 的 task_description** 要写完整上下文,因为子 agent 看到的是裁切后的视野。\n"
        "**敏感操作(预订 / 改签 / 取消)** 由工具内部触发用户确认,你和子 agent 都不需要在文字里再确认一次,直接调用工具即可。\n"
        "\n## 最终格式重申(覆盖前面任何风格冲突)\n"
        "严格遵守上文「输出风格守则」:\n"
        "- 任何候选 / 列表 / 对比信息 → 必须用 Markdown 表格\n"
        "- 正文里不出现 emoji,也不要用 emoji 替代项目符号\n"
        "- 不要在表格之后用散文再复述一遍同样的内容\n"
    )
