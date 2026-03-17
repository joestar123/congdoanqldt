import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import numpy as np
import time

# ================= 1. CẤU HÌNH & KẾT NỐI (TỐI ƯU QUOTA) =================
SHEET_NAME = "diem_cong_doan" 

@st.cache_resource
def get_gspread_client():
    creds_info = st.secrets["gcp_service_account"].to_dict()
    if "private_key" in creds_info:
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(creds)

client = get_gspread_client()
sh = client.open(SHEET_NAME)

@st.cache_data(ttl=300)
def load_data(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        if "Ngày diễn ra" in df.columns:
            df["Ngày diễn ra"] = pd.to_datetime(df["Ngày diễn ra"], dayfirst=True, errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()

def save_data(df, sheet_name):
    try:
        df_to_save = df.copy()
        if "Ngày diễn ra" in df_to_save.columns:
            df_to_save["Ngày diễn ra"] = pd.to_datetime(df_to_save["Ngày diễn ra"]).dt.strftime('%d/%m/%Y')

        for col in df_to_save.select_dtypes(include=['datetime', 'datetimetz']).columns:
            df_to_save[col] = df_to_save[col].astype(str)

        df_to_save = df_to_save.replace([np.inf, -np.inf], np.nan).fillna("")

        def force_json_safe(val):
            if isinstance(val, (np.integer, np.int64)): return int(val)
            if isinstance(val, (np.floating, np.float64)): return float(val)
            if isinstance(val, (bool, np.bool_)): return bool(val)
            if pd.isna(val) or str(val) == "NaT": return ""
            return str(val)

        data_list = [df_to_save.columns.values.tolist()]
        for row in df_to_save.values.tolist():
            data_list.append([force_json_safe(v) for v in row])

        worksheet = sh.worksheet(sheet_name)
        worksheet.clear() 
        worksheet.update(data_list)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"❌ Lỗi khi lưu: {e}")

# ================= 2. GIAO DIỆN & ĐIỀU HƯỚNG =================
st.set_page_config(page_title="Quản lý Công Đoàn", layout="wide")

with st.sidebar:
    st.title("📌 Menu Chính")
    menu = st.radio(
        "Chọn chức năng:",
        ["🏆 Bảng Xếp Hạng", "📅 Quản lý Sự Kiện", "✅ Điểm Danh"],
        index=0 
    )
    
    st.divider()
    if st.button("🔄 Tải lại dữ liệu"):
        st.cache_data.clear()
        st.rerun()

    st.header("🔐 Quyền Admin")
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False

    if not st.session_state.is_admin:
        admin_pass = st.text_input("Mật khẩu:", type="password")
        if st.button("Đăng nhập"):
            if admin_pass == st.secrets["admin_password"]:
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Sai mật khẩu!")
    else:
        st.success("✅ Đang ở chế độ Admin")
        if st.button("Đăng xuất"):
            st.session_state.is_admin = False
            st.rerun()

# Tải dữ liệu
df_thanhvien = load_data("Thành viên")
df_sukien = load_data("Sự kiện")
df_nhatky = load_data("Nhật ký")

st.title(f"🎯 {menu}")

# ================= HIỂN THỊ NỘI DUNG THEO MENU =================

if menu == "🏆 Bảng Xếp Hạng":
    # Kiểm tra xem có cột ID Sự kiện chưa để tránh lỗi
    if not df_nhatky.empty and not df_sukien.empty and "ID Sự kiện" in df_sukien.columns and "ID Sự kiện" in df_nhatky.columns:
        # Merge dựa trên ID Sự kiện thay vì Tên sự kiện
        df_merged = pd.merge(df_nhatky, df_sukien[["ID Sự kiện", "Tên sự kiện", "Ngày diễn ra"]], on="ID Sự kiện", how="left")
        df_merged['Ngày diễn ra'] = pd.to_datetime(df_merged['Ngày diễn ra'])
        df_merged = df_merged.dropna(subset=['Ngày diễn ra'])
        
        df_merged['Năm'] = df_merged['Ngày diễn ra'].dt.year.astype(int)
        df_merged['Tháng'] = df_merged['Ngày diễn ra'].dt.month.astype(int)
        
        view_type = st.radio("Chế độ lọc:", ["Tất cả", "Năm", "Tháng"], horizontal=True)
        filtered_df = df_merged.copy()
        
        if view_type != "Tất cả":
            years = sorted(df_merged['Năm'].unique(), reverse=True)
            if years:
                y = st.selectbox("Năm:", years)
                filtered_df = df_merged[df_merged['Năm'] == y]
                if view_type == "Tháng":
                    m = st.selectbox("Tháng:", list(range(1, 13)), index=datetime.now().month-1)
                    filtered_df = filtered_df[filtered_df['Tháng'] == m]

        tong_diem = filtered_df.groupby("Thành viên")["Số điểm"].sum().reset_index()
        bxh = pd.merge(df_thanhvien, tong_diem, left_on="Tên Thành viên", right_on="Thành viên", how="left")
        bxh["Số điểm"] = bxh["Số điểm"].fillna(0).astype(int)
        
        df_hien_thi = bxh[["Tên Thành viên", "Số điểm"]].sort_values("Số điểm", ascending=False).reset_index(drop=True)
        
        def highlight_top3(row):
            if row.name == 0:
                return ['background-color: #FFD700; color: black; font-weight: bold'] * len(row)
            elif row.name == 1:
                return ['background-color: #E0E0E0; color: black; font-weight: bold'] * len(row)
            elif row.name == 2:
                return ['background-color: #CD7F32; color: black; font-weight: bold'] * len(row)
            return [''] * len(row)

        df_styled = df_hien_thi.style.apply(highlight_top3, axis=1).set_properties(subset=["Số điểm"], **{"text-align": "center"})
        
        st.dataframe(df_styled, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có dữ liệu hoặc bạn chưa thêm cột 'ID Sự kiện' vào Google Sheets.")

elif menu == "📅 Quản lý Sự Kiện":
    if not df_sukien.empty:
        df_disp = df_sukien.copy()
        df_disp['Ngày diễn ra'] = df_disp['Ngày diễn ra'].dt.strftime('%d/%m/%Y')
        
        # Ẩn cột ID Sự kiện khi hiển thị cho người dùng xem cho đẹp
        cols_to_show = [col for col in df_disp.columns if col != "ID Sự kiện"]
        df_show = df_disp[cols_to_show]
        
        if "Số điểm" in df_show.columns:
            df_styled_sukien = df_show.style.set_properties(subset=["Số điểm"], **{"text-align": "center"})
            st.dataframe(df_styled_sukien, use_container_width=True, hide_index=True)
        else:
            st.dataframe(df_show, use_container_width=True, hide_index=True)
    
    if st.session_state.is_admin:
        with st.expander("➕ Thêm sự kiện mới"):
            with st.form("add_sk"):
                c1, c2 = st.columns(2)
                ten = c1.text_input("Tên sự kiện")
                diadiem = c1.text_input("Địa điểm")
                ngay = c2.date_input("Ngày")
                gio = c2.time_input("Giờ")
                diem = c2.number_input("Điểm", min_value=1, value=5)
                if st.form_submit_button("Lưu"):
                    # Tự động tạo ID Sự kiện duy nhất theo thời gian thực
                    unique_id = f"SK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    new_sk = pd.DataFrame({
                        "ID Sự kiện": [unique_id],
                        "Tên sự kiện": [ten], 
                        "Ngày diễn ra": [pd.to_datetime(ngay)], 
                        "Thời gian bắt đầu": [gio.strftime("%H:%M")], 
                        "Địa điểm": [diadiem], 
                        "Số điểm": [diem]
                    })
                    save_data(pd.concat([df_sukien, new_sk], ignore_index=True), "Sự kiện")
                    st.success("✅ Đã thêm sự kiện!")
                    time.sleep(1)
                    st.rerun()

        with st.expander("🗑️ Xóa sự kiện"):
            if not df_sukien.empty and "ID Sự kiện" in df_sukien.columns:
                # Tạo chuỗi hiển thị dễ nhìn cho Admin chọn (Tên + Ngày)
                df_sukien["HienThi"] = df_sukien["Tên sự kiện"] + " (" + df_sukien["Ngày diễn ra"].dt.strftime('%d/%m/%Y').fillna("") + ")"
                
                # Tạo dictionary để map từ Chuỗi hiển thị -> ID Sự kiện
                sk_dict = dict(zip(df_sukien["HienThi"], df_sukien["ID Sự kiện"]))
                
                sk_xoa_hien_thi = st.selectbox("Chọn sự kiện cần xóa:", list(sk_dict.keys()))
                
                if st.button("Xác nhận xóa"):
                    sk_xoa_id = sk_dict[sk_xoa_hien_thi]
                    # Xóa theo ID Sự kiện
                    save_data(df_sukien[df_sukien["ID Sự kiện"] != sk_xoa_id].drop(columns=["HienThi"], errors="ignore"), "Sự kiện")
                    if not df_nhatky.empty and "ID Sự kiện" in df_nhatky.columns:
                        save_data(df_nhatky[df_nhatky["ID Sự kiện"] != sk_xoa_id], "Nhật ký")
                    st.success("✅ Đã xóa thành công!")
                    time.sleep(1)
                    st.rerun()
            else:
                st.warning("Không có sự kiện để xóa hoặc thiếu cột ID Sự kiện.")

