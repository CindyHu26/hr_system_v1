# services/employee_logic.py
import pandas as pd
from db import queries_employee as q_emp

# 反向的國籍對應，用於將中文轉為代碼
NATIONALITY_MAP_REVERSE = {'台灣': 'TW', '泰國': 'TH', '印尼': 'ID', '越南': 'VN', '菲律賓': 'PH'}

def batch_import_employees(conn, uploaded_file):
    """
    處理上傳的員工資料 Excel，進行驗證並呼叫資料庫函式進行儲存。
    """
    try:
        df = pd.read_excel(uploaded_file)
        
        # 為了比對，將欄位名稱與 template 中的 key 對應起來
        column_rename_map = {
            '姓名*': 'name_ch', '身分證號*': 'id_no', '員工編號*': 'hr_code',
            '到職日(YYYY-MM-DD)': 'entry_date', '性別(男/女)': 'gender',
            '生日(YYYY-MM-DD)': 'birth_date', '國籍(台灣/泰國...)': 'nationality',
            '首次抵台日(YYYY-MM-DD)': 'arrival_date', '電話': 'phone', '地址': 'address',
            '部門': 'dept', '職稱': 'title', '離職日(YYYY-MM-DD)': 'resign_date',
            '銀行帳號': 'bank_account', '備註': 'note'
        }
        df.rename(columns=column_rename_map, inplace=True)

        # 資料清洗與驗證
        records_to_process = []
        errors = []
        for index, row in df.iterrows():
            # 檢查必填欄位
            if pd.isna(row.get('name_ch')) or pd.isna(row.get('id_no')) or pd.isna(row.get('hr_code')):
                errors.append({'row': index + 2, 'reason': '姓名、身分證號或員工編號為空，已跳過此行。'})
                continue
            
            # 轉換國籍
            if pd.notna(row.get('nationality')):
                row['nationality'] = NATIONALITY_MAP_REVERSE.get(row['nationality'], 'TW')
            
            # 處理日期格式
            for date_col in ['entry_date', 'birth_date', 'arrival_date', 'resign_date']:
                if pd.notna(row.get(date_col)):
                    try:
                        # pd.to_datetime 可以彈性解析多種日期格式
                        row[date_col] = pd.to_datetime(row[date_col]).strftime('%Y-%m-%d')
                    except ValueError:
                        errors.append({'row': index + 2, 'reason': f"日期欄位 {date_col} 格式錯誤，已將其設為空值。"})
                        row[date_col] = None
            
            # 將處理好的 row 加入待處理列表
            records_to_process.append(row.to_dict())
            
        # 如果沒有可處理的資料，就直接返回
        if not records_to_process:
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': errors}

        # 將 list of dicts 轉回 DataFrame，準備傳入資料庫
        clean_df = pd.DataFrame(records_to_process)
        
        # 呼叫資料庫函式執行批次操作
        db_report = q_emp.batch_add_or_update_employees(conn, clean_df)
        
        # 組合最終報告
        final_report = {
            'inserted': db_report.get('inserted', 0),
            'updated': db_report.get('updated', 0),
            'failed': len(df) - db_report.get('processed', 0),
            'errors': errors + db_report.get('errors', [])
        }
        return final_report

    except Exception as e:
        # 如果是讀取或解析 Excel 階段就出錯
        raise Exception(f"處理 Excel 檔案時發生錯誤：{e}")