import os
import asyncio
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains.llm import LLMChain
from logger import logger

# --- 1. 加载环境变量 ---
load_dotenv()
dashscope_api_key = os.getenv("HUNYUAN_API_KEY")

if not dashscope_api_key:
    logger.error("错误：请确保在 .env 文件中设置了 DASHSCOPE_API_KEY")
    exit()


# --- 2. 定义核心功能函数 ---
def load_product_info(filepath=r"C:\Users\97909\Desktop\EmailAgent\config\product_info.txt"):
    """从文本文件中加载产品信息"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"错误：找不到产品信息文件 {filepath}。请创建该文件并填入产品介绍。")
        return None


def load_my_info(filepath=r"C:\Users\97909\Desktop\EmailAgent\config\my_info.txt"):
    """从文本文件中加载身份信息"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"错误：找不到身份信息文件 {filepath}。请创建该文件并填入身份信息。")
        return None


def create_email_generation_chain():
    """创建 LangChain 来生成邮件 (使用通义千问模型)"""
    logger.info("正在创建 LangChain 邮件生成链...")
    llm = ChatOpenAI(
        model="hunyuan-lite",
        temperature=0.2,
        api_key=dashscope_api_key,
        base_url="https://api.hunyuan.cloud.tencent.com/v1"
    )

    prompt_template = """
        Your task is to write a concise, professional cold email in English for a potential client. The email must be entirely in English, including all professional terms and product names.
        Input:
        Product Information: {product_info}        
        My Information: {my_info}        
        
        Client Information:        
        Company Name: {company_name}        
        Company Profile: {company_info}        
        Contact Name: {contact_name}       
        Contact Title: {contact_title}       
        
        Writing Guidelines:
        Salutation: Address the contact by name and title.       
        Opening: Show you've done research by referencing their company profile.      
        Value Proposition: Clearly link your product to a specific client problem or a valuable benefit (e.g., increased efficiency, cost savings).    
        Conciseness: Keep the email around 155-200 words.   
        Call to Action: Provide a low-threshold CTA, for example:   
        Please visit our website for the full product list.       
        Are there any products your company needs? If so, please provide the name and specifications.      
        What are your packaging and application requirements?       
        What is the estimated order quantity?       
        Signature: Sign off professionally.     
        
        Output Format:
        Subject: [Your email subject]       
        [Your email body]
        
        Note: Strictly use the provided client data. Do not use placeholders like nan or [Optional Content].
    """

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["product_info", "company_name", "company_info", "contact_name", "contact_title", "my_info"]
    )

    return LLMChain(llm=llm, prompt=prompt)


async def process_contacts(filepath="", chain=None, max_concurrency=5):
    """异步处理 Excel 文件并为每个联系人生成邮件，然后将结果写入新的 Excel 文件"""
    if not chain:
        logger.error("错误：Chain 未初始化。")
        return

    try:
        df = pd.read_excel(filepath)
        logger.info(f"成功读取 {len(df)} 条联系人信息。")
    except FileNotFoundError:
        logger.error(f"错误：找不到联系人文件 {filepath}。")
        return
    except Exception as e:
        logger.error(f"读取 Excel 文件时出错: {e}")
        return

    df_filtered = df.dropna(subset=['邮箱']).copy()
    df_filtered['邮箱'] = df_filtered['邮箱'].astype(str).str.strip()
    df_filtered = df_filtered[df_filtered['邮箱'] != '']

    removed_count = len(df) - len(df_filtered)
    if removed_count > 0:
        logger.warning(f"已移除 {removed_count} 条邮箱为空或无效的数据。")

    if df_filtered.empty:
        logger.warning("处理后没有有效的联系人信息，程序终止。")
        return

    product_info = load_product_info()
    if not product_info:
        return
    my_info = load_my_info()
    if not my_info:
        return

    generated_emails = []
    semaphore = asyncio.Semaphore(max_concurrency)  # 限制并发数量

    async def process_single_contact(index, row):
        async with semaphore:  # 控制最大并发
            company_name = row.get('公司名称', 'N/A')
            company_info = row.get('简介', 'N/A')
            contact_name = row.get('姓名', 'N/A')
            contact_email = row.get('邮箱', 'N/A')
            contact_title = row.get('职务', 'N/A')

            logger.info(f"===== 正在为 {company_name} 的 {contact_name} ({contact_title}) 生成开发信... =====")

            input_data = {
                'product_info': product_info,
                'my_info': my_info,
                'company_name': company_name,
                'company_info': company_info,
                'contact_name': contact_name,
                'contact_title': contact_title
            }

            try:
                response = await chain.ainvoke(input_data)  # 🚀 异步调用
                full_response = response['text']

                parts = full_response.split('\n\n', 1)
                generated_subject = "未生成主题"
                generated_content = full_response
                print(generated_content)
                if len(parts) >= 2:
                    subject_line = parts[0].strip()
                    generated_content = parts[1].strip()

                    if subject_line.startswith("主题:"):
                        generated_subject = subject_line[3:].strip()
                    elif subject_line.startswith("Subject:"):
                        generated_subject = subject_line[8:].strip()

                generated_subject = generated_subject.replace('**', '').strip()
                generated_content = generated_content.replace('**', '').strip()
                logger.success(f"--- 生成的邮件 (收件人: {contact_email}) ---")
                logger.debug(f"主题: {generated_subject}")
                logger.debug(f"内容:\n{generated_content}")

                return {
                    'id': index + 1,
                    '公司名称': company_name,
                    '姓名': contact_name,
                    '职务': contact_title,
                    '邮箱': contact_email,
                    '开发信主题': generated_subject,
                    '开发信内容': generated_content
                }

            except Exception as e:
                logger.error(f"为 {company_name} 生成邮件时出错: {e}")
                return None

    # 🔹 并发执行所有任务
    tasks = [process_single_contact(idx, row) for idx, row in df_filtered.iterrows()]
    results = await asyncio.gather(*tasks)

    for res in results:
        if res:
            generated_emails.append(res)

    if generated_emails:
        output_df = pd.DataFrame(generated_emails)
        output_filename = "../email_output/generated_emails_0827.xlsx"
        try:
            output_df.to_excel(output_filename, index=False)
            logger.success(f"\n--- 所有邮件已生成，并成功保存到 {output_filename} ---")
        except Exception as e:
            logger.error(f"\n错误：保存 Excel 文件时出错: {e}")


# # --- 3. 主程序入口 --- 调试或分步执行用
# if __name__ == "__main__":
#     print("--- AI 开发信生成 Agent 启动 (模型: 腾讯混元) ---")

#     # 创建邮件生成链
#     email_chain = create_email_generation_chain()

#     asyncio.run(process_contacts(
#         filepath=r"C:\Users\97909\Desktop\EmailAgent\data\data_0820.xlsx",
#         chain=email_chain,
#         max_concurrency=5
#     ))

#     print("\n--- 所有联系人处理完毕 ---")
