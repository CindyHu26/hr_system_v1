# services/performance_bonus_scraper.py
import os
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
import config

def fetch_performance_count(username, password, start_date_str, end_date_str):
    """
    登入指定系統，填寫表單並抓取最終合計人數。
    此函式改寫自您提供的腳本，使其更為通用。
    """
    if not config.PERFORMANCE_BONUS_URL:
        raise ValueError("環境變數 PERFORMANCE_BONUS_URL 未設定。")

    # 建立一個專用的下載資料夾（雖然不用下載，但這是個好習慣）
    download_path = os.path.join(os.getcwd(), "temp_downloads")
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "safeBrowse.disable_download_protection": True
    }
    options.add_experimental_option("prefs", prefs)
    # 若要在背景執行，可以取消下一行的註解
    # options.add_argument('--headless')

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        
        # 組合包含帳號密碼的 URL
        base_url_no_protocol = config.PERFORMANCE_BONUS_URL.split('//')[1]
        auth_url = f"http://{username}:{password}@{base_url_no_protocol}"
        driver.get(auth_url)
        time.sleep(2)

        # 定義一個內部函式簡化操作
        def clear_and_fill(xpath, value):
            el = driver.find_element(By.XPATH, xpath)
            el.clear()
            el.send_keys(value)

        # 填寫表單
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

        # 點擊查詢按鈕 (假設是 "轉出Excel" 按鈕觸發查詢)
        driver.find_element(By.XPATH, '//*[@id="myform"]/table/tbody/tr[32]/td/input[1]').click()
        time.sleep(3) # 等待頁面刷新

        # 抓取頁面源碼並尋找目標文字
        page_content = driver.page_source
        
        # 使用正規表示式尋找您要的目標行
        pattern = r"合計:\s*(\d+)人.*?遞補:\s*(\d+)人"
        match = re.search(pattern, page_content)

        if not match:
            raise ValueError("在頁面源碼中找不到符合 '合計: X人, ... 遞補: Y人' 格式的文字。")
        
        total_count = int(match.group(1))
        replacement_count = int(match.group(2))
        
        # 根據您的計算邏輯回傳結果
        final_count = total_count - replacement_count
        return final_count

    finally:
        if driver:
            driver.quit()