# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# --- 基本工資設定 (應隨法規更新) ---
MINIMUM_WAGE = 28590 #2025年1月起的基本工資

# --- 薪資計算相關設定 ---
HOURLY_RATE_DIVISOR = 240.0

# --- 二代健保補充保費相關 ---
NHI_SUPPLEMENT_RATE = 0.0211
NHI_SUPPLEMENT_THRESHOLD = MINIMUM_WAGE
# [新增] 用於計算個人高額獎金補充保費的投保薪資倍數
NHI_BONUS_MULTIPLIER = 4
# [新增] 定義哪些薪資項目屬於需要累計計算補充保費的 "獎金"
NHI_BONUS_ITEMS = [
    '津貼', '津貼加班', '特休未休', '主管津貼', 
    '仲介師', '加薪', '補助', '業務獎金', '績效獎金'
]

# --- 外籍人士稅務設定 ---
FOREIGNER_TAX_RATE_THRESHOLD_MULTIPLIER = 1.5
FOREIGNER_LOW_INCOME_TAX_RATE = 0.06
FOREIGNER_HIGH_INCOME_TAX_RATE = 0.18

# --- 外部連結設定 ---
LABOR_INSURANCE_URL = "https://www.bli.gov.tw/0011588.html"
HEALTH_INSURANCE_URL = "https://www.nhi.gov.tw/ch/cp-17545-f87bd-2576-1.html"

# --- 請假單來源設定 (Google Sheet) ---
DEFAULT_GSHEET_URL = os.getenv("GSHEET_URL", "請在此貼上您的Google Sheet分享連結或在.env中設定")

# --- 業績獎金系統來源設定 ---
BONUS_SYSTEM_URL = os.getenv("BONUS_SYSTEM_URL")

# --- 績效獎金系統URL
PERFORMANCE_BONUS_URL = os.getenv("PERFORMANCE_BONUS_URL")