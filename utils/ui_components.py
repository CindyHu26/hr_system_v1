# utils/ui_components.py
import streamlit as st
import pandas as pd
import io

# 修正 import 路徑
from db import queries_employee as q_emp

def employee_selector(conn, key_prefix="", pre_selected_ids=None):
    """
    一個可重複使用的員工選擇器元件，具備部門篩選和預選功能。
    返回選定的員工 ID 列表。
    """
    st.markdown("##### 選擇員工")
    if pre_selected_ids is None:
        pre_selected_ids = []
    
    try:
        emp_df = q_emp.get_all_employees(conn)[['id', 'name_ch', 'dept', 'title']]
        emp_df['display'] = emp_df['name_ch'] + " (" + emp_df['dept'].fillna('未分配') + " - " + emp_df['title'].fillna('無職稱') + ")"
        
        valid_depts = sorted([dept for dept in emp_df['dept'].unique() if pd.notna(dept)])
        selected_dept = st.selectbox(
            "依部門篩選", 
            options=['所有部門'] + valid_depts, 
            key=f"{key_prefix}_dept_filter"
        )

        filtered_emp_df = emp_df if selected_dept == '所有部門' else emp_df[emp_df['dept'] == selected_dept]
        
        emp_options = dict(zip(filtered_emp_df['display'], filtered_emp_df['id']))
        id_to_display_map = {v: k for k, v in emp_options.items()}
        default_selections = [id_to_display_map[emp_id] for emp_id in pre_selected_ids if emp_id in id_to_display_map]

        selected_displays = st.multiselect(
            "員工列表 (可複選)",
            options=list(emp_options.keys()),
            default=default_selections,
            key=f"{key_prefix}_multiselect"
        )
        
        return [emp_options[display] for display in selected_displays]
    except Exception as e:
        st.error(f"載入員工選擇器時發生錯誤: {e}")
        return []

# --- 【升級版通用元件】 ---
def create_batch_import_section(info_text: str, template_columns: dict, template_file_name: str, import_logic_func, conn):
    """
    產生一個標準的批次匯入 UI 區塊 (V3)。
    - 完整顯示所有錯誤訊息。
    - 將錯誤訊息放在可滾動的區塊中。
    """
    session_key = f"import_report_{template_file_name}"

    if session_key in st.session_state:
        report = st.session_state[session_key]
        st.subheader("匯入結果報告")
        st.markdown(f"""
        - **成功新增**: {report.get('inserted', 0)} 筆紀錄
        - **成功更新**: {report.get('updated', 0)} 筆紀錄
        - **失敗或跳過**: {report.get('failed', 0)} 筆紀錄
        """)

        if report.get('errors'):
            st.error("部分資料處理失敗，原因如下：")
            # [核心修改] 將錯誤訊息放在一個固定高度且可滾動的容器中
            with st.container(height=300):
                for error in report['errors']:
                    st.write(f"- 第 {error['row']} 行: {error['reason']}")
        
        if st.button("清除報告並重試", key=f"clear_btn_{template_file_name}"):
            del st.session_state[session_key]
            st.rerun()
        return

    st.info(info_text)

    df_template = pd.DataFrame(columns=template_columns.values())
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_template.to_excel(writer, index=False, sheet_name='資料範本')
    
    st.download_button(
        label=f"📥 下載 {template_file_name.split('.')[0]} 範本",
        data=output.getvalue(),
        file_name=template_file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")
    
    uploaded_file = st.file_uploader("上傳填寫好的 Excel 檔案", type=['xlsx'], key=f"uploader_{template_file_name}")

    if uploaded_file:
        if st.button("開始匯入", type="primary", key=f"import_btn_{template_file_name}"):
            with st.spinner("正在處理上傳的檔案..."):
                try:
                    report = import_logic_func(conn, uploaded_file)
                    st.session_state[session_key] = report
                    st.rerun()

                except Exception as e:
                    st.error(f"匯入過程中發生嚴重錯誤：{e}")