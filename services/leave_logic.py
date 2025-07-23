# services/leave_logic.py
"""
此模組包含請假紀錄相關的商業邏輯。
- 從 Google Sheet 或 Excel 檔案讀取假單。
- 精確計算請假時數（扣除午休、假日）。
"""
import pandas as pd
import requests
import io
from datetime import datetime, time, date, timedelta
import traceback

# --- 讀取與解析 ---

def read_leave_file(source_input):
    """
    從 Google Sheet URL 或上傳的檔案中讀取請假資料。
    會自動將 Google Sheet 分享連結轉換為可下載的 CSV 連結。
    """
    try:
        if isinstance(source_input, str) and "docs.google.com/spreadsheets" in source_input:
            # 將標準的 Google Sheet 連結轉換為 CSV 下載連結
            csv_export_url = source_input.replace('/edit?usp=sharing', '/export?format=csv')
            response = requests.get(csv_export_url)
            response.raise_for_status()
            # 將下載的內容當作一個檔案來讀取
            source = io.StringIO(response.text)
        else: # 處理上傳的檔案物件
            source = source_input

        # 將所有資料讀取為字串，避免日期等格式被自動轉換錯誤
        df = pd.read_csv(source, dtype=str).fillna("")
        
        # 只處理已通過的假單
        df = df[df['Status'] == '已通過'].copy()
        if df.empty:
            raise ValueError("找不到任何狀態為「已通過」的假單。")

        # --- 關鍵的日期時間解析 ---
        # 為了處理 'YYYY/MM/DD' 和 'YYYY/MM/DD HH:MM:SS' 兩種混合格式
        df['Start Date'] = pd.to_datetime(df['Start Date'], errors='coerce')
        df['End Date'] = pd.to_datetime(df['End Date'], errors='coerce')
        df['Date Submitted'] = pd.to_datetime(df['Date Submitted'], errors='coerce')
        
        # 移除解析失敗的行
        df.dropna(subset=['Start Date', 'End Date'], inplace=True)

        return df
    except Exception as e:
        raise ValueError(f"讀取或解析請假檔案時發生錯誤: {e}")


# --- 時數計算 ---

def fetch_taiwan_calendar(year: int):
    """
    獲取指定年份的台灣政府行政機關辦公日曆。
    注意：此為簡易範例，政府網站可能改版。為求穩定，暫時返回空集合。
    未來可替換為更可靠的 API 或手動維護假日列表。
    """
    try:
        # 範例：從政府開放資料平台獲取資料 (需注意 API 變動)
        # url = f"https://data.gov.tw/api/v2/rest/dataset/100142" 
        # response = requests.get(url)
        # data = response.json()
        # ... 解析 data 的邏輯 ...
        st.warning(f"注意：目前為開發模式，未實際抓取 {year} 年的台灣行事曆。")
        holidays = set() # 應為假日
        workdays = set() # 應為補班日
        return holidays, workdays
    except Exception as e:
        print(f"無法獲取台灣行事曆資料：{e}")
        return set(), set()

def calculate_leave_hours(start_dt, end_dt, is_full_day):
    """
    精確計算請假時數，支援跨日、自動排除週末與假日、扣除午休。
    """
    if pd.isna(start_dt) or pd.isna(end_dt) or end_dt < start_dt:
        return 0.0

    holidays, makeup_workdays = fetch_taiwan_calendar(start_dt.year)
    if start_dt.year != end_dt.year:
        h, w = fetch_taiwan_calendar(end_dt.year)
        holidays.update(h)
        makeup_workdays.update(w)
        
    total_hours = 0.0
    
    # 定義公司工時與午休時間
    work_start, lunch_start = time(8, 30), time(12, 0)
    lunch_end, work_end = time(13, 0), time(17, 30)
    
    current_date = start_dt.date()
    while current_date <= end_dt.date():
        # 判斷是否為工作日
        is_weekend = current_date.weekday() >= 5
        is_holiday = current_date in holidays
        is_makeup_workday = current_date in makeup_workdays
        
        # 如果是週末且不是補班日，或 是假日且不是補班日 -> 跳過
        if (is_weekend and not is_makeup_workday) or (is_holiday and not is_makeup_workday):
            current_date += timedelta(days=1)
            continue

        # 根據是否為全天假，決定當天的請假時間範圍
        if is_full_day:
            day_leave_start = work_start
            day_leave_end = work_end
        else:
            day_leave_start = start_dt.time() if current_date == start_dt.date() else time.min
            day_leave_end = end_dt.time() if current_date == end_dt.date() else time.max
        
        # 計算上午工時交集
        am_overlap_start = max(day_leave_start, work_start)
        am_overlap_end = min(day_leave_end, lunch_start)
        if am_overlap_end > am_overlap_start:
            duration = datetime.combine(date.today(), am_overlap_end) - datetime.combine(date.today(), am_overlap_start)
            total_hours += duration.total_seconds() / 3600

        # 計算下午工時交集
        pm_overlap_start = max(day_leave_start, lunch_end)
        pm_overlap_end = min(day_leave_end, work_end)
        if pm_overlap_end > pm_overlap_start:
            duration = datetime.combine(date.today(), pm_overlap_end) - datetime.combine(date.today(), pm_overlap_start)
            total_hours += duration.total_seconds() / 3600
            
        current_date += timedelta(days=1)
        
    return round(total_hours, 2)


def check_and_calculate_all_leave_hours(df: pd.DataFrame):
    """
    遍歷 DataFrame 中所有的假單，計算其核算時數。
    """
    results = []
    df['is_full_day'] = df['Start Date'].dt.time == time(0, 0)

    for _, row in df.iterrows():
        try:
            leave_hours = calculate_leave_hours(row['Start Date'], row['End Date'], row['is_full_day'])
            new_row = row.to_dict()
            new_row["核算時數"] = leave_hours
            # 將原始時數與核算時數做比較
            original_duration = pd.to_numeric(row['Duration (Hours)'], errors='coerce')
            if pd.notna(original_duration) and abs(original_duration - leave_hours) > 0.1:
                new_row["備註"] = f"系統核算時數({leave_hours})與原單據時數({original_duration})不符"
            else:
                 new_row["備註"] = ""
            results.append(new_row)
        except Exception:
            new_row = row.to_dict()
            new_row["核算時數"] = 0.0
            new_row["備註"] = f"時數核算時發生錯誤: {traceback.format_exc()}"
            results.append(new_row)
            
    result_df = pd.DataFrame(results)
    
    # 重新排列欄位順序，讓重要資訊靠前
    cols_order = [
        'Employee Name', 'Type of Leave', 'Start Date', 'End Date', 
        'Duration (Hours)', '核算時數', '備註', 'Request ID', 'Status'
    ]
    # 篩選出 DataFrame 中實際存在的欄位
    existing_cols = [col for col in cols_order if col in result_df.columns]
    # 找出其他剩餘的欄位
    other_cols = [col for col in result_df.columns if col not in existing_cols]
    
    return result_df[existing_cols + other_cols]