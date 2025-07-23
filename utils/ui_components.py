# utils/ui_components.py
import streamlit as st
import pandas as pd
from db import queries as q

def employee_selector(conn, key_prefix="", pre_selected_ids=None):
    """
    一個可重複使用的員工選擇器元件，具備部門篩選和預選功能。
    返回選定的員工 ID 列表。
    """
    st.markdown("##### 選擇員工")
    if pre_selected_ids is None:
        pre_selected_ids = []
    
    try:
        emp_df = q.get_all_employees(conn)[['id', 'name_ch', 'dept', 'title']]
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
