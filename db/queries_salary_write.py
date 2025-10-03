# db/queries_salary_write.py
"""
資料庫查詢：專門處理「寫入」薪資相關紀錄。
"""
import pandas as pd
from . import queries_insurance as q_ins

def delete_salary_drafts(conn, year: int, month: int):
    """
    刪除指定月份所有狀態為 'draft' 的薪資主紀錄。
    由於 schema 中設定了 ON DELETE CASCADE，相關的 salary_detail 也會被一併刪除。
    """
    cursor = conn.cursor()
    sql = "DELETE FROM salary WHERE year = ? AND month = ? AND status = 'draft'"
    cursor.execute(sql, (year, month))
    conn.commit()
    return cursor.rowcount

def _recalculate_and_save_salary_summaries(conn, salary_ids: list, year: int, month: int):
    """
    根據 salary_id 列表，重新計算其對應的薪資總額並更新回 salary 主表。
    V2: 新增對未加保員工的特殊處理邏輯。
    """
    if not salary_ids:
        return

    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in salary_ids)

    details_query = f"""
        SELECT sd.salary_id, si.type, sd.amount, si.name as item_name
        FROM salary_detail sd
        JOIN salary_item si ON sd.salary_item_id = si.id
        WHERE sd.salary_id IN ({placeholders})
    """
    rows = cursor.execute(details_query, salary_ids).fetchall()
    details_df = pd.DataFrame(rows, columns=[description[0] for description in cursor.description])

    emp_id_query = f"SELECT id, employee_id FROM salary WHERE id IN ({placeholders})"
    emp_id_map = {row['id']: row['employee_id'] for row in cursor.execute(emp_id_query, salary_ids).fetchall()}

    summary_updates = []
    
    if details_df.empty:
        for sid in salary_ids:
            summary_updates.append((0, 0, 0, 0, 0, sid))
    else:
        summary = details_df.groupby(['salary_id', 'type'])['amount'].sum().unstack(fill_value=0)
        
        for sid in salary_ids:
            total_payable = summary.loc[sid, 'earning'] if 'earning' in summary.columns and sid in summary.index else 0
            total_deduction = summary.loc[sid, 'deduction'] if 'deduction' in summary.columns and sid in summary.index else 0
            net_salary = total_payable + total_deduction

            employee_id = emp_id_map.get(sid)
            is_insured = q_ins.is_employee_insured_in_month(conn, employee_id, year, month) if employee_id else False
            
            if not is_insured:
                bank_transfer_amount = net_salary
                cash_amount = 0
            else:
                bank_transfer_items_df = details_df[
                    (details_df['salary_id'] == sid) &
                    (details_df['item_name'].isin(['底薪', '加班費(延長工時)', '加班費(再延長工時)', '勞保費', '健保費', '事假', '病假', '遲到', '早退']))
                ]
                bank_transfer_amount = bank_transfer_items_df['amount'].sum()
                cash_amount = net_salary - bank_transfer_amount

            summary_updates.append((
                int(round(total_payable)), int(round(total_deduction)), int(round(net_salary)),
                int(round(bank_transfer_amount)), int(round(cash_amount)),
                sid
            ))

    update_sql = """
        UPDATE salary
        SET total_payable = ?, total_deduction = ?, net_salary = ?,
            bank_transfer_amount = ?, cash_amount = ?
        WHERE id = ? AND status = 'draft'
    """
    cursor.executemany(update_sql, summary_updates)


