import streamlit as st
from supabase import create_client
import pandas as pd
import uuid
from datetime import datetime
from bcrypt import hashpw, gensalt
import re

# ====== Connect to Supabase ======
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

# ====== Super Admin Credentials ======
SUPER_ADMIN_EMAIL = st.secrets["SUPER_ADMIN_EMAIL"]
SUPER_ADMIN_PASSWORD = st.secrets["SUPER_ADMIN_PASSWORD"]

# ====== Helper ======
def slugify(name):
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')
    return slug

# ====== Login ======
def login():
    st.title("🧑‍💼 Super Admin Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if email == SUPER_ADMIN_EMAIL and password == SUPER_ADMIN_PASSWORD:
            st.session_state["superadmin"] = True
            st.success("✅ Login สำเร็จ")
            st.rerun()
        else:
            st.error("❌ Email หรือ Password ผิด")

# ====== Dashboard ======
def dashboard():
    st.sidebar.title("🧭 Super Admin")
    st.title("📊 MelBooking Super Admin Dashboard")

    # ---- ร้านทั้งหมด
    stores = supabase.table("stores").select("*").execute().data
    st.subheader(f"🏪 All Stores ({len(stores)})")
    for s in stores:
        slug = s.get("store_slug", "")
        store_url = f"https://melbooking.streamlit.app/?store_name={slug}"
        st.markdown(f"- **{s['store_name']}**  
        🔗 [เปิดลิงก์ร้าน]({store_url})  
        🆔 ID: `{s['id']}`", unsafe_allow_html=True)

    # ---- Booking ทุกร้าน
    bookings = supabase.table("bookings").select("*").execute().data
    st.subheader(f"📅 All Bookings ({len(bookings)})")
    if bookings:
        df = pd.DataFrame(bookings)
        expected_cols = ["customer_name", "start_time", "store_id"]
        available_cols = [col for col in expected_cols if col in df.columns]
        st.dataframe(df[available_cols])
    else:
        st.info("ยังไม่มีข้อมูลการจอง")

    # ---- เพิ่มร้านใหม่
    st.subheader("➕ Add New Store")
    name = st.text_input("Store name")
    if st.button("Create Store"):
        slug = slugify(name)
        new_store = {
            "id": str(uuid.uuid4()),
            "store_name": name,
            "store_slug": slug,
            "status": "active",
            "created_at": datetime.now().isoformat()
        }
        supabase.table("stores").insert(new_store).execute()
        st.success("✅ Store added!")
        st.rerun()

    # ---- Reset Password Admin
    st.subheader("🔐 Reset Admin Password")
    email_reset = st.text_input("Admin email to reset")
    new_password = st.text_input("New password")
    if st.button("Reset Password"):
        hashed_pw = hashpw(new_password.encode(), gensalt()).decode()
        result = supabase.table("admins").update({"hashed_password": hashed_pw}).eq("email", email_reset).execute()
        if result.data:
            st.success("✅ Password updated successfully.")
        else:
            st.error("❌ Failed to update password.")

    # ---- เพิ่มแอดมินร้านใหม่
    st.subheader("👤 Create New Admin Account")
    new_admin_email = st.text_input("New Admin Email")
    new_admin_password = st.text_input("New Admin Password")
    store_options = {s["store_name"]: s["id"] for s in stores}
    selected_store = st.selectbox("Assign to Store", list(store_options.keys()))
    if st.button("Create Admin Account"):
        hashed_pw = hashpw(new_admin_password.encode(), gensalt()).decode()
        store_id = store_options[selected_store]
        result = supabase.table("admins").insert({
            "email": new_admin_email,
            "hashed_password": hashed_pw,
            "store_id": store_id,
            "role": "owner",
            "created_at": datetime.now().isoformat()
        }).execute()
        if result.data:
            st.success(f"✅ Admin created for store: {selected_store}")
            st.rerun()
        else:
            st.error("❌ Failed to create admin. อาจมี email ซ้ำ")

    # ---- ดู/ลบ/แก้ไข Admin
    st.subheader("👥 Manage Admin Accounts")
    admins = supabase.table("admins").select("*").execute().data
    if admins:
        df_admins = pd.DataFrame(admins)
        expected_cols = ["email", "store_id", "role", "created_at"]
        available_cols = [col for col in expected_cols if col in df_admins.columns]
        st.dataframe(df_admins[available_cols])

        st.markdown("### 🔧 Modify Admin Account")
        admin_emails = [a.get("email", "unknown") for a in admins if a.get("email")]
        if admin_emails:
            selected_email = st.selectbox("Select admin email", admin_emails)
            action = st.radio("Action", ["Change Store", "Delete Admin"])

            if action == "Change Store":
                selected_store = st.selectbox("Assign new store", list(store_options.keys()))
                store_id = store_options[selected_store]
                if st.button("Update Admin Store"):
                    result = supabase.table("admins").update({
                        "store_id": store_id
                    }).eq("email", selected_email).execute()
                    if result.data:
                        st.success("✅ Admin store updated.")
                        st.rerun()
                    else:
                        st.error("❌ Failed to update store.")

            elif action == "Delete Admin":
                if st.button("Confirm Delete Admin"):
                    result = supabase.table("admins").delete().eq("email", selected_email).execute()
                    if result.data:
                        st.success("🗑️ Admin deleted.")
                        st.rerun()
                    else:
                        st.error("❌ Failed to delete admin.")
        else:
            st.info("ไม่มีแอดมินให้จัดการ")
    else:
        st.info("ยังไม่มีแอดมินในระบบ")

# ====== Main ======
if "superadmin" not in st.session_state:
    login()
else:
    dashboard()