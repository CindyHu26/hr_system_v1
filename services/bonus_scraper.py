# services/bonus_scraper.py
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from utils.helpers import get_monthly_dates
import config

WAIT_TIMEOUT = 20

def get_salespersons_list(username, password):
    """登入系統並獲取業務人員的下拉選單列表。"""
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 5)

        if not config.BONUS_SYSTEM_URL:
            raise ValueError("錯誤：請在 .env 檔案中設定 BONUS_SYSTEM_URL")
        base_url = config.BONUS_SYSTEM_URL.replace("http://", "").replace("https://", "")
        url = f"http://{username}:{password}@{base_url}"
        
        driver.get(url)
        sales_dropdown = wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/form/table/tbody/tr[12]/td/select")))
        salespersons = [opt.text.strip() for opt in Select(sales_dropdown).options if opt.get_attribute("value")]
        return salespersons
    except Exception as e:
        raise ConnectionError(f"無法連接到獎金系統或獲取業務員列表，請檢查 .env 設定與系統狀態。錯誤: {e}")
    finally:
        if driver:
            driver.quit()

def fetch_all_bonus_data(username, password, year, month, salespersons, progress_callback=None):
    """【優化版 V2】遍歷所有業務員，使用單一瀏覽器實例抓取業績資料，並在每次查詢後返回上一頁。"""
    all_details = []
    _, end_date = get_monthly_dates(year, month)
    search_start_date = f"{year-1}-{month:02d}-01"
    
    driver = None
    try:
        options = webdriver.ChromeOptions()
        # options.add_argument("--headless") # 如果需要無頭模式，請取消註解
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        
        if not config.BONUS_SYSTEM_URL:
            raise ValueError("錯誤：請在 .env 檔案中設定 BONUS_SYSTEM_URL")
        base_url = config.BONUS_SYSTEM_URL.replace("http://", "").replace("https://", "")
        url = f"http://{username}:{password}@{base_url}"
        driver.get(url)

        for i, name in enumerate(salespersons):
            if progress_callback:
                progress_callback(f"({i+1}/{len(salespersons)}) 正在擷取 [{name}] 的資料...", (i + 1) / len(salespersons))
            
            # 等待確保回到了主查詢頁面
            wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/form/table/tbody/tr[12]/td/select")))

            wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/form/table/tbody/tr[6]/td/input[1]"))).clear()
            wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/form/table/tbody/tr[6]/td/input[1]"))).send_keys(search_start_date)
            
            wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/form/table/tbody/tr[7]/td/input[1]"))).clear()
            wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/form/table/tbody/tr[7]/td/input[1]"))).send_keys(end_date)
            
            Select(wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/form/table/tbody/tr[12]/td/select")))).select_by_visible_text(name)
            Select(wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/form/table/tbody/tr[20]/td/select")))).select_by_value("1")
            
            wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/form/table/tbody/tr[27]/td/input[1]"))).click()
            
            wait.until(EC.visibility_of_element_located((By.XPATH, "//td[contains(text(), '應收合計')]")))
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'lxml')
            data_rows = soup.find_all('tr', class_=['bg1', 'bg2'])
            
            for row in data_rows:
                cells = row.find_all('td')
                if len(cells) >= 9:
                    all_details.append([cell.get_text(strip=True) for cell in cells[:9]])
            
            # **【關鍵修改】**
            # 在抓取完資料後，模擬點擊瀏覽器的 "返回" 按鈕
            driver.back()

    finally:
        if driver:
            driver.quit()

    if not all_details:
        return pd.DataFrame()

    headers = ["序號", "雇主姓名", "入境日", "外勞姓名", "帳款名稱", "帳款日", "應收金額", "收款日", "實收金額"]
    return pd.DataFrame(all_details, columns=headers)