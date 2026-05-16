"""手写 handoff 工具:LLM 调用后用 Command(goto=agent_name) 把控制权交给某个子 agent。

langgraph-supervisor 需要 Python 3.10+,本项目环境是 3.9,所以自己写了精简版本,
仅依赖 langgraph 主包。
"""
from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


def create_handoff_tool(agent_name: str, description: str):
    """生成 ``transfer_to_<agent_name>`` 工具。

    被 supervisor 调用时把对话状态(messages)透传给目标 agent,
    并跳到父图(StateGraph)的对应节点。
    """
    tool_name = f"transfer_to_{agent_name}"

    @tool(tool_name, description=description)
    def handoff(
        task_description: Annotated[
            str,
            "详细描述你希望该专家 agent 完成的任务,包括所有相关上下文。",
        ],
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        tool_message = ToolMessage(
            content=f"已转交至 {agent_name},任务说明:{task_description}",
            name=tool_name,
            tool_call_id=tool_call_id,
        )
        return Command(
            goto=agent_name,
            graph=Command.PARENT,
            update={
                "messages": state.get("messages", []) + [tool_message],
            },
        )

    return handoff
