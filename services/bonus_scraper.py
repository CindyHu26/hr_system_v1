# services/bonus_scraper.py
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from bs4 import BeautifulSoup
from utils.helpers import get_monthly_dates
import config

# 等待時間可以視情況調整
WAIT_TIMEOUT = 120

def fetch_all_bonus_data(username, password, year, month, employee_names, progress_callback=None):
    """
    【修正版 v5】
    - 移除 UI 相關的 st.error 呼叫，改為向上拋出例外。
    """
    all_details = []
    not_found_employees = []
    start_date, end_date = get_monthly_dates(year, month)

    driver = None
    try:
        options = webdriver.ChromeOptions()
        # options.add_argument("--headless") 
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        
        if not config.BONUS_SYSTEM_URL:
            raise ValueError("錯誤：請在 .env 檔案中設定 BONUS_SYSTEM_URL")
        base_url = config.BONUS_SYSTEM_URL.replace("http://", "").replace("https://", "")
        url = f"http://{username}:{password}@{base_url}"
        driver.get(url)

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "form")))

        for i, name in enumerate(employee_names):
            if progress_callback:
                progress_callback(f"({i+1}/{len(employee_names)}) 正在擷取 [{name}] 的資料...", (i + 1) / len(employee_names))
            
            try:
                receipt_start_date_input = wait.until(EC.element_to_be_clickable((By.ID, "CU00_BDATE1")))
                receipt_start_date_input.clear()
                receipt_start_date_input.send_keys(start_date)
                
                receipt_end_date_input = wait.until(EC.element_to_be_clickable((By.ID, "CU00_EDATE1")))
                receipt_end_date_input.clear()
                receipt_end_date_input.send_keys(end_date)
                
                salesperson_select_element = wait.until(EC.visibility_of_element_located((By.NAME, "CU00_SALERS")))
                Select(salesperson_select_element).select_by_visible_text(name)

                submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='列印作業']")))
                submit_button.click()

            except TimeoutException:
                 # ▼▼▼▼▼【程式碼修正處】▼▼▼▼▼
                 # 改為拋出帶有清晰說明的例外
                 raise TimeoutException("在頁面上找不到必要的查詢欄位（如 '業務人員' 或 '列印作業' 按鈕），外部網站結構可能已大幅變更。")
                 # ▲▲▲▲▲【程式碼修正處】▲▲▲▲▲
            except NoSuchElementException:
                not_found_employees.append(name)
                print(f"在下拉選單中找不到員工: {name}，已跳過。")
                try:
                    driver.get(url) 
                    wait.until(EC.presence_of_element_located((By.TAG_NAME, "form")))
                except Exception as e:
                    print(f"重新載入頁面失敗: {e}")
                    raise 
                continue

            wait.until(EC.visibility_of_element_located((By.XPATH, "//td[contains(text(), '應收合計')]")))
            time.sleep(1) 

            soup = BeautifulSoup(driver.page_source, 'lxml')
            data_rows = soup.find_all('tr', class_=['bg1', 'bg2'])
            
            for row in data_rows:
                cells = row.find_all('td')
                if len(cells) >= 9:
                    if cells[0].get_text(strip=True) == "序號":
                        continue
                    
                    row_data = [cell.get_text(strip=True) for cell in cells[:9]]
                    row_data.append(name)
                    all_details.append(row_data)
            
            driver.back()
            wait.until(EC.presence_of_element_located((By.NAME, "CU00_SALERS")))

    finally:
        if driver:
            driver.quit()
    
    if not all_details:
        return pd.DataFrame(), not_found_employees

    headers = ["序號", "雇主姓名", "入境日", "外勞姓名", "帳款名稱", "帳款日", "應收金額", "收款日", "實收金額", "業務員姓名"]
    return pd.DataFrame(all_details, columns=headers), not_found_employees