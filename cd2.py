import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import numpy as np

# ================= 1. CẤU HÌNH KẾT NỐI =================
SHEET_NAME = "diem_cong_doan" 

def get_gspread_client():
    creds_info = st.secrets["gcp_service_account"].to_dict()
    if "private_key" in creds_info:
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(creds)

try:
    client = get_gspread_client()
    sh = client.open(SHEET_NAME)
except Exception as e:
    st.error(f"Không thể kết nối Google Sheets: {e}")
    st.stop()

def load_data(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        # Đồng bộ định dạng ngày ngay khi load để tránh lỗi "None"
        if "Ngày diễn ra" in df.columns:
            df["Ngày diễn ra"] = pd.to_datetime(df["Ngày diễn ra"], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()

def save_data(df, sheet_name):
    try:
        df_to_save = df.copy()
        
        # 🟢 FIX: Luôn chuyển cột Ngày diễn ra về dạng chuỗi YYYY-MM-DD trước khi lưu
        if "Ngày diễn ra" in df_to_save.columns:
            df_to_save["Ngày diễn ra"] = pd.to_datetime(df_to_save["Ngày diễn ra"]).dt.strftime('%Y-%m-%d')

        # Chuyển các cột datetime khác (nếu có) sang string
        for col in df_to_save.select_dtypes(include=['datetime', 'datetimetz']).columns:
            df_to_save[col] = df_to_save[col].astype(str)

        df_to_save = df_to_save.replace([np.inf, -np.inf], np.nan).fillna("")

        def force_json_safe(val):
            if isinstance(val, (np.integer, np.int64)): return int(val)
            if isinstance(val, (np.floating, np.float64)): return float(val)
            if isinstance(val, (bool, np.bool_)): return bool(val)
            # Nếu là giá trị NaT (ngày lỗi), trả về chuỗi rỗng
            if pd.isna(val) or str(val) == "NaT": return ""
            return str(val)

        data_list = [df_to_save.columns.values.tolist()]
        for row in df_to_save.values.tolist():
            data_list.append([force_json_safe(v) for v in row])

        worksheet = sh.worksheet(sheet_name)
        worksheet.clear() 
        worksheet.update(data_list)
        
    except Exception as e:
        st.error(f"❌ Lỗi khi lưu dữ liệu vào '{sheet_name}': {e}")

# ================= 2. GIAO DIỆN & ADMIN =================
st.set_page_config(page_title="Quản lý Công Đoàn", layout="wide")
st.title("🎯 Ứng dụng Chấm Điểm Công Đoàn")

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

with st.sidebar:
    st.header("🔐 Admin")
    if not st.session_state.is_admin:
        admin_pass = st.text_input("Mật khẩu:", type="password")
        if st.button("Đăng nhập"):
            if admin_pass == st.secrets["admin_password"]:
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Sai mật khẩu!")
    else:
        if st.button("Đăng xuất"):
            st.session_state.is_admin = False
            st.rerun()

df_thanhvien = load_data("Thành viên")
df_sukien = load_data("Sự kiện")
df_nhatky = load_data("Nhật ký")

tab1, tab2, tab3 = st.tabs(["🏆 Bảng Xếp Hạng", "📅 Quản lý Sự Kiện", "✅ Điểm Danh"])

# ================= TAB 1: BẢNG XẾP HẠNG =================
with tab1:
    st.header("Bảng Xếp Hạng Điểm Tích Lũy")
    if not df_nhatky.empty and not df_sukien.empty:
        df_merged = pd.merge(df_nhatky, df_sukien[["Tên sự kiện", "Ngày diễn ra"]], on="Tên sự kiện", how="left")
        df_merged['Ngày diễn ra'] = pd.to_datetime(df_merged['Ngày diễn ra'])
        
        # Chỉ lấy các dòng có ngày hợp lệ để tính toán
        df_merged = df_merged.dropna(subset=['Ngày diễn ra'])
        
        df_merged['Năm'] = df_merged['Ngày diễn ra'].dt.year.astype(int)
        df_merged['Tháng'] = df_merged['Ngày diễn ra'].dt.month.astype(int)
        df_merged['Quý'] = df_merged['Ngày diễn ra'].dt.quarter.astype(int)

        c_f1, c_f2 = st.columns([1, 2])
        view_type = c_f1.radio("Xem theo:", ["Tất cả", "Theo Năm", "Theo Quý", "Theo Tháng"], horizontal=True)

        filtered_df = df_merged.copy()
        with c_f2:
            years = sorted(df_merged['Năm'].unique(), reverse=True)
            if view_type == "Theo Năm":
                y = st.selectbox("Chọn năm:", years)
                filtered_df = df_merged[df_merged['Năm'] == y]
            elif view_type == "Theo Quý":
                y = st.selectbox("Năm:", years, key="q_y")
                q = st.selectbox("Quý:", [1, 2, 3, 4])
                filtered_df = df_merged[(df_merged['Năm'] == y) & (df_merged['Quý'] == q)]
            elif view_type == "Theo Tháng":
                y = st.selectbox("Năm:", years, key="m_y")
                m = st.selectbox("Tháng:", list(range(1, 13)), index=datetime.now().month - 1)
                filtered_df = df_merged[(df_merged['Năm'] == y) & (df_merged['Tháng'] == m)]

        tong_diem = filtered_df.groupby("Thành viên")["Số điểm"].sum().reset_index()
        bxh = pd.merge(df_thanhvien, tong_diem, left_on="Tên Thành viên", right_on="Thành viên", how="left")
        bxh["Số điểm"] = bxh["Số điểm"].fillna(0)
        st.dataframe(bxh[["Tên Thành viên", "Số điểm"]].sort_values("Số điểm", ascending=False), use_container_width=True)
    else:
        st.info("Chưa có dữ liệu.")

# ================= TAB 2: QUẢN LÝ SỰ KIỆN =================
with tab2:
    st.header("Danh Sách Sự Kiện")
    if not df_sukien.empty:
        df_disp = df_sukien.copy()
        # Hiển thị ngày ngắn gọn trên bảng
        df_disp['Ngày diễn ra'] = df_disp['Ngày diễn ra'].dt.strftime('%Y-%m-%d')
        st.dataframe(df_disp, use_container_width=True)
    
    if st.session_state.is_admin:
        st.divider()
        st.subheader("➕ Thêm Sự Kiện")
        with st.form("add_sk", clear_on_submit=True):
            c1, c2 = st.columns(2)
            ten = c1.text_input("Tên sự kiện")
            diadiem = c1.text_input("Địa điểm")
            ngay = c2.date_input("Ngày")
            gio = c2.time_input("Giờ")
            diem = c2.number_input("Điểm", min_value=1, value=5)
            
            if st.form_submit_button("Lưu sự kiện"):
                if ten:
                    # 🟢 FIX: Tạo sự kiện mới với kiểu Datetime để đồng bộ với bảng chính
                    new_sk = pd.DataFrame({
                        "Tên sự kiện": [ten], 
                        "Ngày diễn ra": [pd.to_datetime(ngay)], 
                        "Thời gian bắt đầu": [gio.strftime("%H:%M")], 
                        "Địa điểm": [diadiem], 
                        "Số điểm": [diem]
                    })
                    df_sukien_updated = pd.concat([df_sukien, new_sk], ignore_index=True)
                    save_data(df_sukien_updated, "Sự kiện")
                    st.success("Đã thêm sự kiện!")
                    st.rerun()

        st.divider()
        st.subheader("🗑️ Xóa Sự Kiện")
        if not df_sukien.empty:
            danh_sach_sk = df_sukien["Tên sự kiện"].tolist()
            sk_xoa = st.selectbox("Chọn sự kiện để xóa:", danh_sach_sk)
            if st.button("Xác nhận xóa sự kiện", type="primary"):
                df_sukien = df_sukien[df_sukien["Tên sự kiện"] != sk_xoa]
                save_data(df_sukien, "Sự kiện")
                if not df_nhatky.empty:
                    df_nhatky = df_nhatky[df_nhatky["Tên sự kiện"] != sk_xoa]
                    save_data(df_nhatky, "Nhật ký")
                st.success(f"Đã xóa: {sk_xoa}")
                st.rerun()

# ================= TAB 3: ĐIỂM DANH =================
with tab3:
    if not df_sukien.empty:
        sk_list = df_sukien["Tên sự kiện"].tolist()[::-1]
        sel_sk = st.selectbox("📌 Chọn sự kiện:", sk_list)
        info = df_sukien[df_sukien["Tên sự kiện"] == sel_sk].iloc[0]
        da_den = df_nhatky[df_nhatky["Tên sự kiện"] == sel_sk]["Thành viên"].tolist() if not df_nhatky.empty else []
        
        if st.session_state.is_admin:
            chon_tv = st.multiselect("✅ Chọn thành viên tham gia:", df_thanhvien["Tên Thành viên"].tolist(), default=da_den)
            if st.button("Cập nhật điểm danh"):
                df_nk_new = df_nhatky[df_nhatky["Tên sự kiện"] != sel_sk] if not df_nhatky.empty else pd.DataFrame(columns=["Tên sự kiện", "Thành viên", "Số điểm"])
                if chon_tv:
                    new_logs = pd.DataFrame({
                        "Tên sự kiện": [sel_sk]*len(chon_tv), 
                        "Thành viên": chon_tv, 
                        "Số điểm": [info["Số điểm"]]*len(chon_tv)
                    })
                    df_nk_new = pd.concat([df_nk_new, new_logs], ignore_index=True)
                save_data(df_nk_new, "Nhật ký")
                st.success("Đã lưu!")
                st.rerun()
        else:
            st.write("**Thành viên đã tham gia:**", ", ".join(da_den) if da_den else "Chưa có ai.")
