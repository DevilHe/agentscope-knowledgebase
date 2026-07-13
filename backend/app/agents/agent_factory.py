from agentscope.agent import Agent
from agentscope.message import Msg
from agentscope.state import AgentState
from agentscope.tool import Toolkit

from app.agents.permissions import build_permission_context
from app.core.prompt_registry import resolve_system_prompt
from app.db.models import User
from app.services.llm import get_chat_model, resolve_model_name
from app.tools.knowledge_search_tool import create_knowledge_search_tool
from app.tools.search_tool import WebSearchTool
from app.tools.weather_tool import WeatherTool


def create_chat_agent(
    history: list[Msg] | None,
    user_role: str,
    top_k: int,
    sources_out: list[dict],
    user: User | None = None,
    *,
    model_name: str | None = None,
) -> tuple[Agent, str]:
    """创建统一 Agent；返回 (agent, prompt_version)。"""
    system_prompt, prompt_version = resolve_system_prompt(user.id if user else None)
    state = AgentState(permission_context=build_permission_context(user_role))
    if history:
        state.context = list(history)

    resolved_model = model_name or resolve_model_name("chat")
    agent = Agent(
        name="kb-assistant",
        system_prompt=system_prompt,
        model=get_chat_model(stream=True, model_name=resolved_model),
        toolkit=Toolkit(
            tools=[
                create_knowledge_search_tool(top_k, sources_out, user=user),
                WebSearchTool(),
                WeatherTool(),
            ]
        ),
        state=state,
    )
    return agent, prompt_version
