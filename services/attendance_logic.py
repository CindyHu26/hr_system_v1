# services/attendance_logic.py
import pandas as pd
import io
import re
import warnings
from db import queries_employee as q_emp

def read_attendance_file(file):
    """
    從上傳的類 Excel 檔案中讀取並解析出勤資料。
    此函式源自舊版 utils.py，針對新架構進行了微調。
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

        column_mapping = {
            '人員ID': 'hr_code', '名稱': 'name_ch', '日期': 'date', '簽到': 'checkin_time',
            '簽退': 'checkout_time', '遲到': 'late_minutes', '早退': 'early_leave_minutes',
            '缺席': 'absent_minutes', '加班1': 'overtime1_minutes', '加班2': 'overtime2_minutes',
            '加班3': 'overtime3_minutes'
        }
        df = df.rename(columns=column_mapping)
        
        # 將時間相關的分鐘數欄位轉換為數字，處理無資料或格式錯誤的情況
        numeric_cols = ['late_minutes', 'early_leave_minutes', 'absent_minutes', 'overtime1_minutes', 'overtime2_minutes', 'overtime3_minutes']
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
    使用「姓名」作為唯一匹配鍵，為出勤紀錄 DataFrame 加上 employee_id。
    此函式同樣源自舊版，並改為呼叫新的查詢函式。
    """
    if attendance_df.empty:
        return attendance_df

    try:
        # 從資料庫獲取所有員工資料用於匹配
        emp_df = q_emp.get_all_employees(conn)
        if emp_df.empty:
            # 如果資料庫中沒有員工，則無法進行任何匹配
            attendance_df['employee_id'] = None
            return attendance_df
            
        # 建立用於匹配的「淨化姓名鍵」，移除所有全形半形空格
        # 例如："林 芯　愉" -> "林芯愉"
        attendance_df['match_key'] = attendance_df['name_ch'].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
        emp_df['match_key'] = emp_df['name_ch'].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
        
        # 建立從「淨化姓名」到「員工系統ID」的映射字典
        emp_map = dict(zip(emp_df['match_key'], emp_df['id']))
        
        # 進行匹配
        attendance_df['employee_id'] = attendance_df['match_key'].map(emp_map)
        
        # 移除輔助欄位，保持 DataFrame 乾淨
        attendance_df.drop(columns=['match_key'], inplace=True)
        
        return attendance_df
        
    except Exception as e:
        # 如果過程中出錯，回傳原始 DataFrame 並附加錯誤訊息
        raise Exception(f"員工姓名匹配過程中發生錯誤: {e}")