elif menu == "✅ Điểm Danh":
    if not df_sukien.empty and "ID Sự kiện" in df_sukien.columns:
        # Tạo chuỗi hiển thị để chọn sự kiện không bị nhầm lẫn
        df_sukien["HienThi"] = df_sukien["Tên sự kiện"] + " (" + df_sukien["Ngày diễn ra"].dt.strftime('%d/%m/%Y').fillna("") + ")"
        sk_dict = dict(zip(df_sukien["HienThi"], df_sukien["ID Sự kiện"]))
        
        sel_sk_hienthi = st.selectbox("📌 Chọn sự kiện:", list(sk_dict.keys())[::-1])
        sel_sk_id = sk_dict[sel_sk_hienthi]
        
        # Lấy thông tin sự kiện dựa trên ID
        info = df_sukien[df_sukien["ID Sự kiện"] == sel_sk_id].iloc[0]
        
        # Lấy danh sách đã điểm danh dựa trên ID
        if not df_nhatky.empty and "ID Sự kiện" in df_nhatky.columns:
            da_den = df_nhatky[df_nhatky["ID Sự kiện"] == sel_sk_id]["Thành viên"].tolist()
        else:
            da_den = []
        
        if st.session_state.is_admin:
            chon_tv = st.multiselect("✅ Thành viên tham gia:", df_thanhvien["Tên Thành viên"].tolist(), default=da_den)
            if st.button("Cập nhật"):
                # Tách riêng các lịch sử điểm danh KHÁC sự kiện đang chọn
                if not df_nhatky.empty and "ID Sự kiện" in df_nhatky.columns:
                    df_nk_other = df_nhatky[df_nhatky["ID Sự kiện"] != sel_sk_id]
                else:
                    df_nk_other = pd.DataFrame(columns=["ID Sự kiện", "Tên sự kiện", "Thành viên", "Số điểm"])
                
                # Tạo data điểm danh mới (lưu kèm ID)
                new_logs = pd.DataFrame({
                    "ID Sự kiện": [sel_sk_id] * len(chon_tv),
                    "Tên sự kiện": [info["Tên sự kiện"]] * len(chon_tv), # Vẫn lưu tên để dễ nhìn trong Google Sheet
                    "Thành viên": chon_tv, 
                    "Số điểm": [info["Số điểm"]] * len(chon_tv)
                })
                
                save_data(pd.concat([df_nk_other, new_logs], ignore_index=True), "Nhật ký")
                st.success("✅ Đã cập nhật điểm danh!")
                time.sleep(1)
                st.rerun()
        else:
            st.write(f"**Danh sách tham gia ({len(da_den)}):**", ", ".join(da_den) if da_den else "Trống.")
    else:
         st.warning("Vui lòng thêm sự kiện hoặc kiểm tra lại cấu trúc cột (cần có ID Sự kiện).")
