# services/bonus_scraper.py
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup
from utils.helpers import get_monthly_dates
import config

WAIT_TIMEOUT = 60

# 【函式已移除】此函式不再需要，因為員工名單將從主程式傳入
# def get_salespersons_list(username, password): ...

def fetch_all_bonus_data(username, password, year, month, employee_names, progress_callback=None):
    """
    【全新邏輯】使用 HR 系統的員工名單作為查詢依據。
    - 遍歷傳入的 employee_names 列表。
    - 對於在獎金系統中找不到的員工姓名，會跳過並回報。
    """
    all_details = []
    not_found_employees = [] # 用於記錄在獎金系統中找不到的員工
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

        # 【核心修改】遍歷從 HR 系統資料庫傳入的員工名單
        for i, name in enumerate(employee_names):
            if progress_callback:
                progress_callback(f"({i+1}/{len(employee_names)}) 正在擷取 [{name}] 的資料...", (i + 1) / len(employee_names))
            
            wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id=\"myform\"]/table/tbody/tr[12]/td/select")))

            # --- 填寫表單 ---
            receipt_start_date_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id=\"CU00_BDATE1\"]")))
            receipt_start_date_input.clear()
            receipt_start_date_input.send_keys(start_date)
            
            receipt_end_date_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id=\"CU00_EDATE1\"]")))
            receipt_end_date_input.clear()
            receipt_end_date_input.send_keys(end_date)

            Select(wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id=\"myform\"]/table/tbody/tr[10]/td/select")))).select_by_index(0)

            # --- 【新增錯誤處理】選擇業務人員 ---
            try:
                # 依據傳入的姓名，選擇下拉選單中的項目
                Select(wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id=\"myform\"]/table/tbody/tr[12]/td/select")))).select_by_visible_text(name)
            except NoSuchElementException:
                # 如果在下拉選單中找不到該姓名，則記錄下來並跳過此人
                not_found_employees.append(name)
                continue # 繼續處理下一位員工

            Select(wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id=\"myform\"]/table/tbody/tr[17]/td/select")))).select_by_index(0)
            Select(wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id=\"myform\"]/table/tbody/tr[20]/td/select")))).select_by_value("1")
            wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id=\"myform\"]/table/tbody/tr[27]/td/input[1]"))).click()
            
            # --- 資料抓取與返回 ---
            wait.until(EC.visibility_of_element_located((By.XPATH, "//td[contains(text(), '應收合計')]")))
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'lxml')
            data_rows = soup.find_all('tr', class_=['bg1', 'bg2'])
            
            for row in data_rows:
                cells = row.find_all('td')
                if len(cells) >= 9:
                    all_details.append([cell.get_text(strip=True) for cell in cells[:9]])
            
            driver.back()

    finally:
        if driver:
            driver.quit()
    
    # 【核心修改】回傳抓到的資料以及找不到的員工名單
    if not all_details:
        return pd.DataFrame(), not_found_employees

    headers = ["序號", "雇主姓名", "入境日", "外勞姓名", "帳款名稱", "帳款日", "應收金額", "收款日", "實收金額"]
    return pd.DataFrame(all_details, columns=headers), not_found_employees