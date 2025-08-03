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

def fetch_performance_count(username, password, start_date_str, end_date_str):
    """
    【修正版 v4】
    - 根據使用者提供的最新 HTML 結構，修正所有欄位的定位方式。
    - 保留從 .crdownload 暫存檔讀取文字的邏輯。
    - 移除舊的、不穩定的 full XPath 定位方式。
    """
    PERFORMANCE_BONUS_URL = os.getenv("PERFORMANCE_BONUS_URL")
    if not PERFORMANCE_BONUS_URL:
        raise ValueError("環境變數 PERFORMANCE_BONUS_URL 未設定。")

    download_path = os.path.join(os.getcwd(), "temp_downloads_perf")
    if not os.path.exists(download_path): os.makedirs(download_path)
    for f in glob.glob(os.path.join(download_path, "*.*")): os.remove(f)

    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False, "download.directory_upgrade": True,
        "safeBrowse.enabled": True, "plugins.always_open_pdf_externally": True
    }
    options.add_experimental_option("prefs", prefs)
    options.add_argument('--headless')

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 180)
        
        base_url_no_protocol = PERFORMANCE_BONUS_URL.split('//')[1]
        auth_url = f"http://{username}:{password}@{base_url_no_protocol}"
        driver.get(auth_url)
        
        wait.until(EC.presence_of_element_located((By.NAME, "myform")))
        
        # 1. 填寫期間起始日與截止日
        driver.find_element(By.ID, "CU00_BDATE").clear()
        driver.find_element(By.ID, "CU00_BDATE").send_keys(start_date_str)
        driver.find_element(By.ID, "CU00_EDATE").clear()
        driver.find_element(By.ID, "CU00_EDATE").send_keys(end_date_str)
        
        # 2. 選擇下拉選單選項
        Select(driver.find_element(By.NAME, "CU00_LA198")).select_by_visible_text('一般移工')
        Select(driver.find_element(By.NAME, "CU00_ORG1")).select_by_visible_text('入境任用')
        Select(driver.find_element(By.NAME, "CU00_LNO")).select_by_visible_text('聘僱中')
        Select(driver.find_element(By.NAME, "CU00_SALERS")).select_by_visible_text('全部')
        
        # 3. 填寫其他輸入框 (根據舊版邏輯)
        # 注意: 如果這些欄位不存在或不需要，可以安全地移除
        driver.find_element(By.NAME, "CU00_SDATE").clear()
        driver.find_element(By.NAME, "CU00_SDATE").send_keys('1')
        driver.find_element(By.NAME, "CU00_drt").clear()
        driver.find_element(By.NAME, "CU00_drt").send_keys('5')
        driver.find_element(By.NAME, "CU00_SEL33").clear()
        driver.find_element(By.NAME, "CU00_SEL33").send_keys('9')

        # 4. 點擊按鈕以觸發下載 (注意：這裡的按鈕是 "轉出Excel"，而不是 "列印作業")
        # 根據您的需求，我假設這個頁面觸發的是下載而不是顯示在頁面上
        # 如果是顯示在頁面，邏輯會需要再次調整
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='轉出Excel']").click()
        
        # --- 後續邏輯維持不變，繼續等待並讀取 .crdownload 檔案 ---
        wait_time = 0
        max_wait_time = 60 # 等待時間可依需調整
        file_found = False
        
        while wait_time < max_wait_time:
            target_files = glob.glob(os.path.join(download_path, "*.crdownload"))
            if target_files:
                latest_file = max(target_files, key=os.path.getmtime)
                # 等待一下，確保檔案內容已被寫入
                time.sleep(2) 
                file_found = True
                break
            time.sleep(1)
            wait_time += 1

        if not file_found:
            raise TimeoutError(f"在 {max_wait_time} 秒內，於 '{download_path}' 資料夾中找不到任何 .crdownload 檔案。")

        # 讀取暫存檔內容
        with open(latest_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # 使用正規表示式解析檔案內容
        # 假設 .crdownload 內部的文字格式與您之前提到的類似
        pattern = r"合計:\s*(\d+)人.*?遞補:\s*(\d+)人"
        match = re.search(pattern, content)

        if not match:
            # 如果找不到，提供一個更有用的錯誤訊息
            # print(f"暫存檔內容: {content[:500]}") # 偵錯用，可以印出檔案內容
            raise ValueError("在下載的暫存檔案內容中找不到 '合計: X人' 和 '遞補: Y人' 的格式文字。")
        
        total_count = int(match.group(1))
        replacement_count = int(match.group(2))
        
        final_count = total_count - replacement_count
        return final_count

    finally:
        if driver:
            driver.quit()
        if os.path.exists(download_path):
            for f in glob.glob(os.path.join(download_path, "*.*")):
                os.remove(f)
            os.rmdir(download_path)