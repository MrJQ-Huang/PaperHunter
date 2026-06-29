from crewai import Task

from ..agents.search_agent import create_search_agent
from ..agents.filter_agent import create_filter_agent
from ..agents.download_agent import create_download_agent
from ..agents.chat_agent import create_chat_agent


def create_search_task(query: str, sources: list[str], agent) -> Task:
    return Task(
        description=f"""搜索主题: "{query}"
数据源: {', '.join(sources)}

请执行以下步骤:
1. 从指定的多个学术数据源并行搜索论文
2. 汇总所有搜索结果
3. 对结果进行去重（基于 DOI 和标题）
4. 返回去重后的论文列表，包含: 标题、作者、摘要、DOI、来源、发表日期、引用数、是否OA

搜索关键词: {query}
请确保搜索尽可能全面，不要遗漏重要论文。""",
        expected_output="去重后的论文列表，以 JSON 格式返回，包含每篇论文的完整元数据",
        agent=agent,
    )


def create_filter_task(query: str, filters: dict, agent) -> Task:
    filter_desc = ""
    if filters.get("year_min"):
        filter_desc += f"\n- 发表年份 >= {filters['year_min']}"
    if filters.get("citations_min"):
        filter_desc += f"\n- 引用数 >= {filters['citations_min']}"
    if filters.get("only_oa"):
        filter_desc += "\n- 仅限开放获取论文"
    if filters.get("exclude_reviews"):
        filter_desc += "\n- 排除综述类论文"

    return Task(
        description=f"""对搜索到的论文进行智能筛选和排序。

搜索主题: "{query}"
筛选条件:{filter_desc if filter_desc else " 无特殊条件"}

评分维度:
- 语义相关性 (40%): 摘要与查询主题的匹配度 0-10
- 引用数 (20%): log10(citations + 1) / log10(max_citations + 1) * 10
- 时效性 (15%): 近1年=10, 近3年=8, 近5年=6, 更早=4
- 可获取性 (15%): OA=10, 有OA链接=7, 需付费=3
- 来源可信度 (10%): 顶刊/顶会=10, 一般期刊=7, 预印本=5

请:
1. 按综合评分排序所有论文
2. 给出每篇论文的筛选理由
3. 返回排序后的推荐论文列表""",
        expected_output="排序后的推荐论文列表，附带每篇的综合评分和筛选理由",
        agent=agent,
    )


def create_download_task(agent) -> Task:
    return Task(
        description="""下载筛选后的论文 PDF 文件。

下载策略（按优先级）:
1. 优先从开放获取(OA)源直接下载
2. 通过 Unpaywall API 查找合法 OA 版本
3. 从 arXiv/PubMed Central 等开放仓库下载

文件命名规则: {任务名称}/{作者}_{年份}_{标题}_{论文ID前8位}.pdf

请:
1. 逐篇尝试下载 PDF
2. 验证下载的文件是否为有效 PDF
3. 按前端任务名称分类存储
4. 记录下载成功/失败及失败原因
5. 返回下载结果报告""",
        expected_output="下载结果报告，包含成功/失败数量和每篇论文的下载状态",
        agent=agent,
    )


def create_chat_summary_task(agent) -> Task:
    return Task(
        description="""汇总整个论文搜索任务的结果，生成用户友好的报告。

报告内容:
1. 搜索概览：搜索了哪些数据源，找到多少论文
2. 筛选结果：推荐了多少篇论文，推荐理由
3. 下载情况：成功下载多少篇，失败多少篇及原因
4. 推荐的下一步操作

请用简洁清晰的语言撰写报告，突出最重要的信息。""",
        expected_output="用户友好的任务完成报告，包含搜索、筛选、下载的完整摘要",
        agent=agent,
    )
