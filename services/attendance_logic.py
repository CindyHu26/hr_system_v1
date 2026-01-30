# services/attendance_logic.py
import pandas as pd
import io
import re
import warnings
from datetime import time, datetime, timedelta
from db import queries_employee as q_emp

def read_attendance_file(file):
    """
    從上傳的類 Excel 檔案中讀取並解析出勤資料。(使用 read_html)
    """
    file.seek(0)
    # 忽略 pandas 讀取 html 時可能出現的 UserWarning
    warnings.filterwarnings("ignore", category=UserWarning, module="pandas")
    try:
        # 使用 read_html 是因為舊版的打卡機檔案本質上是 HTML 表格
        tables = pd.read_html(io.StringIO(file.read().decode('utf-8')), flavor='bs4', header=None)
        if len(tables) < 2:
            return None, "檔案格式不符，找不到主要的資料表格。"
        
        header_row = tables[0].iloc[1]
        sanitized_headers = [str(h).strip() for h in header_row]
        
        df = tables[1].copy()
        # 校正欄位數量不一致的問題
        if len(df.columns) != len(sanitized_headers):
            min_cols = min(len(df.columns), len(sanitized_headers))
            df = df.iloc[:, :min_cols]
            df.columns = sanitized_headers[:min_cols]
        else:
            df.columns = sanitized_headers
            
        if '人員 ID' not in df.columns:
            return None, "檔案中缺少 '人員 ID' 欄位，無法處理。"
            
        # 篩選出有效的員工紀錄 (例如以 'A' 開頭的ID)
        df = df[df['人員 ID'].astype(str).str.contains('^A[0-9]', na=False)].reset_index(drop=True)
        df.columns = df.columns.str.replace(' ', '') # 移除欄位名稱中的空格

        # 【修改】在欄位對應中加入 "請假"
        column_mapping = {
            '人員ID': 'hr_code', '名稱': 'name_ch', '日期': 'date', '簽到': 'checkin_time',
            '簽退': 'checkout_time', '遲到': 'late_minutes', '早退': 'early_leave_minutes',
            '缺席': 'absent_minutes', '加班1': 'overtime1_minutes', '加班2': 'overtime2_minutes',
            '加班3': 'overtime3_minutes', '請假': 'leave_minutes' # 新增此行
        }
        df = df.rename(columns=column_mapping)
        
        # 【修改】將 leave_minutes 加入數字處理列表
        numeric_cols = [
            'late_minutes', 'early_leave_minutes', 'absent_minutes', 
            'overtime1_minutes', 'overtime2_minutes', 'overtime3_minutes',
            'leave_minutes' # 新增此行
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.extract(r'(\d+)').fillna(0)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            else:
                # 如果檔案中缺少某個欄位，則新增並補 0
                df[col] = 0
                
        return df, "檔案解析成功"
    except Exception as e:
        return None, f"解析出勤檔案時發生未知錯誤：{e}"
    
def match_employees_by_name(conn, attendance_df: pd.DataFrame):
    """
    V2: 新增對 "服務" 部門的特殊規則處理。
    """
    if attendance_df.empty: return attendance_df
    try:
        emp_df = q_emp.s(conn)
        if emp_df.empty:
            attendance_df['employee_id'] = None
            return attendance_df
            
        attendance_df['match_key'] = attendance_df['name_ch'].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
        emp_df['match_key'] = emp_df['name_ch'].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
        
        # 建立姓名到ID和部門的映射
        emp_id_map = dict(zip(emp_df['match_key'], emp_df['id']))
        emp_dept_map = dict(zip(emp_df['match_key'], emp_df['dept']))
        
        attendance_df['employee_id'] = attendance_df['match_key'].map(emp_id_map)
        attendance_df['dept'] = attendance_df['match_key'].map(emp_dept_map)
        
        # --- 服務部門規則 ---
        service_dept_time_limit = time(17, 30)
        service_dept_correction_time = "17:29:59" # 改為 17:29:59 更精準
        
        for index, row in attendance_df.iterrows():
            if row['dept'] == '服務' and pd.notna(row['checkout_time']):
                try:
                    checkout_t = datetime.strptime(str(row['checkout_time']), '%H:%M:%S').time()
                    if checkout_t > service_dept_time_limit:
                        attendance_df.loc[index, 'checkout_time'] = service_dept_correction_time
                        # 將加班時數歸零
                        attendance_df.loc[index, 'overtime1_minutes'] = 0
                        attendance_df.loc[index, 'overtime2_minutes'] = 0
                        attendance_df.loc[index, 'overtime3_minutes'] = 0
                except (ValueError, TypeError):
                    continue # 如果時間格式錯誤，跳過

        attendance_df.drop(columns=['match_key', 'dept'], inplace=True)
        return attendance_df
    except Exception as e:
        raise Exception(f"員工姓名匹配過程中發生錯誤: {e}")

def recalculate_attendance_minutes(checkin: time, checkout: time) -> dict:
    """
    根據新的簽到簽退時間，重新計算遲到、早退、加班分鐘數。
    """
    work_start, lunch_start = time(8, 0), time(12, 0)
    lunch_end, work_end = time(13, 0), time(17, 0)
    overtime_start_1, overtime_end_1 = time(17, 30), time(19, 30)
    overtime_start_2, overtime_end_2 = time(19, 30), time(23, 59)

    # 將 time 物件轉換為 timedelta 以便計算
    def to_timedelta(t):
        return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)

    checkin_td = to_timedelta(checkin)
    checkout_td = to_timedelta(checkout)

    # 計算遲到
    late_minutes = max(0, (checkin_td - to_timedelta(work_start)).total_seconds() / 60)
    
    # 計算早退
    early_leave_minutes = max(0, (to_timedelta(work_end) - checkout_td).total_seconds() / 60)

    # 計算加班
    overtime1_minutes = 0
    if checkout_td > to_timedelta(overtime_start_1):
        overtime1_minutes = ((min(checkout_td, to_timedelta(overtime_end_1)) - to_timedelta(overtime_start_1)).total_seconds() / 60)

    overtime2_minutes = 0
    if checkout_td > to_timedelta(overtime_start_2):
        overtime2_minutes = ((min(checkout_td, to_timedelta(overtime_end_2)) - to_timedelta(overtime_start_2)).total_seconds() / 60)

    return {
        "late_minutes": int(round(late_minutes)),
        "early_leave_minutes": int(round(early_leave_minutes)),
        "overtime1_minutes": int(round(overtime1_minutes)),
        "overtime2_minutes": int(round(overtime2_minutes)),
        "overtime3_minutes": 0 # 假設手動修改不考慮第三段加班
    }