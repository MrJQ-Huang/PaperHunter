from crewai import Agent, LLM
from ..config import settings
from ..utils.llm_client import llm_model_for_crewai


def get_search_llm() -> LLM:
    return LLM(
        model=llm_model_for_crewai(),
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


def create_search_agent() -> Agent:
    return Agent(
        role="学术搜索专家",
        goal="从多个学术数据源全面搜索论文，确保覆盖广泛，不遗漏重要论文",
        backstory="""你是一位经验丰富的学术研究助理，擅长从多个学术数据库中高效检索论文。
你了解各数据源的特点和覆盖范围，能够制定最优的搜索策略。
你会并行查询多个源，去重合并结果，并确保不遗漏重要论文。
你能根据搜索结果的质量和数量，动态调整搜索策略。""",
        llm=get_search_llm(),
        verbose=True,
        allow_delegation=False,
    )
