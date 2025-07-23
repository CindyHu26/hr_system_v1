# config.py
import os
from dotenv import load_dotenv

# 從 .env 檔案載入環境變數 (如果存在)
load_dotenv()

# --- 薪資計算相關設定 ---
# 計算時薪時的固定除數 (每月時數)
HOURLY_RATE_DIVISOR = 240.0

# --- 二代健保補充保費相關 ---
NHI_SUPPLEMENT_RATE = 0.0211

# --- 外部連結設定 ---
LABOR_INSURANCE_URL = "https://www.bli.gov.tw/0011588.html"
HEALTH_INSURANCE_URL = "https://www.nhi.gov.tw/ch/cp-17545-f87bd-2576-1.html"

# --- 請假單來源設定 (Google Sheet) ---
# 建議您在專案根目錄建立一個 .env 檔案，並在其中寫入 GSHEET_URL="您的GoogleSheet分享連結"
# 這樣就不會將連結直接寫在程式碼中。
# os.getenv 會優先讀取 .env 中的設定。
DEFAULT_GSHEET_URL = os.getenv("GSHEET_URL", "請在此貼上您的Google Sheet分享連結或在.env中設定")