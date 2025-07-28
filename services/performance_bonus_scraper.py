# services/performance_bonus_scraper.py
import os
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
import glob
import config

def fetch_performance_count(username, password, start_date_str, end_date_str):
    """
    【修正版】登入指定系統，觸發下載後，直接等待並讀取 .crdownload 暫存檔以獲取人數。
    """
    if not config.PERFORMANCE_BONUS_URL:
        raise ValueError("環境變數 PERFORMANCE_BONUS_URL 未設定。")

    # 建立一個專用的下載資料夾
    download_path = os.path.join(os.getcwd(), "temp_downloads")
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # 清空舊的暫存檔，避免讀到上一次的紀錄
    for f in glob.glob(os.path.join(download_path, "*.crdownload")):
        os.remove(f)

    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "safeBrowse.disable_download_protection": True
    }
    options.add_experimental_option("prefs", prefs)
    # options.add_argument('--headless')

    driver = None
    latest_file = None # 將 latest_file 提到 try block 外層
    try:
        driver = webdriver.Chrome(options=options)
        
        base_url_no_protocol = config.PERFORMANCE_BONUS_URL.split('//')[1]
        auth_url = f"http://{username}:{password}@{base_url_no_protocol}"
        driver.get(auth_url)
        time.sleep(2)

        def clear_and_fill(xpath, value):
            el = driver.find_element(By.XPATH, xpath)
            el.clear()
            el.send_keys(value)

        # --- 填寫表單 (與之前相同) ---
        clear_and_fill('//*[@id="myform"]/table/tbody/tr[4]/td/input', '1')
        clear_and_fill('//*[@id="CU00_BDATE"]', start_date_str)
        clear_and_fill('//*[@id="CU00_EDATE"]', end_date_str)
        Select(driver.find_element(By.XPATH, '//*[@id="myform"]/table/tbody/tr[12]/td/select')).select_by_visible_text('全部')
        Select(driver.find_element(By.XPATH, '//*[@id="myform"]/table/tbody/tr[13]/td/select')).select_by_visible_text('一般移工')
        Select(driver.find_element(By.XPATH, '//*[@id="myform"]/table/tbody/tr[15]/td/select')).select_by_visible_text('所有')
        Select(driver.find_element(By.XPATH, '//*[@id="myform"]/table/tbody/tr[16]/td/select')).select_by_visible_text('入境任用')
        Select(driver.find_element(By.XPATH, '//*[@id="myform"]/table/tbody/tr[17]/td/select')).select_by_visible_text('所有')
        Select(driver.find_element(By.XPATH, '//*[@id="myform"]/table/tbody/tr[24]/td/select')).select_by_visible_text('全部')
        clear_and_fill('//*[@id="myform"]/table/tbody/tr[26]/td/input', '5')
        clear_and_fill('//*[@id="myform"]/table/tbody/tr[28]/td/input', '9')

        # --- 【核心修改】從讀取頁面改為等待檔案 ---
        
        # 1. 點擊按鈕以觸發下載
        driver.find_element(By.XPATH, '//*[@id="myform"]/table/tbody/tr[32]/td/input[1]').click()
        
        # 2. 建立等待迴圈，尋找 .crdownload 檔案
        wait_time = 0
        max_wait_time = 30 # 最長等待30秒
        file_found = False
        
        while wait_time < max_wait_time:
            target_files = glob.glob(os.path.join(download_path, "*.crdownload"))
            if target_files:
                latest_file = max(target_files, key=os.path.getmtime)
                file_found = True
                break
            time.sleep(1)
            wait_time += 1

        if not file_found:
            raise TimeoutError(f"在 {max_wait_time} 秒內，於 '{download_path}' 資料夾中找不到任何 .crdownload 檔案。")

        # 3. 讀取檔案內容
        # 稍微等待一下，確保檔案已寫入完成
        time.sleep(1)
        with open(latest_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 4. 使用正規表示式解析檔案內容
        pattern = r"合計:\s*(\d+)人.*?遞補:\s*(\d+)人"
        match = re.search(pattern, content)

        if not match:
            raise ValueError("在下載的檔案內容中找不到符合 '合計: X人, ... 遞補: Y人' 格式的文字。")
        
        total_count = int(match.group(1))
        replacement_count = int(match.group(2))
        
        final_count = total_count - replacement_count
        return final_count

    finally:
        if driver:
            driver.quit()
        # 確保無論成功或失敗，都刪除暫存檔
        if latest_file and os.path.exists(latest_file):
            os.remove(latest_file)