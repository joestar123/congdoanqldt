import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import numpy as np

# ================= 1. CẤU HÌNH & KẾT NỐI (TỐI ƯU QUOTA) =================
SHEET_NAME = "diem_cong_doan" 

@st.cache_resource
def get_gspread_client():
    # Chuyển secrets sang dict để có thể chỉnh sửa (tránh lỗi Read-only)
    creds_info = st.secrets["gcp_service_account"].to_dict()
    if "private_key" in creds_info:
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(creds)

# Khởi tạo client
client = get_gspread_client()
sh = client.open(SHEET_NAME)

@st.cache_data(ttl=300) # Cache 5 phút để phục vụ nhiều người dùng cùng lúc
def load_data(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        # Đọc ngày tháng theo định dạng dd/mm/yyyy
        if "Ngày diễn ra" in df.columns:
            df["Ngày diễn ra"] = pd.to_datetime(df["Ngày diễn ra"], dayfirst=True, errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()

def save_data(df, sheet_name):
    """Lưu dữ liệu với định dạng dd/mm/yyyy và xử lý an toàn JSON"""
    try:
        df_to_save = df.copy()
        
        # Chuyển cột ngày tháng sang định dạng dd/mm/yyyy trước khi lưu xuống Sheet
        if "Ngày diễn ra" in df_to_save.columns:
            df_to_save["Ngày diễn ra"] = pd.to_datetime(df_to_save["Ngày diễn ra"]).dt.strftime('%d/%m/%Y')

        # Ép kiểu các cột datetime khác sang chuỗi
        for col in df_to_save.select_dtypes(include=['datetime', 'datetimetz']).columns:
            df_to_save[col] = df_to_save[col].astype(str)

        # Xử lý các giá trị đặc biệt (NaN, inf)
        df_to_save = df_to_save.replace([np.inf, -np.inf], np.nan).fillna("")

        # Hàm đảm bảo kiểu dữ liệu thuần túy cho JSON API
        def force_json_safe(val):
            if isinstance(val, (np.integer, np.int64)): return int(val)
            if isinstance(val, (np.floating, np.float64)): return float(val)
            if isinstance(val, (bool, np.bool_)): return bool(val)
            if pd.isna(val) or str(val) == "NaT": return ""
            return str(val)

        data_list = [df_to_save.columns.values.tolist()]
        for row in df_to_save.values.tolist():
            data_list.append([force_json_safe(v) for v in row])

        # Thực hiện ghi đè an toàn
        worksheet = sh.worksheet(sheet_name)
        worksheet.clear() 
        worksheet.update(data_list)
        
        # Làm mới bộ nhớ đệm cho tất cả người dùng
        st.cache_data.clear()
        
    except Exception as e:
        st.error(f"❌ Lỗi khi lưu vào '{sheet_name}': {e}")

# ================= 2. GIAO DIỆN ỨNG DỤNG =================
st.set_page_config(page_title="Quản lý Công Đoàn", layout="wide")

# Nút Refresh dữ liệu ở Sidebar
if st.sidebar.button("🔄 Tải lại dữ liệu mới nhất"):
    st.cache_data.clear()
    st.rerun()

st.title("🎯 Hệ thống Quản lý Điểm Công Đoàn")

# Quản lý Admin
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

with st.sidebar:
    st.header("🔐 Quyền Admin")
    if not st.session_state.is_admin:
        admin_pass = st.text_input("Mật khẩu hệ thống:", type="password")
        if st.button("Đăng nhập"):
            if admin_pass == st.secrets["admin_password"]:
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Sai mật khẩu!")
    else:
        st.success("✅ Chế độ Admin: Bật")
        if st.button("Đăng xuất"):
            st.session_state.is_admin = False
            st.rerun()

# Tải dữ liệu từ Cache
df_thanhvien = load_data("Thành viên")
df_sukien = load_data("Sự kiện")
df_nhatky = load_data("Nhật ký")

tab1, tab2, tab3 = st.tabs(["🏆 Bảng Xếp Hạng", "📅 Quản lý Sự Kiện", "✅ Điểm Danh"])

# ================= TAB 1: BẢNG XẾP HẠNG =================
with tab1:
    st.header("Thống kê Điểm Tích Lũy")
    if not df_nhatky.empty and not df_sukien.empty:
        df_merged = pd.merge(df_nhatky, df_sukien[["Tên sự kiện", "Ngày diễn ra"]], on="Tên sự kiện", how="left")
        df_merged['Ngày diễn ra'] = pd.to_datetime(df_merged['Ngày diễn ra'])
        df_merged = df_merged.dropna(subset=['Ngày diễn ra'])
        
        df_merged['Năm'] = df_merged['Ngày diễn ra'].dt.year.astype(int)
        df_merged['Tháng'] = df_merged['Ngày diễn ra'].dt.month.astype(int)
        
        c_f1, c_f2 = st.columns([1, 2])
        view_type = c_f1.radio("Chế độ xem:", ["Tất cả", "Theo Năm", "Theo Tháng"], horizontal=True)
        filtered_df = df_merged.copy()
        
        with c_f2:
            if view_type != "Tất cả":
                years = sorted(df_merged['Năm'].unique(), reverse=True)
                y = st.selectbox("Chọn Năm:", years)
                filtered_df = df_merged[df_merged['Năm'] == y]
                if view_type == "Theo Tháng":
                    m = st.selectbox("Chọn Tháng:", list(range(1, 13)), index=datetime.now().month-1)
                    filtered_df = filtered_df[filtered_df['Tháng'] == m]

        tong_diem = filtered_df.groupby("Thành viên")["Số điểm"].sum().reset_index()
        bxh = pd.merge(df_thanhvien, tong_diem, left_on="Tên Thành viên", right_on="Thành viên", how="left")
        bxh["Số điểm"] = bxh["Số điểm"].fillna(0)
        
        st.dataframe(bxh[["Tên Thành viên", "Số điểm"]].sort_values("Số điểm", ascending=False), use_container_width=True)
    else:
        st.info("Chưa có dữ liệu để hiển thị.")

# ================= TAB 2: QUẢN LÝ SỰ KIỆN =================
with tab2:
    st.header("Danh Sách Sự Kiện")
    if not df_sukien.empty:
        df_disp = df_sukien.copy()
        # Hiển thị ngày dạng dd/mm/yyyy trên bảng Streamlit
        df_disp['Ngày diễn ra'] = df_disp['Ngày diễn ra'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_disp, use_container_width=True)
    
    if st.session_state.is_admin:
        st.divider()
        st.subheader("➕ Thêm Sự Kiện")
        with st.form("add_sk_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            ten = c1.text_input("Tên sự kiện")
            diadiem = c1.text_input("Địa điểm tổ chức")
            ngay = c2.date_input("Ngày diễn ra")
            gio = c2.time_input("Giờ bắt đầu")
            diem = c2.number_input("Số điểm cộng", min_value=1, value=5)
            
            if st.form_submit_button("Lưu vào hệ thống"):
                if ten:
                    new_sk = pd.DataFrame({
                        "Tên sự kiện": [ten], 
                        "Ngày diễn ra": [pd.to_datetime(ngay)], 
                        "Thời gian bắt đầu": [gio.strftime("%H:%M")],
                        "Địa điểm": [diadiem], 
                        "Số điểm": [diem]
                    })
                    # Hợp nhất và lưu lại
                    df_sukien_all = pd.concat([df_sukien, new_sk], ignore_index=True)
                    save_data(df_sukien_all, "Sự kiện")
                    st.success(f"Đã thêm thành công sự kiện: {ten}")
                    st.rerun()
                else:
                    st.error("Tên sự kiện không được để trống!")

        st.divider()
        st.subheader("🗑️ Xóa Sự Kiện")
        if not df_sukien.empty:
            list_sk = df_sukien["Tên sự kiện"].tolist()
            sk_del = st.selectbox("Chọn sự kiện để xóa:", list_sk)
            if st.button("Xác nhận xóa vĩnh viễn", type="primary"):
                # Cập nhật bảng Sự kiện
                df_sukien = df_sukien[df_sukien["Tên sự kiện"] != sk_del]
                save_data(df_sukien, "Sự kiện")
                # Cập nhật bảng Nhật ký để xóa điểm liên quan
                if not df_nhatky.empty:
                    df_nhatky = df_nhatky[df_nhatky["Tên sự kiện"] != sk_del]
                    save_data(df_nhatky, "Nhật ký")
                st.success(f"Đã xóa toàn bộ dữ liệu của: {sk_del}")
                st.rerun()

# ================= TAB 3: ĐIỂM DANH =================
with tab3:
    st.header("Thực Hiện Điểm Danh")
    if not df_sukien.empty:
        # Sắp xếp sự kiện mới nhất lên trên
        sk_options = df_sukien["Tên sự kiện"].tolist()[::-1]
        sel_sk = st.selectbox("📌 Chọn sự kiện đang diễn ra:", sk_options)
        
        # Lấy thông tin điểm của sự kiện được chọn
        row_info = df_sukien[df_sukien["Tên sự kiện"] == sel_sk].iloc[0]
        
        # Lấy danh sách đã điểm danh cũ
        da_co = []
        if not df_nhatky.empty:
            da_co = df_nhatky[df_nhatky["Tên sự kiện"] == sel_sk]["Thành viên"].tolist()
        
        if st.session_state.is_admin:
            all_members = df_thanhvien["Tên Thành viên"].tolist()
            chon_tv = st.multiselect("✅ Tích chọn thành viên có mặt:", all_members, default=da_co)
            
            if st.button("Lưu danh sách điểm danh"):
                # Giữ nhật ký các sự kiện khác
                if not df_nhatky.empty:
                    df_nk_keep = df_nhatky[df_nhatky["Tên sự kiện"] != sel_sk]
                else:
                    df_nk_keep = pd.DataFrame(columns=["Tên sự kiện", "Thành viên", "Số điểm"])
                
                # Tạo bản ghi mới cho sự kiện này
                if chon_tv:
                    new_entries = pd.DataFrame({
                        "Tên sự kiện": [sel_sk] * len(chon_tv), 
                        "Thành viên": chon_tv, 
                        "Số điểm": [row_info["Số điểm"]] * len(chon_tv)
                    })
                    df_nk_final = pd.concat([df_nk_keep, new_entries], ignore_index=True)
                else:
                    df_nk_final = df_nk_keep
                
                save_data(df_nk_final, "Nhật ký")
                st.success("Cập nhật điểm danh thành công!")
                st.rerun()
        else:
            st.write(f"**Danh sách tham gia ({len(da_co)}):**")
            if da_co:
                for n, name in enumerate(da_co, 1):
                    st.write(f"{n}. {name}")
            else:
                st.info("Chưa có thành viên nào được điểm danh cho sự kiện này.")
    else:
        st.warning("Vui lòng tạo sự kiện trước khi thực hiện điểm danh.")
