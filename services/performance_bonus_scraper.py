# services/performance_bonus_scraper.py
import os
import re
import time
import pandas as pd
import glob
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import config

def fetch_performance_count(username, password, start_date_str, end_date_str):
    """
    【修正版 v2】
    - 根據使用者提供的最新 HTML 結構，修正所有欄位的定位方式。
    - 將操作流程改為：填寫表單 -> 點擊 "轉出Excel" -> 等待下載 -> 讀取 Excel 檔案 -> 計算行數。
    - 增加更穩健的等待機制與檔案清理邏輯。
    """
    if not config.PERFORMANCE_BONUS_URL:
        raise ValueError("環境變數 PERFORMANCE_BONUS_URL 未設定。")

    # 建立一個專用的下載資料夾
    download_path = os.path.join(os.getcwd(), "temp_downloads_perf")
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # 清空舊的檔案，避免讀到上一次的紀錄
    for f in glob.glob(os.path.join(download_path, "*.*")):
        os.remove(f)

    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safeBrowse.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    # 偵錯時建議註解下面這行，以便觀察瀏覽器實際操作
    # options.add_argument('--headless')

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 120)
        
        base_url_no_protocol = config.PERFORMANCE_BONUS_URL.split('//')[1]
        auth_url = f"http://{username}:{password}@{base_url_no_protocol}"
        driver.get(auth_url)
        
        # 等待表單出現
        wait.until(EC.presence_of_element_located((By.NAME, "myform")))
        
        # --- 【核心修改】根據新的 HTML 結構填寫表單 ---
        
        # 1. 填寫期間起始日與截止日
        driver.find_element(By.ID, "CU00_BDATE").clear()
        driver.find_element(By.ID, "CU00_BDATE").send_keys(start_date_str)
        driver.find_element(By.ID, "CU00_EDATE").clear()
        driver.find_element(By.ID, "CU00_EDATE").send_keys(end_date_str)
        
        # 2. 選擇下拉選單選項
        Select(driver.find_element(By.NAME, "CU00_LA198")).select_by_visible_text('一般移工')
        Select(driver.find_element(By.NAME, "CU00_ORG1")).select_by_visible_text('入境任用')
        Select(driver.find_element(By.NAME, "CU00_LNO")).select_by_visible_text('所有')
        Select(driver.find_element(By.NAME, "CU00_SALERS")).select_by_visible_text('全部')
        
        # 3. 點擊按鈕以觸發下載
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='轉出Excel']").click()
        
        # 4. 等待檔案下載完成
        wait_time = 0
        max_wait_time = 60 # 最長等待60秒
        downloaded_file_path = None
        
        while wait_time < max_wait_time:
            # 尋找已下載完成的檔案 (不是 .crdownload)
            downloaded_files = [f for f in os.listdir(download_path) if f.endswith('.xls') or f.endswith('.xlsx')]
            if downloaded_files:
                downloaded_file_path = os.path.join(download_path, downloaded_files[0])
                break
            time.sleep(1)
            wait_time += 1

        if not downloaded_file_path:
            raise TimeoutError(f"在 {max_wait_time} 秒內，於 '{download_path}' 資料夾中找不到下載完成的 Excel 檔案。")

        # 5. 讀取 Excel 檔案並計算人數
        # 使用 xlrd 引擎以兼容舊版 .xls 格式
        df = pd.read_excel(downloaded_file_path, engine='xlrd')
        
        # 人數 = DataFrame 的行數 (假設一行代表一人)
        # 您可能需要根據實際 Excel 內容調整，例如減去表頭行
        # 如果第一行是標題，實際人數會是 len(df)
        # 如果 Excel 有合計欄，可能需要更複雜的處理
        # 此處我們假設行數即為人數
        final_count = len(df)
        
        return final_count

    finally:
        if driver:
            driver.quit()
        # 確保無論成功或失敗，都清空下載資料夾
        if os.path.exists(download_path):
            for f in glob.glob(os.path.join(download_path, "*.*")):
                os.remove(f)
            os.rmdir(download_path)