def save_salary_draft(conn, year, month, df: pd.DataFrame):
    cursor = conn.cursor()
    emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()
    item_map = pd.read_sql("SELECT id, name FROM salary_item", conn).set_index('name')['id'].to_dict()
    
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        all_affected_salary_ids = []

        for _, row in df.iterrows():
            emp_id = emp_map.get(row['員工姓名'])
            if not emp_id: continue

            cursor.execute("""
                INSERT INTO salary (employee_id, year, month, status)
                VALUES (?, ?, ?, 'draft')
                ON CONFLICT(employee_id, year, month) DO NOTHING
            """, (emp_id, year, month))
            
            salary_id = cursor.execute("SELECT id FROM salary WHERE employee_id = ? AND year = ? AND month = ?", (emp_id, year, month)).fetchone()[0]
            all_affected_salary_ids.append(salary_id)

            pension = row.get('勞退提撥', 0); pension = 0 if pd.isna(pension) else int(pension)
            note = row.get('備註', ''); note = '' if pd.isna(note) else note
            cursor.execute("UPDATE salary SET employer_pension_contribution = ?, note = ? WHERE id = ?", (pension, note, salary_id))
            
            cursor.execute("DELETE FROM salary_detail WHERE salary_id = ?", (salary_id,))
            
            details_to_insert = []
            for k, v in row.items():
                if k in item_map and pd.notna(v) and v != 0:
                    if k == '勞健保':
                        if '勞保費' in item_map and pd.notna(row['勞保費']) and row['勞保費'] != 0:
                            details_to_insert.append((salary_id, item_map['勞保費'], int(row['勞保費'])))
                        if '健保費' in item_map and pd.notna(row['健保費']) and row['健保費'] != 0:
                            details_to_insert.append((salary_id, item_map['健保費'], int(row['健保費'])))
                    else:
                        details_to_insert.append((salary_id, item_map[k], int(v)))

            if details_to_insert:
                cursor.executemany("INSERT INTO salary_detail (salary_id, salary_item_id, amount) VALUES (?, ?, ?)", details_to_insert)
        
        if all_affected_salary_ids:
            # ▼▼▼ 核心修改：將 year 和 month 傳遞給函式 ▼▼▼
            _recalculate_and_save_salary_summaries(conn, list(set(all_affected_salary_ids)), year, month)

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

def finalize_salary_records(conn, year, month, df: pd.DataFrame):
    cursor = conn.cursor()
    emp_map = pd.read_sql("SELECT id, name_ch FROM employee", conn).set_index('name_ch')['id'].to_dict()

    for _, row in df.iterrows():
        emp_id = emp_map.get(row['員工姓名'])
        if not emp_id: continue

        params = {
            'total_payable': int(row.get('應付總額', 0)), 'total_deduction': int(row.get('應扣總額', 0)),
            'net_salary': int(row.get('實支金額', 0)), 'bank_transfer_amount': int(row.get('匯入銀行', 0)),
            'cash_amount': int(row.get('現金', 0)), 'status': 'final',
            'employer_pension_contribution': int(row.get('勞退提撥', 0)),
            'note': str(row.get('備註', '')) if pd.notna(row.get('備註')) else '',
            'employee_id': emp_id, 'year': year, 'month': month
        }

        cursor.execute("""
            UPDATE salary SET
            total_payable = :total_payable, total_deduction = :total_deduction,
            net_salary = :net_salary, bank_transfer_amount = :bank_transfer_amount,
            cash_amount = :cash_amount, status = :status,
            employer_pension_contribution = :employer_pension_contribution,
            note = :note
            WHERE employee_id = :employee_id AND year = :year AND month = :month
        """, params)

    conn.commit()

def revert_salary_to_draft(conn, year, month, employee_ids: list):
    if not employee_ids: return 0
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in employee_ids)
    sql = f"UPDATE salary SET status = 'draft' WHERE year = ? AND month = ? AND employee_id IN ({placeholders}) AND status = 'final'"
    params = [year, month] + employee_ids
    cursor.execute(sql, params)
    conn.commit()
    return cursor.rowcount

def batch_upsert_salary_details(conn, data_to_upsert: list):
    if not data_to_upsert: return 0
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN TRANSACTION")
        
        sql = """
            INSERT INTO salary_detail (salary_id, salary_item_id, amount) VALUES (?, ?, ?)
            ON CONFLICT(salary_id, salary_item_id) DO UPDATE SET amount = excluded.amount;
        """
        cursor.executemany(sql, data_to_upsert)
        
        affected_salary_ids = list(set([item[0] for item in data_to_upsert]))
        
        if affected_salary_ids:
            first_salary_id = affected_salary_ids[0]
            year_month_query = "SELECT year, month FROM salary WHERE id = ? LIMIT 1"
            res = cursor.execute(year_month_query, (first_salary_id,)).fetchone()
            if res:
                _recalculate_and_save_salary_summaries(conn, affected_salary_ids, res['year'], res['month'])
        
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback(); raise e