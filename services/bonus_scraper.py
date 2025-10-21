# services/bonus_scraper.py
import time
import pandas as pd
import requests # 使用 requests 函式庫
from requests.auth import HTTPBasicAuth # 用於 HTTP 基本認證
from bs4 import BeautifulSoup # 用於解析 HTML
from utils.helpers import get_monthly_dates # 輔助函式，獲取月份起訖日
import os # 用於讀取環境變數
import streamlit as st # 用於顯示進度或錯誤訊息
import json # 用於除錯時印出 payload

REQUEST_TIMEOUT = 60 # 設定請求超時時間 (秒)

def fetch_all_bonus_data(username, password, year, month, employee_names, progress_callback=None):
    """
    【Requests 版本 - 動態建立員工 ID 映射 & 完整 Payload】
    使用 requests 函式庫擷取業務獎金收款資料。
    會先讀取查詢頁面以動態建立員工姓名與ID的映射，然後為每個員工發送 POST 請求。
    假設：
    1. 網站使用 HTTP Basic Authentication。
    2. 表單提交是標準的 POST 請求。
    3. 結果頁面的表格不需要 JavaScript 渲染。
    """
    all_details = [] # 用於儲存所有成功擷取的資料列
    start_date, end_date = get_monthly_dates(year, month) # 獲取查詢月份的起始和結束日期

    # 從 .env 檔案讀取目標系統的 URL
    BONUS_SYSTEM_URL = os.getenv("BONUS_SYSTEM_URL")
    if not BONUS_SYSTEM_URL:
        raise ValueError("錯誤：請在 .env 檔案中設定 BONUS_SYSTEM_URL")

    # 定義 URL
    form_url = BONUS_SYSTEM_URL # 包含查詢表單的頁面 URL (假設與 .env 中設定相同)
    # 表單提交的目標 URL (根據您提供的 HTML action 屬性)
    submit_url = "http://192.168.1.168/labor/labor_123_p02.php"
    # 注意: 請確保執行此程式的環境可以訪問 submit_url

    # 使用 requests.Session 來處理 cookies 和認證
    with requests.Session() as session:
        session.auth = HTTPBasicAuth(username, password) # 設定 HTTP 基本認證

        # --- 步驟 1：動態獲取員工姓名到 ID 的映射 ---
        employee_name_to_id_map = {}
        missing_id_employees = [] # 記錄在下拉選單中找不到的員工姓名
        try:
            st.info("正在讀取查詢頁面以建立員工 ID 映射...")
            # 發送 GET 請求獲取包含表單的頁面
            form_response = session.get(form_url, timeout=REQUEST_TIMEOUT)
            form_response.raise_for_status() # 檢查是否有 HTTP 錯誤 (如 404, 500)

            # 嘗試用 Big5 或 cp950 解碼，如果失敗則使用 requests 的自動偵測
            try:
                form_html = form_response.content.decode('big5')
            except UnicodeDecodeError:
                try:
                    form_html = form_response.content.decode('cp950')
                except UnicodeDecodeError:
                    form_response.encoding = form_response.apparent_encoding # 使用自動偵測的編碼
                    form_html = form_response.text
                    st.warning(f"查詢頁面 Big5/cp950 解碼失敗，嘗試使用自動偵測的編碼 ({form_response.encoding})。")

            # 使用 BeautifulSoup 解析 HTML
            form_soup = BeautifulSoup(form_html, 'lxml')
            # 找到 name 為 "CU00_SALERS" 的 select 元素 (下拉選單)
            sales_select = form_soup.find('select', {'name': 'CU00_SALERS'})

            if not sales_select:
                raise ValueError("錯誤：在查詢頁面 HTML 中找不到 'CU00_SALERS' (業務人員) 下拉選單。")

            # 遍歷下拉選單中的所有 <option>
            for option in sales_select.find_all('option'):
                option_value = option.get('value') # 獲取 <option> 的 value 屬性 (員工 ID)
                option_text = option.text.strip() # 獲取 <option> 顯示的文字 (員工姓名)
                # 如果 value 和 text 都存在，且不是 "全部" (value='0')，則存入字典
                if option_value and option_text and option_value != '0':
                    employee_name_to_id_map[option_text] = option_value
            st.success(f"成功建立員工 ID 映射，共 {len(employee_name_to_id_map)} 位員工。")
            # print(employee_name_to_id_map) # 可取消註解用於除錯

        except requests.exceptions.RequestException as e:
            st.error(f"讀取查詢頁面失敗，無法建立員工映射: {e}")
            raise ConnectionError(f"無法讀取查詢頁面以建立員工映射: {e}") # 拋出錯誤，終止執行
        except ValueError as e: # 捕捉上面 raise 的 ValueError
            st.error(str(e))
            raise e # 重新拋出
        except Exception as e:
            st.error(f"解析查詢頁面時發生未預期錯誤: {e}")
            raise RuntimeError(f"解析查詢頁面時發生未預期錯誤: {e}") # 拋出錯誤
        # --- 步驟 1 結束 ---

        total_employees = len(employee_names)

        # --- 步驟 2：遍歷提供的員工姓名列表，查找 ID 並發送 POST 請求 ---
        for i, name in enumerate(employee_names):
            # 更新進度回饋 (如果提供了 callback 函式)
            if progress_callback:
                progress_callback(f"({i+1}/{total_employees}) 正在查詢 [{name}] 的資料...", (i + 1) / total_employees)

            # 使用動態建立的字典查找員工 ID
            employee_id_value = employee_name_to_id_map.get(name)
            # 如果在字典中找不到該員工姓名
            if not employee_id_value:
                st.warning(f"警告：在剛讀取的下拉選單中找不到員工 [{name}] 的 ID，將跳過此員工。")
                missing_id_employees.append(name) # 記錄下來
                continue # 處理下一個員工

            # --- 步驟 3：組裝 POST 請求的 payload (表單資料) ---
            # 根據 HTML 原始碼分析，包含所有 input 和 select 欄位及其值
            payload = {
                # 主要查詢條件
                'CU00_BDATE1': start_date,   # 己收款起始日
                'CU00_EDATE1': end_date,     # 己收款截止日
                'CU00_LNO': '0',           # 離管身份代號: 所有 (value='0')
                'CU00_SALERS': employee_id_value, # 業務人員: 使用查找到的 ID
                'LAB03SS': '1',          # 費用項目: 外勞服務費 (value='1')
                'CU00_sel2': '2',          # 外勞姓名用: 中文 (value='2')

                # 其他欄位的預設值 (確保與瀏覽器提交一致)
                'CU00_BNO1': '',           # 起始雇主編號
                'CU00_ENO1': '',           # 截止雇主編號
                'CU00_BDATE': '',          # 應收款起始日
                'CU00_EDATE': '',          # 應收款截止日
                'CU00_CU44': '',           # 雇主簡稱條件
                'CU00_TEL': '',            # 電話號碼條件
                'CU00_LA04': '0',          # 外勞國籍: 全部 (value='0')
                'CU00_MEMBER': '0',        # 負責行政人員: 全部 (value='0')
                'CU00_SERVS': '0',         # 雇主客服員: 全部 (value='0')
                'CU00_SERVS1': '0',        # 外勞客服員: 全部 (value='0')
                'CU00_WORK': '0',          # 申請類別: 全部 (value='0')
                'CU00_LA19': '0',          # 工種類別: 全部 (value='0')
                'CU00_ORD': '2',           # 資料排序: 雇主 (value='2', selected)
                'CU00_LA76': '0',          # 收款方式: 全部 (value='0', selected)
                'CU00_BDATE2': '',         # 起始期間..接管日
                'CU00_EDATE2': '',         # 截止期間..接管日
                'CU00_sel21': '0',         # 範圍選擇: 全部 (value='0')
                'CU00_sel23': '1',         # 報表別: 應收明細 (value='1')
                'CU00_sel': 'Y',           # 已離管外勞是否列出: Y(要) (value='Y')

                # 提交按鈕的 name 和 value
                'key': '列印作業'
            }
            # --- Payload 組裝結束 ---

            try:
                # 發送 POST 請求到 submit_url
                # st.info(f"正在為 [{name}] (ID: {employee_id_value}) 發送請求...") # 可選的進度訊息
                response = session.post(submit_url, data=payload, timeout=REQUEST_TIMEOUT)
                response.raise_for_status() # 檢查 HTTP 錯誤 (4xx, 5xx)

                # --- 步驟 4：解碼伺服器回應 ---
                html_content = "" # 初始化
                try:
                    # 優先嘗試 Big5
                    html_content = response.content.decode('big5')
                    # st.info(f"收到 [{name}] 的回應 (Big5 解碼)，正在解析...") # 可選的進度訊息
                except UnicodeDecodeError:
                    try:
                        # Big5 失敗，嘗試 cp950
                        html_content = response.content.decode('cp950')
                        # st.info(f"收到 [{name}] 的回應 (cp950 解碼)，正在解析...") # 可選的進度訊息
                    except UnicodeDecodeError:
                        # 如果都失敗，使用 requests 的自動偵測
                        st.warning(f"警告：[{name}] 的回應 Big5/cp950 解碼失敗，嘗試使用自動偵測的編碼 ({response.apparent_encoding})。")
                        response.encoding = response.apparent_encoding
                        html_content = response.text
                # --- 解碼結束 ---

                # --- 步驟 5：使用 BeautifulSoup 解析 HTML 並提取資料 ---
                soup = BeautifulSoup(html_content, 'lxml')
                # 找到所有 class 為 'bg1' 或 'bg2' 的 <tr> 標籤
                data_rows = soup.find_all('tr', class_=['bg1', 'bg2'])
                # st.write(f"[{name}] BeautifulSoup 找到 {len(data_rows)} 個 <tr class='bg1' or class='bg2'> 標籤。") # 除錯訊息
                if not data_rows and response.ok: # 如果請求成功但沒找到資料列
                     st.info(f"員工 [{name}] 在此查詢條件下沒有找到任何資料。")

                found_data_for_employee = False
                processed_rows = 0
                # 遍歷找到的每一行 <tr>
                for row_index, row in enumerate(data_rows):
                    cells = row.find_all('td') # 找到該行所有的 <td> 標籤
                    # 檢查是否有足夠的欄位 (至少 9 個)
                    if len(cells) >= 9:
                        first_cell_text = cells[0].get_text(strip=True) # 獲取第一欄的文字

                        # 如果第一欄的文字不是 "序號" (排除表頭)
                        if first_cell_text != "序號":
                            # 提取前 9 個欄位的文字內容
                            row_data = [cell.get_text(strip=True) for cell in cells[:9]]
                            # 將業務員姓名附加到資料末尾 (供後續 bonus_logic 使用)
                            row_data.append(name)
                            all_details.append(row_data) # 將此行資料加入總列表
                            found_data_for_employee = True
                            processed_rows += 1 # 增加處理行數計數

                # if found_data_for_employee:
                #      st.write(f"成功從表格中解析出 {processed_rows} 筆 [{name}] 的資料。") # 可選的成功訊息
                # elif data_rows: # 如果找到了 <tr> 但沒有解析出任何資料
                #     st.warning(f"警告：[{name}] 找到了表格列，但沒有解析出任何資料列 (請檢查表格結構或解析條件)。")

                # 在處理下一個員工前稍作停頓，避免請求過於頻繁
                time.sleep(0.3)

            # --- 步驟 6：錯誤處理 ---
            except requests.exceptions.Timeout:
                 st.warning(f"查詢員工 [{name}] 時請求超時 ({REQUEST_TIMEOUT}秒)，已跳過。")
                 continue # 繼續下一個員工
            except requests.exceptions.RequestException as e:
                # 處理網路連線或 HTTP 錯誤
                status_code = e.response.status_code if e.response is not None else 'N/A'
                st.warning(f"查詢員工 [{name}] 時發生網路錯誤 (狀態碼: {status_code})，已跳過: {e}")
                continue # 繼續下一個員工
            except Exception as e:
                # 處理其他未預期的錯誤 (例如解析錯誤)
                st.warning(f"處理員工 [{name}] 的資料時發生錯誤，已跳過: {e}\n"
                           f"回應內容預覽 (前 500 字元):\n{response.text[:500] if 'response' in locals() else '無法獲取回應內容'}")
                continue # 繼續下一個員工
            # --- 錯誤處理結束 ---

        # --- 所有員工處理完畢 ---

    # --- 步驟 7：整理結果並返回 ---
    # 如果有員工因為找不到 ID 而被跳過，顯示錯誤訊息
    if missing_id_employees:
        st.error(f"以下員工因在聘軒系統當前的下拉選單中找不到對應 ID 而被跳過：{', '.join(missing_id_employees)}")

    # 如果最終沒有收集到任何資料
    if not all_details:
        st.warning("所有員工查詢完成，但未擷取到任何有效的明細資料。")
        # 返回空的 DataFrame 和被跳過的員工列表
        return pd.DataFrame(columns=["序號", "雇主姓名", "入境日", "外勞姓名", "帳款名稱", "帳款日", "應收金額", "收款日", "實收金額", "業務員姓名"]), missing_id_employees

    # 定義最終 DataFrame 的欄位名稱
    headers = ["序號", "雇主姓名", "入境日", "外勞姓名", "帳款名稱", "帳款日", "應收金額", "收款日", "實收金額", "業務員姓名"]
    st.success(f"所有員工查詢完成，共擷取 {len(all_details)} 筆明細。")
    # 創建 DataFrame 並返回結果和被跳過的員工列表
    return pd.DataFrame(all_details, columns=headers), missing_id_employees