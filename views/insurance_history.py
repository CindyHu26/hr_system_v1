# views/insurance_history.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from db import queries_insurance as q_ins
from db import queries_employee as q_emp
from db import queries_common as q_common
from utils.ui_components import create_batch_import_section
from services import insurance_logic as logic_ins

INSURANCE_TEMPLATE_COLUMNS = {
    'name_ch': '員工姓名*',
    'company_name': '加保單位名稱*',
    'start_date': '加保日期*(YYYY-MM-DD)',
    'end_date': '退保日期(YYYY-MM-DD)',
    'note': '備註'
}

def show_page(conn):
    st.header("📄 員工加保管理")
    
    try:
        history_df = q_ins.get_all_insurance_history(conn)
        history_df['start_date'] = pd.to_datetime(history_df['start_date'], errors='coerce').dt.date
        history_df['end_date'] = pd.to_datetime(history_df['end_date'], errors='coerce').dt.date

        st.info("您可以直接在下表中修改加/退保日期與備註，完成後點擊下方的「儲存變更」按鈕。")
        history_df.set_index('id', inplace=True)
        
        if 'original_insurance_df' not in st.session_state:
            st.session_state.original_insurance_df = history_df.copy()

        COLUMN_MAP = {
            'name_ch': '員工姓名', 'company_name': '加保單位',
            'start_date': '加保日期', 'end_date': '退保日期', 'note': '備註'
        }
        
        edited_df = st.data_editor(
            history_df.rename(columns=COLUMN_MAP),
            use_container_width=True,
            column_config={
                "加保日期": st.column_config.DateColumn("加保日期", format="YYYY-MM-DD"),
                "退保日期": st.column_config.DateColumn("退保日期", format="YYYY-MM-DD"),
            },
            disabled=["員工姓名", "加保單位"]
        )
        
        if st.button("💾 儲存加保資料變更", type="primary"):
            original_df_renamed = st.session_state.original_insurance_df.rename(columns=COLUMN_MAP)
            changed_rows = edited_df[edited_df.ne(original_df_renamed)].dropna(how='all')

            if changed_rows.empty:
                st.info("沒有偵測到任何變更。")
            else:
                updates_count = 0
                with st.spinner("正在儲存變更..."):
                    for record_id, row in changed_rows.iterrows():
                        update_data = row.dropna().to_dict()
                        update_data_reverted = {
                            (k for k, v in COLUMN_MAP.items() if v == col_name).__next__(): val 
                            for col_name, val in update_data.items()
                        }

                        # 將 Timestamp 轉換為字串
                        for key, value in update_data_reverted.items():
                            if isinstance(value, (pd.Timestamp, date)):
                                update_data_reverted[key] = value.strftime('%Y-%m-%d')
                        
                        q_common.update_record(conn, 'employee_company_history', record_id, update_data_reverted)
                        updates_count += 1

                st.success(f"成功更新了 {updates_count} 筆加保紀錄！")
                del st.session_state.original_insurance_df
                st.rerun()

    except Exception as e:
        st.error(f"讀取加保歷史時發生錯誤: {e}")
        return
        
    st.write("---")
    st.subheader("🔍 依公司查詢當月在保名單")
    
    all_companies = q_emp.get_all_companies(conn)
    if not all_companies.empty:
        comp_options = dict(zip(all_companies['name'], all_companies['id']))
        
        c1, c2, c3 = st.columns(3)
        
        selected_comp_name = c1.selectbox(
            "選擇公司",
            options=list(comp_options.keys()),
            key="comp_filter_selectbox"
        )
        
        today = datetime.now()
        last_month = today - relativedelta(months=1)
        
        year = c2.number_input("選擇年份", min_value=2000, max_value=today.year + 5, value=last_month.year, key="ins_count_year")
        month = c3.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="ins_count_month")

        if st.button("查詢在保員工", type="primary", key="query_insured_btn"):
            if selected_comp_name:
                company_id = comp_options[selected_comp_name]
                with st.spinner(f"正在查詢 {selected_comp_name} 在 {year}年{month}月 的在保員工..."):
                    insured_employees_df = q_ins.get_insured_employees_by_company_and_month(conn, company_id, year, month)
                    st.session_state['insured_employees_df'] = insured_employees_df
                    st.session_state['insured_employees_count'] = len(insured_employees_df)
                    st.session_state['last_query_company_info'] = f"{selected_comp_name} ({year}年{month}月)"
            else:
                st.warning("請選擇一間公司進行查詢。")

        if 'insured_employees_df' in st.session_state:
            count = st.session_state['insured_employees_count']
            info = st.session_state['last_query_company_info']
            st.success(f"查詢 {info} 完成，共有 **{count}** 名員工在保。")
            st.dataframe(st.session_state['insured_employees_df'], use_container_width=True)

    else:
        st.info("系統中尚無公司資料可供查詢。")

    st.subheader("資料操作")
    tab1, tab2 = st.tabs([" ✨ 新增紀錄", "🚀 批次匯入 (Excel)"])

    with tab1:
        st.markdown("#### 新增一筆加保紀錄")
        employees = q_emp.get_all_employees(conn)
        companies = q_emp.get_all_companies(conn)
        emp_options = {f"{name} ({code})": eid for eid, name, code in zip(employees['id'], employees['name_ch'], employees['hr_code'])}
        comp_options = {name: cid for cid, name in zip(companies['id'], companies['name'])}

        with st.form("add_insurance_form", clear_on_submit=True):
            selected_emp_key = st.selectbox("選擇員工*", options=emp_options.keys())
            selected_comp_key = st.selectbox("選擇加保單位*", options=comp_options.keys())
            
            min_date = date(2000, 1, 1)
            
            start_date = st.date_input(
                "加保日期*",
                value=datetime.now(),
                min_value=min_date,
                max_value=date.today().replace(year=date.today().year + 5)
            )
            end_date = st.date_input(
                "退保日期 (可留空)",
                value=None,
                min_value=min_date
            )
            
            note = st.text_input("備註")

            if st.form_submit_button("確認新增"):
                new_data = {
                    'employee_id': emp_options[selected_emp_key],
                    'company_id': comp_options[selected_comp_key],
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d') if end_date else None,
                    'note': note
                }
                q_common.add_record(conn, 'employee_company_history', new_data)
                st.success("成功新增加保紀錄！")
                st.rerun()
    with tab2:
        create_batch_import_section(
            info_text="說明：系統會以「員工姓名」、「加保單位名稱」和「加保日期」為唯一鍵，若紀錄已存在則會更新，否則新增。",
            template_columns=INSURANCE_TEMPLATE_COLUMNS,
            template_file_name="insurance_history_template.xlsx",
            import_logic_func=logic_ins.batch_import_insurance_history,
            conn=conn
        )