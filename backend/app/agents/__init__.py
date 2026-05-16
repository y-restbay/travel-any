"""多智能体 supervisor:WanderBot 的多智能体协作实现。

模块布局:
- handoffs.py:create_handoff_tool 工厂
- specialists.py:4 个子 agent(flight / hotel / car / trip)的工具集与 prompt
- supervisor.py:装配 + checkpointer + 暴露 build_supervisor_graph
"""
