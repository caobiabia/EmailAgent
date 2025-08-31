import os
import asyncio
import json
import re
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from dotenv import load_dotenv
from logger import logger

# --- 1. 加载环境变量和初始化LLM ---
load_dotenv()
ali_api_key = os.getenv("DASHSCOPE_API_KEY")

if not ali_api_key:
    logger.error("错误：请确保在 .env 文件中设置了 DASHSCOPE_API_KEY")
    exit()

llm = ChatOpenAI(
    model="qwen-turbo",
    temperature=0.2,
    api_key=ali_api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# --- 2. 定义LLM分析用的Prompt ---

# 唯一 Prompt: 负责所有阶段的分析和决策
iterative_analysis_prompt_template = """
        你是一位专业的市场分析师和智能网页爬虫。我为你提供了公司网站已爬取的内容。
        
        你的任务是：
        1.  分析所提供的内容，对公司的核心业务、产品、服务和价值主张形成全面的理解。
        2.  基于分析，判断信息是否足以编写一封高度个性化的开发信（cold email）。
        3.  如果需要更多信息，请建议下一个最相关的URL子路径。选择最有可能提供详细产品/服务信息的路径（例如，'products', 'solutions', 'services'）。
        4.  如果信息已足够，请回答 "DONE"，并提供一个最终详细的总结。
        
        请以结构化的 JSON 格式输出你的响应。
        
        "继续爬取"的 JSON 输出示例:
        {{
            "status": "CONTINUE",
            "summary_so_far": "该公司似乎是一家 B2B 软件供应商，但具体产品细节尚不清楚。主页提到了 'AI 赋能的解决方案'。",
            "next_url_path": "/solutions"
        }}
        
        "完成爬取"的 JSON 输出示例:
        {{
            "status": "DONE",
            "final_analysis": {{
                "company_summary": "对公司业务、产品和服务的详细总结。",
                "target_market": "识别出的目标客户群体（例如：'零售业的中小型企业'）。",
                "potential_pain_points": ["列出公司产品/服务为其客户解决的问题。", "例如：'低效的库存管理'"]
            }}
        }}
        
        ---
        已爬取的内容:
        {crawled_content}
        """

analysis_prompt = PromptTemplate(
    template=iterative_analysis_prompt_template,
    input_variables=["crawled_content"]
)
analysis_chain = LLMChain(llm=llm, prompt=analysis_prompt)


def extract_json_from_response(response_text: str):
    """
    尝试从可能包含额外文本的字符串中提取 JSON 对象。
    """
    match = re.search(r'\{.*}', response_text, re.DOTALL)
    if match:
        json_string = match.group(0)
        try:
            return json.loads(json_string)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return None
    logger.warning("在LLM响应中未找到有效的JSON对象。")
    return None


async def ai_company_profiler_iterative(company_url: str, max_crawls=5):
    """
    使用多轮 AI-driven 爬取和分析，直到LLM认为信息已足够。
    """
    logger.info(f"===== 正在为公司 {company_url} 进行AI背调 (多轮模式)... =====")
    url_path = urlparse(company_url).path
    if '.' in os.path.basename(url_path):
        base_path = os.path.dirname(url_path)
    else:
        base_path = url_path
    if not base_path.endswith('/'):
        base_path += '/'

    parsed_url = urlparse(company_url)
    base_url_for_session = f"{parsed_url.scheme}://{parsed_url.netloc}{base_path}"
    logger.info(f"  -> 会话基础URL已设定为: {base_url_for_session}")

    async with AsyncWebCrawler() as crawler:
        full_content = ""
        current_url = company_url
        crawls_count = 0
        visited_paths = {company_url.strip('/')}

        while crawls_count < max_crawls:
            crawls_count += 1
            logger.info(f"  -> 第 {crawls_count} 次尝试: 爬取 {current_url}")

            try:
                crawl_result = await crawler.arun(url=current_url)
                if crawl_result and crawl_result.markdown:
                    full_content += f"\n\n--- Content from {current_url} ---\n\n{crawl_result.markdown}"
                else:
                    logger.warning(f"  -> 爬取 {current_url} 未返回有效内容。")

            except Exception as e:
                logger.error(f"  -> 错误: 爬取 {current_url} 失败: {e}")
                break

            try:
                logger.info("  -> 正在进行AI分析并决策下一步...")
                analysis_response = await analysis_chain.ainvoke({"crawled_content": full_content})
                analysis_data = extract_json_from_response(analysis_response['text'])

                if analysis_data is None:
                    logger.error("  -> 错误: LLM返回了非JSON格式响应，无法解析。终止循环。")
                    break

                status = analysis_data.get("status")
                logger.info(f"  -> AI Agent 状态: {status}")
                logger.info(f"  -> AI Agent 当前总结: {analysis_data.get('summary_so_far', 'N/A')}")

                if status == "DONE":
                    logger.success("  -> AI Agent认为信息已足够，正在生成最终报告。")
                    return analysis_data.get("final_analysis")

                elif status == "CONTINUE":
                    next_path = analysis_data.get("next_url_path")
                    if next_path:
                        next_url = base_url_for_session + next_path.lstrip('/')
                        current_url = next_url
                        visited_paths.add(current_url.strip('/'))
                        logger.info(f"  -> AI Agent决定继续爬取，下一个目标是: {current_url}")
                    else:
                        logger.warning("  -> AI Agent决定继续，但没有提供下一个路径，终止循环。")
                        break
                else:
                    logger.error(f"  -> AI返回了未知的状态: {status}，终止循环。")
                    break

            except Exception as e:
                logger.error(f"  -> 错误: 分析或决策失败: {e}")
                break

        logger.warning("  -> 循环结束，使用现有内容进行最终分析。")
        final_analysis_prompt_template = """
        你是一位高级市场分析师。基于从公司网站上爬取的所有内容，你的任务是提供一份最终的、全面的分析报告。
        你的目标是收集足够的情报，用于撰写一封有针对性的销售邮件。

        请执行以下分析并以 JSON 格式使用中文输出你的报告：
        1.  **公司总结 (company_summary)**: 简洁地总结公司做什么，其核心产品/服务，以及主要价值主张。
        2.  **核心业务/产品 (core_products_services)**: 详细描述公司的主要业务线或核心产品/服务。
        3.  **目标市场 (target_market)**: 描述公司的理想客户画像或目标行业。
        4.  **潜在痛点 (potential_pain_points)**: 基于其产品/服务，列出其客户可能面临的、而其产品/服务旨在解决的潜在问题或挑战。
        5.  **潜在合作点 (potential_collaboration_points)**: 基于公司的业务和你的洞察，提出几个可能的合作方向或切入点，用于在开发信中提及。

        已爬取的内容:
        {all_content}

        请使用以下 JSON 格式提供你的中文输出：
        {{
            "company_summary": "...",
            "core_products_services": "...",
            "target_market": "...",
            "potential_pain_points": ["...", "..."],
            "potential_collaboration_points": ["...", "..."]
        }}
        """
        final_analysis_prompt = PromptTemplate(
            template=final_analysis_prompt_template,
            input_variables=["all_content"]
        )
        final_analysis_chain = LLMChain(llm=llm, prompt=final_analysis_prompt)

        try:
            final_response = await final_analysis_chain.ainvoke({"all_content": full_content})
            final_analysis_data = extract_json_from_response(final_response['text'])
            return final_analysis_data or {"error": "最终分析失败，无法解析。"}
        except Exception as e:
            logger.error(f"  -> 最终分析环节发生错误: {e}")
            return {"error": f"最终分析时发生异常: {e}"}


def pretty_print_analysis(analysis_data: dict):
    """
    格式化并打印最终的公司分析报告。
    """
    if not analysis_data or "error" in analysis_data:
        logger.error(f"未能生成分析报告: {analysis_data.get('error', '未知错误')}")
        return

    print("\n\n" + "=" * 25 + " AI 公司背调报告 " + "=" * 25)

    print("\n## 🏢 公司总结")
    print(analysis_data.get("company_summary", "无"))

    print("\n## 💡 核心业务/产品")
    print(analysis_data.get("core_products_services", "无"))

    print("\n## 🎯 目标市场")
    print(analysis_data.get("target_market", "无"))

    print("\n## ⚡️ 潜在痛点")
    pain_points = analysis_data.get("potential_pain_points", [])
    if pain_points:
        for point in pain_points:
            print(f"  - {point}")
    else:
        print("无")

    print("\n## 🤝 潜在合作点")
    collaboration_points = analysis_data.get("potential_collaboration_points", [])
    if collaboration_points:
        for point in collaboration_points:
            print(f"  - {point}")
    else:
        print("无")

    print("\n" + "=" * 65 + "\n")


# --- 4. 主程序入口 ---
async def run_profiler(url: str):
    """
    执行分析器并打印结果。
    """
    analysis_result = await ai_company_profiler_iterative(url, max_crawls=3)
    if analysis_result:
        pretty_print_analysis(analysis_result)
    else:
        logger.error("分析过程未返回任何结果。")


if __name__ == "__main__":
    # 想要分析的公司网址
    TARGET_URL = "https://www.aceler.com.cn/"

    # 运行异步主程序
    asyncio.run(run_profiler(TARGET_URL))