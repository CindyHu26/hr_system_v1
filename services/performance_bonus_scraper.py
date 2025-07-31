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
    【修正版 v3】
    - 強化 Chrome 瀏覽器選項，降低下載被阻擋的機率。
    - 延長檔案下載的等待時間至 120 秒。
    - 在偵錯時，更容易透過取消註解來觀察實際瀏覽器行為。
    """
    if not config.PERFORMANCE_BONUS_URL:
        raise ValueError("環境變數 PERFORMANCE_BONUS_URL 未設定。")

    download_path = os.path.join(os.getcwd(), "temp_downloads_perf")
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    for f in glob.glob(os.path.join(download_path, "*.*")):
        os.remove(f)

    options = webdriver.ChromeOptions()
    
    # ▼▼▼▼▼【程式碼修正處】▼▼▼▼▼
    # 優化下載相關設定，提高成功率
    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False, # 禁止跳出另存新檔視窗
        "download.directory_upgrade": True,
        "safeBrowse.enabled": False, # 關閉安全瀏覽功能
        "plugins.always_open_pdf_externally": True, # 避免在瀏覽器內開啟PDF
        "safeBrowse.disable_download_protection": True # 停用下載保護
    }
    options.add_experimental_option("prefs", prefs)
    # 偵錯時建議註解下面這行，以便觀察瀏覽器實際操作
    # options.add_argument('--headless')
    # ▲▲▲▲▲【程式碼修正處】▲▲▲▲▲

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        # 將等待時間延長
        wait = WebDriverWait(driver, 180)
        
        base_url_no_protocol = config.PERFORMANCE_BONUS_URL.split('//')[1]
        auth_url = f"http://{username}:{password}@{base_url_no_protocol}"
        driver.get(auth_url)
        
        wait.until(EC.presence_of_element_located((By.NAME, "myform")))
        
        driver.find_element(By.ID, "CU00_BDATE").clear()
        driver.find_element(By.ID, "CU00_BDATE").send_keys(start_date_str)
        driver.find_element(By.ID, "CU00_EDATE").clear()
        driver.find_element(By.ID, "CU00_EDATE").send_keys(end_date_str)
        
        Select(driver.find_element(By.NAME, "CU00_LA198")).select_by_visible_text('一般移工')
        Select(driver.find_element(By.NAME, "CU00_ORG1")).select_by_visible_text('入境任用')
        Select(driver.find_element(By.NAME, "CU00_LNO")).select_by_visible_text('所有')
        Select(driver.find_element(By.NAME, "CU00_SALERS")).select_by_visible_text('全部')
        
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='轉出Excel']").click()
        
        # 將等待時間延長為 120 秒
        wait_time = 0
        max_wait_time = 120 
        downloaded_file_path = None
        
        while wait_time < max_wait_time:
            downloaded_files = [f for f in os.listdir(download_path) if f.endswith('.xls') or f.endswith('.xlsx')]
            if downloaded_files:
                # 確保檔案已完全寫入
                time.sleep(2)
                downloaded_file_path = os.path.join(download_path, downloaded_files[0])
                break
            time.sleep(1)
            wait_time += 1

        if not downloaded_file_path:
            raise TimeoutError(f"在 {max_wait_time} 秒內，於 '{download_path}' 資料夾中找不到下載完成的 Excel 檔案。")

        df = pd.read_excel(downloaded_file_path, engine='xlrd')
        
        final_count = len(df)
        
        return final_count

    finally:
        if driver:
            driver.quit()
        if os.path.exists(download_path):
            for f in glob.glob(os.path.join(download_path, "*.*")):
                os.remove(f)
            os.rmdir(download_path)