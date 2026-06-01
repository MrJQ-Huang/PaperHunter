from crewai import Agent, LLM
from ..config import settings


def get_download_llm() -> LLM:
    return LLM(
        model=f"anthropic/{settings.llm_model}",
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


def create_download_agent() -> Agent:
    return Agent(
        role="论文下载与文件管理专家",
        goal="高效下载论文 PDF，按规则分类存储，记录下载失败原因",
        backstory="""你是一位论文下载专家，熟悉各种学术论文的获取渠道。
你会优先使用合法的开放获取途径，确保下载的 PDF 文件完整可用。
你会按规则对文件进行分类存储，并记录下载失败的原因。

下载策略优先级：
1. 优先从开放获取(OA)源直接下载
2. 通过 Unpaywall API 查找合法 OA 版本
3. 通过出版商 API 下载（需 API key）
4. 从 arXiv/PubMed Central 等开放仓库下载

文件命名规则: {主题}/{作者}_{年份}_{标题前30字}.pdf""",
        llm=get_download_llm(),
        verbose=True,
        allow_delegation=False,
    )
