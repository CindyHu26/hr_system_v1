# services/salary_base_logic.py
import pandas as pd
import re
from db import queries_salary_base as q_base
from db import queries_insurance as q_ins

def batch_import_salary_base(conn, uploaded_file):
    """
    處理上傳的員工薪資基準 Excel，進行驗證並呼叫資料庫函式進行儲存。
    V5: 強化初始欄位檢查與錯誤回報機制。
    """
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        df.columns = df.columns.str.strip()
        df['original_index'] = df.index + 2
        
        # --- [核心修改] 步驟 1: 立即檢查必要欄位是否存在 ---
        expected_cols = {
            '員工姓名*': 'name_ch', 
            '底薪*': 'base_salary',
            '健保眷屬數*': 'dependents', 
            '生效日*(YYYY-MM-DD)': 'start_date'
        }
        
        errors = []
        missing_cols = [col for col in expected_cols.keys() if col not in df.columns]
        if missing_cols:
            reason = f"Excel 檔案缺少必要的欄位，請檢查範本是否正確: {', '.join(missing_cols)}"
            # 如果連基本欄位都沒有，直接返回錯誤，不繼續執行
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': [{'row': 'N/A', 'reason': reason}]}

        # --- 步驟 2: 重新命名欄位 ---
        column_rename_map = {
            '員工姓名*': 'name_ch', '底薪*': 'base_salary',
            '健保眷屬數*': 'dependents', '生效日*(YYYY-MM-DD)': 'start_date',
            '結束日(YYYY-MM-DD)': 'end_date', '備註': 'note'
        }
        df.rename(columns=column_rename_map, inplace=True)

        # --- 步驟 3: 建立姓名映射表 ---
        emp_df_db = pd.read_sql("SELECT name_ch, id FROM employee", conn)
        emp_df_db['clean_name'] = emp_df_db['name_ch'].astype(str).str.replace(r'\s+', '', regex=True)
        emp_map = emp_df_db.set_index('clean_name')['id'].to_dict()

        # --- 步驟 4: 逐行驗證，收集所有錯誤 ---
        valid_rows = []
        for _, row in df.iterrows():
            # 檢查必填欄位是否有值
            if pd.isna(row['name_ch']) or pd.isna(row['base_salary']) or pd.isna(row['dependents']) or pd.isna(row['start_date']):
                errors.append({'row': row['original_index'], 'reason': '姓名、底薪、眷屬數或生效日等必填欄位為空。'})
                continue

            # 驗證日期格式
            start_date = pd.to_datetime(row['start_date'], errors='coerce')
            if pd.isna(start_date):
                errors.append({'row': row['original_index'], 'reason': f"生效日 '{row['start_date']}' 格式無法辨識。"})
                continue

            # 驗證姓名是否存在
            clean_name_excel = re.sub(r'\s+', '', str(row['name_ch']))
            emp_id = emp_map.get(clean_name_excel)
            if not emp_id:
                errors.append({'row': row['original_index'], 'reason': f"在資料庫中找不到員工姓名 '{row['name_ch']}'。"})
                continue
            
            # 如果所有驗證都通過，才加入到準備處理的列表中
            valid_rows.append(row)

        # --- 步驟 5: 處理驗證通過的資料 ---
        if not valid_rows:
            return {'inserted': 0, 'updated': 0, 'failed': len(df), 'errors': errors}

        df_to_process = pd.DataFrame(valid_rows).copy()
        
        df_to_process['start_date'] = pd.to_datetime(df_to_process['start_date']).dt.strftime('%Y-%m-%d')
        if 'end_date' in df_to_process.columns:
            df_to_process['end_date'] = pd.to_datetime(df_to_process['end_date'], errors='coerce').apply(lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else None)
        
        df_to_process['insurance_salary'] = df_to_process['base_salary'].apply(lambda x: q_ins.get_insurance_salary_level(conn, x))

        # --- 步驟 6: 執行資料庫操作 ---
        db_report = q_base.batch_add_or_update_salary_base_history(conn, df_to_process)
        
        # --- 步驟 7: 彙總最終報告 ---
        final_report = {
            'inserted': db_report.get('inserted', 0),
            'updated': db_report.get('updated', 0),
            'failed': len(df) - len(valid_rows),
            'errors': errors + db_report.get('errors', [])
        }
        final_report['failed'] += db_report.get('failed', 0)
        
        return final_report
        
    except Exception as e:
        # 捕獲最外層的任何未知錯誤
        return {'inserted': 0, 'updated': 0, 'failed': df.shape[0] if 'df' in locals() else 0, 'errors': [{'row': 'N/A', 'reason': f'處理 Excel 檔案時發生嚴重錯誤: {e}'}]}