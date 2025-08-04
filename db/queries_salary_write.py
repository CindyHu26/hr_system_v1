# db/queries_salary_write.py
"""
資料庫查詢：專門處理「寫入」薪資相關紀錄。
"""
import pandas as pd

def _recalculate_and_save_salary_summaries(conn, salary_ids: list):
    """
    【V3 - 修正版】
    根據 salary_id 列表，重新計算其對應的薪資總額並更新回 salary 主表。
    此版本確保在同一個交易中，能正確讀取到剛更新的明細。
    """
    if not salary_ids:
        return

    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in salary_ids)

    # 直接使用 cursor 執行查詢，確保在同一個交易中
    details_query = f"""
        SELECT sd.salary_id, si.type, sd.amount, si.name as item_name
        FROM salary_detail sd
        JOIN salary_item si ON sd.salary_item_id = si.id
        WHERE sd.salary_id IN ({placeholders})
    """
    rows = cursor.execute(details_query, salary_ids).fetchall()
    
    # 手動將查詢結果轉為 DataFrame
    details_df = pd.DataFrame(rows, columns=[description[0] for description in cursor.description])

    if details_df.empty:
        # 如果一個員工的所有薪資項目都被刪除，總額應歸零
        summary_updates = [(0, 0, 0, 0, 0, sid) for sid in salary_ids]
    else:
        # 使用 DataFrame 進行計算
        summary = details_df.groupby(['salary_id', 'type'])['amount'].sum().unstack(fill_value=0)
        summary_updates = []
        for sid in salary_ids:
            total_payable = summary.loc[sid, 'earning'] if 'earning' in summary.columns and sid in summary.index else 0
            total_deduction = summary.loc[sid, 'deduction'] if 'deduction' in summary.columns and sid in summary.index else 0
            net_salary = total_payable + total_deduction

            # 重新計算銀行匯款與現金
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
        for _, row in df.iterrows():
            emp_id = emp_map.get(row['員工姓名'])
            if not emp_id: continue

            # 統一處理 NaN 和 None 為 0 或空字串
            pension = row.get('勞退提撥', 0); pension = 0 if pd.isna(pension) else int(pension)
            note = row.get('備註', ''); note = '' if pd.isna(note) else note
            payable = row.get('應付總額', 0); payable = 0 if pd.isna(payable) else int(payable)
            deduction = row.get('應扣總額', 0); deduction = 0 if pd.isna(deduction) else int(deduction)
            net = row.get('實支金額', 0); net = 0 if pd.isna(net) else int(net)
            bank = row.get('匯入銀行', 0); bank = 0 if pd.isna(bank) else int(bank)
            cash = row.get('現金', 0); cash = 0 if pd.isna(cash) else int(cash)


            cursor.execute("""
                INSERT INTO salary (employee_id, year, month, status, employer_pension_contribution, note, total_payable, total_deduction, net_salary, bank_transfer_amount, cash_amount)
                VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(employee_id, year, month)
                DO UPDATE SET status = 'draft', employer_pension_contribution = excluded.employer_pension_contribution, note = excluded.note,
                               total_payable = excluded.total_payable, total_deduction = excluded.total_deduction, net_salary = excluded.net_salary,
                               bank_transfer_amount = excluded.bank_transfer_amount, cash_amount = excluded.cash_amount
                WHERE status != 'final'
            """, (emp_id, year, month, pension, note, payable, deduction, net, bank, cash))

            salary_id_result = cursor.execute("SELECT id FROM salary WHERE employee_id = ? AND year = ? AND month = ?", (emp_id, year, month)).fetchone()
            if not salary_id_result: continue
            salary_id = salary_id_result[0]
            
            cursor.execute("DELETE FROM salary_detail WHERE salary_id = ?", (salary_id,))
            
            details_to_insert = []
            for k, v in row.items():
                if k in item_map and pd.notna(v) and v != 0:
                    details_to_insert.append((salary_id, item_map[k], int(v)))

            if details_to_insert:
                cursor.executemany("INSERT INTO salary_detail (salary_id, salary_item_id, amount) VALUES (?, ?, ?)", details_to_insert)
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
        _recalculate_and_save_salary_summaries(conn, affected_salary_ids)
        
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback(); raise e

def update_salary_preview_data(conn, year: int, month: int, df_to_update: pd.DataFrame):
    if df_to_update.empty: return 0
    cursor = conn.cursor()
    salary_id_map = pd.read_sql("SELECT id, employee_id FROM salary WHERE year = ? AND month = ?", conn, params=(year, month)).set_index('employee_id')['id'].to_dict()
    item_map = pd.read_sql("SELECT id, name FROM salary_item", conn).set_index('name')['id'].to_dict()
    base_salary_id, labor_fee_id, health_fee_id = item_map.get('底薪'), item_map.get('勞保費'), item_map.get('健保費')
    updates_for_details, updates_for_pension = [], []
    for _, row in df_to_update.iterrows():
        emp_id = row['employee_id']
        salary_id = salary_id_map.get(emp_id)
        if not salary_id: continue
        if base_salary_id: updates_for_details.append((row['底薪'], salary_id, base_salary_id))
        if labor_fee_id: updates_for_details.append((row['勞保費'], salary_id, labor_fee_id))
        if health_fee_id: updates_for_details.append((row['健保費'], salary_id, health_fee_id))
        updates_for_pension.append((row['勞退提撥'], salary_id))
    try:
        cursor.execute("BEGIN TRANSACTION")
        detail_sql = """
            INSERT INTO salary_detail (amount, salary_id, salary_item_id) VALUES (?, ?, ?)
            ON CONFLICT(salary_id, salary_item_id) DO UPDATE SET amount = excluded.amount;
        """
        cursor.executemany(detail_sql, updates_for_details)
        pension_sql = "UPDATE salary SET employer_pension_contribution = ? WHERE id = ?"
        cursor.executemany(pension_sql, updates_for_pension)
        
        affected_salary_ids = list(set(salary_id_map.values()))
        _recalculate_and_save_salary_summaries(conn, affected_salary_ids)
        
        conn.commit()
        return len(df_to_update)
    except Exception as e:
        conn.rollback(); raise e