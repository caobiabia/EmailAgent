import os
import pandas as pd
from dotenv import load_dotenv
import yagmail
import time
from logger import logger


def send_generated_emails(filepath=""):
    """
    从指定的 Excel 文件中读取邮件信息，并使用 yagmail 发送。

    :param filepath: 包含待发送邮件信息的 Excel 文件路径。
    """
    # --- 1. 加载环境变量 ---
    load_dotenv()
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")

    if not sender_email or not sender_password:
        logger.error("错误：请确保在 .env 文件中设置了 SENDER_EMAIL 和 SENDER_PASSWORD")
        return

    if smtp_port:
        try:
            smtp_port = int(smtp_port)
        except ValueError:
            logger.error("错误：.env 文件中的 SMTP_PORT 值无效，应为数字。")
            return

    # --- 2. 读取 Excel 文件 ---
    try:
        df = pd.read_excel(filepath)
        logger.info(f"成功读取 {len(df)} 条待发送邮件信息。")
    except FileNotFoundError:
        logger.error(f"错误：找不到邮件文件 {filepath}。请先运行主脚本生成该文件。")
        return
    except Exception as e:
        logger.error(f"读取 Excel 文件时出错: {e}")
        return

    # --- 3. 初始化 yagmail 客户端 ---
    try:
        if smtp_server and smtp_port:
            yag = yagmail.SMTP(user=sender_email, password=sender_password, host=smtp_server, port=smtp_port)
        else:
            yag = yagmail.SMTP(user=sender_email, password=sender_password)
        logger.info("成功连接到邮件服务器。")
    except Exception as e:
        logger.error(f"错误：连接邮件服务器失败。请检查您的邮箱地址、密码、网络连接或SMTP配置。详细错误: {e}")
        return

    # --- 4. 遍历并发送邮件 ---
    success_count = 0
    fail_count = 0
    for index, row in df.iterrows():
        contact_email = row.get('邮箱', 'N/A')
        generated_subject = row.get('开发信主题', 'N/A')
        generated_content = row.get('开发信内容', 'N/A')

        if pd.isna(contact_email) or contact_email == 'N/A':
            logger.warning(f"跳过第 {int(index) + 1} 行：邮箱地址无效。")
            continue

        logger.info(f"===== 正在发送邮件至 {contact_email}... =====")
        logger.info(f"主题: {generated_subject}")

        try:
            yag.send(
                to=contact_email,
                subject=generated_subject,
                contents=generated_content
            )
            logger.success(f"--- 邮件发送成功！ ---")
            success_count += 1
        except Exception as e:
            logger.error(f"--- 邮件发送失败: {e} ---")
            fail_count += 1

        time.sleep(5)

    logger.info("--- 所有邮件处理完毕 ---")
    logger.info(f"成功发送: {success_count} 封")
    logger.info(f"发送失败: {fail_count} 封")


# --- 主程序入口 ---
if __name__ == "__main__":
    send_generated_emails(filepath="../email_output/generated_emails_0820.xlsx")
