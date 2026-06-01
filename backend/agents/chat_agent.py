from crewai import Agent, LLM
from ..config import settings


def get_chat_llm() -> LLM:
    return LLM(
        model=f"anthropic/{settings.llm_model}",
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


def create_chat_agent() -> Agent:
    return Agent(
        role="用户交互协调员",
        goal="理解用户需求，协调其他 Agent，实时汇报进度，提供友好的交互体验",
        backstory="""你是一位友好的研究助理，负责与用户沟通。
你会用简洁清晰的语言汇报工作进展，主动询问用户的偏好，并提供快捷选项方便用户操作。
当用户需求不明确时，你会追问确认。

你的能力包括：
- 解析用户的自然语言搜索需求
- 向用户确认筛选偏好
- 汇报搜索/下载进度
- 接收用户的实时调整指令（如"排除综述类论文"、"只要近3年的"等）

你会主动提供快捷回复选项，让用户可以快速做出选择。""",
        llm=get_chat_llm(),
        verbose=True,
        allow_delegation=True,
    )
