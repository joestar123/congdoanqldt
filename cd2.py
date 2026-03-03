import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import numpy as np

# ================= 1. CẤU HÌNH & KẾT NỐI (TỐI ƯU QUOTA) =================
SHEET_NAME = "diem_cong_doan" 

@st.cache_resource # Lưu kết nối để không phải login lại nhiều lần
def get_gspread_client():
    creds_info = st.secrets["gcp_service_account"].to_dict()
    if "private_key" in creds_info:
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(creds)

# Khởi tạo kết nối
client = get_gspread_client()
sh = client.open(SHEET_NAME)

# Cache dữ liệu trong 5 phút để tránh lỗi Quota 429 khi có nhiều người truy cập
@st.cache_data(ttl=300) 
def load_data(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        # Tự động sửa lỗi định dạng ngày tháng khi đọc từ Sheet
        if "Ngày diễn ra" in df.columns:
            df["Ngày diễn ra"] = pd.to_datetime(df["Ngày diễn ra"], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()

def save_data(df, sheet_name):
    """Hàm lưu dữ liệu an toàn, chống lỗi JSON và làm mới Cache"""
    try:
        df_to_save = df.copy()
        
        # Thống nhất định dạng Ngày diễn ra là chuỗi YYYY-MM-DD
        if "Ngày diễn ra" in df_to_save.columns:
            df_to_save["Ngày diễn ra"] = pd.to_datetime(df_to_save["Ngày diễn ra"]).dt.strftime('%Y-%m-%d')

        # Ép kiểu các cột datetime khác sang chuỗi
        for col in df_to_save.select_dtypes(include=['datetime', 'datetimetz']).columns:
            df_to_save[col] = df_to_save[col].astype(str)

        # Xử lý các giá trị NaN/Vô cực
        df_to_save = df_to_save.replace([np.inf, -np.inf], np.nan).fillna("")

        # Hàm lọc dữ liệu JSON an toàn
        def force_json_safe(val):
            if isinstance(val, (np.integer, np.int64)): return int(val)
            if isinstance(val, (np.floating, np.float64)): return float(val)
            if isinstance(val, (bool, np.bool_)): return bool(val)
            if pd.isna(val) or str(val) == "NaT": return ""
            return str(val)

        # Chuẩn bị danh sách ghi lên Sheet
        data_list = [df_to_save.columns.values.tolist()]
        for row in df_to_save.values.tolist():
            data_list.append([force_json_safe(v) for v in row])

        # Ghi vào Google Sheets
        worksheet = sh.worksheet(sheet_name)
        worksheet.clear() 
        worksheet.update(data_list)
        
        # Xóa cache để cập nhật dữ liệu mới cho toàn bộ 13 người dùng
        st.cache_data.clear()
        
    except Exception as e:
        st.error(f"❌ Lỗi khi lưu vào '{sheet_name}': {e}")

# ================= 2. GIAO DIỆN ỨNG DỤNG =================
st.set_page_config(page_title="Quản lý Công Đoàn", layout="wide")

# Nút tải lại dữ liệu nhanh
if st.sidebar.button("🔄 Làm mới dữ liệu"):
    st.cache_data.clear()
    st.rerun()

st.title("🎯 Ứng dụng Quản lý Điểm Công Đoàn")

# Hệ thống Admin
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
        st.success("✅ Chế độ Admin")
        if st.button("Đăng xuất"):
            st.session_state.is_admin = False
            st.rerun()

# Tải dữ liệu từ Cache
df_thanhvien = load_data("Thành viên")
df_sukien = load_data("Sự kiện")
df_nhatky = load_data("Nhật ký")

tab1, tab2, tab3 = st.tabs(["🏆 Bảng Xếp Hạng", "📅 Danh Sách Sự Kiện", "✅ Điểm Danh"])

# ================= TAB 1: BẢNG XẾP HẠNG =================
with tab1:
    if not df_nhatky.empty and not df_sukien.empty:
        df_merged = pd.merge(df_nhatky, df_sukien[["Tên sự kiện", "Ngày diễn ra"]], on="Tên sự kiện", how="left")
        df_merged['Ngày diễn ra'] = pd.to_datetime(df_merged['Ngày diễn ra'])
        df_merged = df_merged.dropna(subset=['Ngày diễn ra'])
        
        df_merged['Năm'] = df_merged['Ngày diễn ra'].dt.year.astype(int)
        df_merged['Tháng'] = df_merged['Ngày diễn ra'].dt.month.astype(int)
        
        view_type = st.radio("Lọc bảng điểm:", ["Tất cả", "Năm", "Tháng"], horizontal=True)
        filtered_df = df_merged.copy()
        
        if view_type != "Tất cả":
            years = sorted(df_merged['Năm'].unique(), reverse=True)
            y = st.selectbox("Chọn Năm:", years)
            filtered_df = df_merged[df_merged['Năm'] == y]
            if view_type == "Tháng":
                m = st.selectbox("Chọn Tháng:", list(range(1, 13)), index=datetime.now().month-1)
                filtered_df = filtered_df[filtered_df['Tháng'] == m]

        tong_diem = filtered_df.groupby("Thành viên")["Số điểm"].sum().reset_index()
        bxh = pd.merge(df_thanhvien, tong_diem, left_on="Tên Thành viên", right_on="Thành viên", how="left")
        bxh["Số điểm"] = bxh["Số điểm"].fillna(0)
        
        st.dataframe(bxh[["Tên Thành viên", "Số điểm"]].sort_values("Số điểm", ascending=False), use_container_width=True)
    else:
        st.info("Chưa có dữ liệu tính điểm.")

# ================= TAB 2: QUẢN LÝ SỰ KIỆN =================
with tab2:
    if not df_sukien.empty:
        df_disp = df_sukien.copy()
        df_disp['Ngày diễn ra'] = df_disp['Ngày diễn ra'].dt.strftime('%Y-%m-%d')
        st.dataframe(df_disp, use_container_width=True)
    
    if st.session_state.is_admin:
        st.divider()
        with st.expander("➕ Thêm sự kiện mới"):
            with st.form("add_sk", clear_on_submit=True):
                c1, c2 = st.columns(2)
                ten = c1.text_input("Tên sự kiện")
                diadiem = c1.text_input("Địa điểm") # Đã thêm lại cột Địa điểm
                ngay = c2.date_input("Ngày")
                gio = c2.time_input("Giờ bắt đầu") # Đã thêm lại cột Giờ
                diem = c2.number_input("Số điểm cộng", min_value=1, value=5)
                
                if st.form_submit_button("Lưu sự kiện"):
                    if ten:
                        new_sk = pd.DataFrame({
                            "Tên sự kiện": [ten], 
                            "Ngày diễn ra": [pd.to_datetime(ngay)], 
                            "Thời gian bắt đầu": [gio.strftime("%H:%M")],
                            "Địa điểm": [diadiem], 
                            "Số điểm": [diem]
                        })
                        save_data(pd.concat([df_sukien, new_sk], ignore_index=True), "Sự kiện")
                        st.success(f"Đã lưu sự kiện: {ten}")
                        st.rerun()
                    else:
                        st.error("Vui lòng nhập tên sự kiện!")
        
        with st.expander("🗑️ Xóa sự kiện"):
            if not df_sukien.empty:
                sk_xoa = st.selectbox("Chọn sự kiện cần xóa:", df_sukien["Tên sự kiện"].tolist())
                if st.button("Xác nhận xóa vĩnh viễn", type="primary"):
                    save_data(df_sukien[df_sukien["Tên sự kiện"] != sk_xoa], "Sự kiện")
                    if not df_nhatky.empty:
                        save_data(df_nhatky[df_nhatky["Tên sự kiện"] != sk_xoa], "Nhật ký")
                    st.success(f"Đã xóa: {sk_xoa}")
                    st.rerun()

# ================= TAB 3: ĐIỂM DANH =================
with tab3:
    if not df_sukien.empty:
        sel_sk = st.selectbox("📌 Chọn sự kiện điểm danh:", df_sukien["Tên sự kiện"].tolist()[::-1])
        info = df_sukien[df_sukien["Tên sự kiện"] == sel_sk].iloc[0]
        da_den = df_nhatky[df_nhatky["Tên sự kiện"] == sel_sk]["Thành viên"].tolist() if not df_nhatky.empty else []
        
        if st.session_state.is_admin:
            chon_tv = st.multiselect("✅ Chọn thành viên tham gia:", df_thanhvien["Tên Thành viên"].tolist(), default=da_den)
            if st.button("Cập nhật điểm danh"):
                df_nk_other = df_nhatky[df_nhatky["Tên sự kiện"] != sel_sk] if not df_nhatky.empty else pd.DataFrame(columns=["Tên sự kiện", "Thành viên", "Số điểm"])
                new_logs = pd.DataFrame({
                    "Tên sự kiện": [sel_sk]*len(chon_tv), 
                    "Thành viên": chon_tv, 
                    "Số điểm": [info["Số điểm"]]*len(chon_tv)
                })
                save_data(pd.concat([df_nk_other, new_logs], ignore_index=True), "Nhật ký")
                st.success("Đã cập nhật danh sách điểm danh!")
                st.rerun()
        else:
            st.write(f"**Danh sách đã tham gia ({len(da_den)} người):**")
            if da_den:
                for idx, name in enumerate(da_den, 1):
                    st.write(f"{idx}. {name}")
            else:
                st.info("Chưa có thành viên nào tham gia.")
