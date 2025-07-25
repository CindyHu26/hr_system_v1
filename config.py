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
DEFAULT_GSHEET_URL = os.getenv("GSHEET_URL", "請在此貼上您的Google Sheet分享連結或在.env中設定")

# --- 獎金系統來源設定 ---
BONUS_SYSTEM_URL = os.getenv("BONUS_SYSTEM_URL")