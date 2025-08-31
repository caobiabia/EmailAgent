import asyncio
import os
import sys
from logger import logger

from src.generate_email import create_email_generation_chain, process_contacts
from src.send_email import send_generated_emails


def main():
    """
    主程序入口，负责协调邮件生成的流程。
    """
    logger.info("--- 邮件代理程序启动 ---")
    logger.info("正在初始化...")

    # --- 1. 定义文件路径 ---
    input_file_path = r"C:\Users\97909\Desktop\EmailAgent\data\data_0827.xlsx"
    output_file_path = r"C:\Users\97909\Desktop\EmailAgent\email_output\generated_emails_0827.xlsx"

    if not os.path.exists(input_file_path):
        logger.error(f"找不到联系人数据文件: {os.path.abspath(input_file_path)}")
        sys.exit(1)

    # --- 2. 生成邮件 ---
    logger.info("--- 任务一：正在生成开发信... ---")
    try:
        email_chain = create_email_generation_chain()
        asyncio.run(process_contacts(
            filepath=r"C:\Users\97909\Desktop\EmailAgent\data\data_0822.xlsx",
            chain=email_chain,
            max_concurrency=5
        ))
        logger.success("--- 开发信已全部生成并保存。---")
    except Exception as e:
        logger.error(f"邮件生成过程中发生错误: {e}")
        sys.exit(1)

    # --- 增加用户确认步骤 ---
    logger.info(f"\n--- 邮件生成任务完成。请检查 {output_file_path} 文件。 ---")

    user_input = input("是否继续执行发送邮件操作？(输入 'y' 继续, 'n' 取消): ").lower()

    if user_input == 'y':
        # --- 3. 发送邮件 ---
        logger.info("--- 任务二：正在发送邮件... ---")
        try:
            send_generated_emails(filepath=output_file_path)
            logger.success("--- 邮件已全部成功发送。---")
        except Exception as e:
            logger.error(f"邮件发送过程中发生错误: {e}")
            sys.exit(1)
    else:
        logger.info("用户选择取消，程序结束。")
        sys.exit(0)


if __name__ == "__main__":
    main()
