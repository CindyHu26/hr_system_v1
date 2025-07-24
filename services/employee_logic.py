# services/employee_logic.py
import pandas as pd
from db import queries_employee as q_emp

# 反向的國籍對應，用於將中文轉為代碼
NATIONALITY_MAP_REVERSE = {'台灣': 'TW', '泰國': 'TH', '印尼': 'ID', '越南': 'VN', '菲律賓': 'PH'}

def batch_import_employees(conn, uploaded_file):
    """
    處理上傳的員工資料 Excel，進行驗證並呼叫資料庫函式进行儲存 (V2)。
    - 強化日期處理與錯誤回報。
    """
    try:
        # 【修改】讀取時，將所有欄位先當作字串，避免日期自動轉換
        df = pd.read_excel(uploaded_file, dtype=str).fillna('')
        
        # ... (column_rename_map 保持不變) ...
        column_rename_map = {
            '姓名*': 'name_ch', '身分證號*': 'id_no', '員工編號*': 'hr_code',
            '到職日(YYYY-MM-DD)': 'entry_date', '性別(男/女)': 'gender',
            '生日(YYYY-MM-DD)': 'birth_date', '國籍(台灣/泰國...)': 'nationality',
            '首次抵台日(YYYY-MM-DD)': 'arrival_date', '電話': 'phone', '地址': 'address',
            '部門': 'dept', '職稱': 'title', '離職日(YYYY-MM-DD)': 'resign_date',
            '銀行帳號': 'bank_account', '備註': 'note'
        }
        df.rename(columns=column_rename_map, inplace=True)

        records_to_process = []
        errors = []
        for index, row in df.iterrows():
            # 檢查必填欄位 (姓名、身分證、員工編號)
            if not row.get('name_ch') or not row.get('id_no') or not row.get('hr_code'):
                errors.append({'row': index + 2, 'reason': '姓名、身分證號或員工編號為空，已跳過此行。'})
                continue
            
            # 轉換國籍
            if row.get('nationality'):
                row['nationality'] = NATIONALITY_MAP_REVERSE.get(row['nationality'], 'TW')
            
            # 【強化】處理日期格式
            for date_col in ['entry_date', 'birth_date', 'arrival_date', 'resign_date']:
                date_val = row.get(date_col)
                if date_val: # 只有在儲存格不為空時才處理
                    try:
                        # pd.to_datetime 可以彈性解析多種格式，包含 Excel 的數字格式
                        # errors='coerce' 會在轉換失敗時回傳 NaT (Not a Time)
                        parsed_date = pd.to_datetime(date_val, errors='coerce')
                        if pd.isna(parsed_date):
                            # 如果轉換失敗，拋出一個我們自訂的錯誤
                            raise ValueError
                        row[date_col] = parsed_date.strftime('%Y-%m-%d')
                    except (ValueError, TypeError):
                        # 捕獲錯誤，並提供更詳細的提示
                        errors.append({'row': index + 2, 'reason': f"日期欄位 [{date_col}] 的內容 '{date_val}' 格式無法辨識，已設為空值。"})
                        row[date_col] = None
            
            records_to_process.append(row.to_dict())
            
        if not records_to_process:
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': errors}

        clean_df = pd.DataFrame(records_to_process)
        
        db_report = q_emp.batch_add_or_update_employees(conn, clean_df)
        
        final_report = {
            'inserted': db_report.get('inserted', 0),
            'updated': db_report.get('updated', 0),
            'failed': len(df) - db_report.get('processed', 0),
            'errors': errors + db_report.get('errors', [])
        }
        return final_report

    except Exception as e:
        raise Exception(f"處理 Excel 檔案時發生錯誤：{e}")