# services/salary_logic.py
import pandas as pd
import config
from db import queries_salary_records as q_records
from db import queries_salary_components as q_comp
from db import queries_attendance as q_att
from db import queries_insurance as q_ins
from services import overtime_logic

def calculate_salary_df(conn, year, month):
    """
    薪資試算引擎：根據各項資料計算全新的薪資草稿。
    """
    # ... (此函式內容不變，只是將導入的模組改為拆分後的模組)
    pass

# --- NEW: 薪資單批次修改 ---
def process_batch_salary_update_excel(conn, year: int, month: int, uploaded_file):
    """
    處理從 Excel 上傳的薪資單批次修改。
    """
    report = {"success": 0, "skipped_emp": [], "skipped_item": [], "no_salary_record": []}
    
    try:
        df = pd.read_excel(uploaded_file)
        if '員工姓名' not in df.columns:
            raise ValueError("Excel 檔案中缺少 '員工姓名' 欄位。")

        # 獲取所有必要的映射表
        emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
        item_map_df = pd.read_sql("SELECT id, name, type FROM salary_item", conn)
        item_map = {row['name']: {'id': row['id'], 'type': row['type']} for _, row in item_map_df.iterrows()}
        
        # 獲取當月所有薪資主紀錄的 ID
        salary_main_df = pd.read_sql("SELECT id, employee_id FROM salary WHERE year = ? AND month = ?", conn, params=(year, month))
        salary_id_map = salary_main_df.set_index('employee_id')['id'].to_dict()

        data_to_upsert = []

        for _, row in df.iterrows():
            emp_name = row.get('員工姓名')
            if pd.isna(emp_name): continue

            emp_id = emp_map.get(emp_name)
            if not emp_id:
                report["skipped_emp"].append(emp_name)
                continue

            salary_id = salary_id_map.get(emp_id)
            if not salary_id:
                report["no_salary_record"].append(emp_name)
                continue

            for item_name, amount in row.items():
                if item_name == '員工姓名' or pd.isna(amount): continue
                
                item_info = item_map.get(item_name)
                if not item_info:
                    report["skipped_item"].append(item_name)
                    continue

                # 根據項目類型決定金額正負號
                final_amount = -abs(float(amount)) if item_info['type'] == 'deduction' else abs(float(amount))
                
                # 將準備好的資料加入列表
                data_to_upsert.append((salary_id, item_info['id'], int(final_amount)))

        # 批次執行資料庫操作
        if data_to_upsert:
            report["success"] = q_records.batch_upsert_salary_details(conn, data_to_upsert)
            
        # 清理回報訊息
        report["skipped_emp"] = list(set(report["skipped_emp"]))
        report["skipped_item"] = list(set(report["skipped_item"]))
        return report

    except Exception as e:
        raise e