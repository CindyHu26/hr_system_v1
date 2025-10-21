# services/performance_bonus_scraper.py
import os
import re
import time # 保留 time 給可能的延遲 (雖然在此版本未使用)
import pandas as pd
import requests # <--- 引入 requests
from requests.auth import HTTPBasicAuth # <--- 用於認證
import streamlit as st # <-- 保留用於提示

REQUEST_TIMEOUT = 180 # 維持較長的超時時間

def fetch_performance_count(username, password, start_date_str, end_date_str):
    """
    【Requests 版本 - 根據 HTML 更新 Payload】
    使用 requests 函式庫抓取績效目標人數。
    假設：
    1. 網站使用 HTTP Basic Authentication。
    2. 點擊 "轉出Excel" 按鈕是提交一個 POST 請求。
    3. 伺服器的回應是包含 "合計: X人" 和 "遞補: Y人" 的純文字或可解析的內容。
    4. 不需要執行 JavaScript。
    """
    # 從 .env 讀取績效獎金系統的 URL
    PERFORMANCE_BONUS_URL = os.getenv("PERFORMANCE_BONUS_URL")
    if not PERFORMANCE_BONUS_URL:
        raise ValueError("錯誤：請在 .env 檔案中設定 PERFORMANCE_BONUS_URL")

    # --- 根據 HTML 更新 URL ---
    form_url = PERFORMANCE_BONUS_URL # 假設 .env 中的 URL 就是表單頁面
    # 從 form action 確認提交 URL
    submit_url = "http://192.168.1.168/labor/labor_817_p02.php"
    # --- URL 確認結束 ---

    # 使用 requests.Session 處理認證和 cookies
    with requests.Session() as session:
        session.auth = HTTPBasicAuth(username, password)

        # --- 根據 HTML 更新 Payload ---
        payload = {
            'CU00_BNO': '',        # 起始雇主編號 (清空)
            'CU00_ENO': '',        # 截止雇主編號 (清空)
            'CU00_SDATE': '1',     # 期間別: 1.入境日 (匹配 Selenium)
            'CU00_BDATE': start_date_str, # 期間起始日
            'CU00_EDATE': end_date_str,   # 期間截止日
            'CU00_BDATE1': '',     # 離境期間起始日
            'CU00_EDATE1': '',     # 離境期間截止日
            'CU00_BDATE2': '',     # 聘可期間起始日
            'CU00_EDATE2': '',     # 聘可期間截止日
            'CU00_BASE': '',       # 基準日期
            'CU00_BASE_I': 'N',    # 廢止聘可移工算任用中?
            'CU00_sel8': 'A',      # 工作地址: 全選
            'CU00_LA04': '0',      # 移工國籍: 全部
            'CU00_LA19': '0',      # 工種類別: 全部
            'CU00_LA198': '1',     # 移工類別: 一般移工 (匹配 Selenium)
            'CU00_WORK': '0',      # 申請類別: 全部
            'CU00_PNO': '0',       # 接管身份代號: 所有
            'CU00_ORG1': '1',      # 任用來源: 入境任用 (匹配 Selenium)
            'CU00_LNO': '1',       # 離管身份代號: 聘僱中 (匹配 Selenium)
            'CU00_LA28': '0',      # 離境原因: 全部
            'CU00_SALERS': '0',    # 業務人員: 全部 (匹配 Selenium)
            'CU00_MEMBER': '0',    # 負責行政人員: 全部
            'CU00_SERVS': 'A',     # 負責客服人員: 全部
            'CU00_ACCS': '0',      # 負責會計人員: 全部 (HTML 未顯示，但通常會有)
            'CU00_TRANSF': '0',    # 負責雙語人員: 全部
            'CU00_RET': '0',       # 回鍋工: 全部
            'CU00_ORD': '1',       # 資料排序: 入境日
            'CU00_drt': '5',       # 辦件別 (匹配 Selenium)
            'CU00_SEL32': '4',     # 期滿到期: 無關
            'CU00_SEL33': '9',     # 報表格式 (匹配 Selenium)
            'CU00_SEL35': '1',     # 表單日期格式: 內定
            'CU00_LA37': '',       # 國外仲介編號
            'CU00_LA37_1': '',     # 國外仲介名稱
            'CU00_LA120': '全部',  # 國內仲介: 全部
            'LFK02_mm': '',        # Hidden input
            # --- 按鈕：根據 HTML 更新 name ---
            'key': '轉出Excel'     # 按鈕 name='key', value='轉出Excel'
        }
        # --- Payload 確認結束 ---

        try:
            st.info(f"正在發送績效獎金請求至 {submit_url}...") # 進度提示
            # 確認方法為 POST
            response = session.post(submit_url, data=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status() # 檢查 HTTP 錯誤

            # --- 嘗試解碼回應內容 (同 bonus_scraper) ---
            html_content = ""
            try:
                html_content = response.content.decode('big5')
                st.info("收到伺服器回應 (嘗試 Big5 解碼)，正在解析...")
            except UnicodeDecodeError:
                try:
                    html_content = response.content.decode('cp950')
                    st.info("收到伺服器回應 (cp950 解碼)，正在解析...")
                except UnicodeDecodeError:
                    st.warning(f"警告：回應 Big5/cp950 解碼失敗，嘗試使用自動偵測的編碼 ({response.apparent_encoding})。")
                    response.encoding = response.apparent_encoding
                    html_content = response.text
            # --- 解碼結束 ---

            # --- 除錯：顯示部分解碼後的內容 ---
            st.text("解碼後的回應內容 (前 1000 字元):")
            st.code(html_content[:1000])
            # --- 除錯結束 ---

            # --- 使用正規表示式解析回應內容 ---
            pattern = r"合計:\s*(\d+)人.*?遞補:\s*(\d+)人"
            match = re.search(pattern, html_content) # 在解碼後的內容中搜索

            if not match:
                preview = html_content[:500].replace('<', '&lt;').replace('>', '&gt;')
                st.error(f"錯誤：在伺服器回應中找不到 '合計: X人' 和 '遞補: Y人' 的格式文字。請檢查上面的回應內容預覽。\n```\n{preview}\n```")
                raise ValueError("在伺服器回應內容中找不到 '合計: X人' 和 '遞補: Y人' 的格式文字。請檢查網站回應或確認是否需要 Selenium。")

            total_count = int(match.group(1))
            replacement_count = int(match.group(2))
            st.success(f"解析成功：合計={total_count}, 遞補={replacement_count}")

            final_count = total_count - replacement_count
            return final_count

        # --- 錯誤處理---
        except requests.exceptions.Timeout:
             st.error(f"請求超時 ({REQUEST_TIMEOUT}秒)，無法從伺服器獲取回應。")
             raise TimeoutError(f"請求超時 ({REQUEST_TIMEOUT}秒)，無法從伺服器獲取回應。")
        except requests.exceptions.RequestException as e:
            st.error(f"網路連線或請求失敗: {e}")
            raise ConnectionError(f"網路連線或請求失敗: {e}")
        except ValueError as e:
            raise e
        except Exception as e:
            st.error(f"處理績效獎金請求時發生未預期錯誤: {e}")
            raise RuntimeError(f"處理績效獎金請求時發生未預期錯誤: {e}")
        # --- 錯誤處理結束 ---