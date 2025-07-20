import streamlit as st
from streamlit_calendar import calendar  # ✅ import component ชื่อ calendar จาก library
from supabase import create_client, Client  # ✅ เชื่อมต่อ Supabase
from datetime import datetime, timedelta  # ✅ ใช้จัดการวัน เวลา
import pytz
from streamlit_autorefresh import st_autorefresh  # ✅ สำหรับ refresh หน้าอัตโนมัติ
import pandas as pd  # ✅ ใช้ DataFrame
import pygame  # ✅ ใช้สำหรับเสียงเตือน (ต้องติดตั้งก่อน)
import hashlib  # ✅ สำหรับสร้าง id หรือ key แบบไม่ซ้ำ
import random
import bcrypt
# ------------------ Supabase Config ------------------
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)


# ------------------ Settings ------------------
st.set_page_config(page_title="MelBooking Admin", layout="wide")


def get_hourly_rate(massage_type):
    try:
        supabase.rpc("set_config", {
            "key": "request.store_id",
            "value": st.session_state["store_id"],
            "is_local": False
        }).execute()

        result = supabase.table("massage_types").select("Price-hour").eq("Type", massage_type).limit(1).execute()
        return float(result.data[0]["Price-hour"])
    except:
        return 0.0


def fetch_bookings():
    try:
        supabase.rpc("set_config", {
            "key": "request.store_id",
            "value": st.session_state["store_id"],
            "is_local": False
        }).execute()

        response = supabase.table("bookings").select("*").execute()
        return response.data if response.data else []
    except:
        return []


def load_bookings():
    try:
        supabase.rpc("set_config", {
            "key": "request.store_id",
            "value": st.session_state["store_id"],
            "is_local": False
        }).execute()

        response = supabase.table("bookings").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"❌ Failed to load bookings: {e}")
        return pd.DataFrame()

# ------------------ Login System ------------------
def login():
    st.sidebar.title("🔐 Admin Login")
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login"):
        response = supabase.table("admins").select("*").eq("email", email).execute()
       
        if response.data:
            admin = response.data[0]
            hashed = admin["hashed_password"]
           
            if bcrypt.checkpw(password.encode(), hashed.encode()):
                st.session_state["logged_in"] = True
                st.session_state["login_time"] = datetime.now()
                st.session_state["admin_email"] = email
                st.session_state["store_id"] = admin.get("store_id")

                # ✅ ตั้งค่า store_id สำหรับ RLS Policy ทันที
                supabase.rpc("set_config", {
                    "key": "request.store_id",
                    "value": st.session_state["store_id"],
                    "is_local": False
                }).execute()

                st.sidebar.success("✅ Login successful")
                st.rerun()
            else:
                st.sidebar.error("❌ Incorrect password")
        else:
            st.sidebar.error("❌ Email not found")


def logout():
    st.session_state.clear()
    st.sidebar.success("Logged out successfully")
    st.rerun()


def check_login():
    if 'logged_in' not in st.session_state:
        return False
    login_duration = (datetime.now() - st.session_state['login_time']).seconds
    return login_duration < 43200  # 12 hours



# ---------- AUTO REFRESH ----------
st_autorefresh(interval=20 * 1000, key="refresh")


# ---------- PLAY SOUND ----------
def play_notification():
    audio_url = "https://raw.githubusercontent.com/Melbooking/sound/main/new_booking.mp3"
    st.audio(audio_url, format="audio/mp3", start_time=0)

# ---------- DETECT NEW BOOKING BY ROW (WITH store_id) ----------
def play_notification_on_new_booking():
    store_id = st.session_state.get("store_id")
    if not store_id:
        return

    # โหลด bookings เฉพาะร้าน
    response = supabase.table("bookings").select("id").eq("store_id", store_id).execute()
    current_ids = set([row["id"] for row in response.data]) if response.data else set()
    current_count = len(current_ids)

    # ถ้ายังไม่มี session state ก็สร้างใหม่
    if "previous_booking_count" not in st.session_state:
        st.session_state.previous_booking_count = current_count
        return

    # ตรวจจับการเพิ่ม row
    if current_count > st.session_state.previous_booking_count:
        play_notification()

    # อัปเดต count ล่าสุด
    st.session_state.previous_booking_count = current_count




def convert_bookings_to_events(data):
    events = []
    melbourne_tz = pytz.timezone("Australia/Melbourne")


    for row in data:
        try:
            # ✅ แปลงวันที่และเวลา
            date_obj = datetime.strptime(row["Date"], "%d/%m/%Y").date()
            start_time = datetime.strptime(row["start_time"], "%I:%M %p").time()
            end_time = datetime.strptime(row["end_time"], "%I:%M %p").time()


            # ✅ รวมเป็น datetime พร้อม timezone
            start_dt = melbourne_tz.localize(datetime.combine(date_obj, start_time))
            end_dt = melbourne_tz.localize(datetime.combine(date_obj, end_time))


            # ✅ สร้าง event สำหรับ calendar
            events.append({
                "title": f"{row.get('customer_name', '')} - {row.get('therapist', '')}",
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat()
            })


        except Exception as e:
            print("❌ Error parsing booking:", row)
            print("📛 Reason:", e)


    return events




def calendar_view():
    st.subheader("📅 Calendar View")
    store_id = st.session_state.get("store_id")

    if not store_id:
        st.error("❌ Store ID not found.")
        return

    # 🔹 โหลด therapist เฉพาะร้าน
    therapist_response = (
        supabase.table("therapists").select("*").eq("store_id", store_id).execute()
    )
    therapists = therapist_response.data or []

    # 🔹 เตรียม resources
    color_palette = [
        "#f44336", "#3f51b5", "#009688", "#ff9800",
        "#9c27b0", "#03a9f4", "#4caf50", "#e91e63",
        "#607d8b", "#cddc39", "#795548", "#00bcd4"
    ]
    resources = []
    therapist_colors = {}
    for i, t in enumerate(therapists):
        name = t["Name"]
        resource_id = f"t_{i}"
        color = color_palette[i % len(color_palette)]
        therapist_colors[name] = {"id": resource_id, "color": color}
        resources.append({"id": resource_id, "title": name})

    # 🔹 โหลด bookings เฉพาะร้าน
    bookings_response = (
        supabase.table("bookings").select("*").eq("store_id", store_id).execute()
    )
    bookings = bookings_response.data or []

    events = []
    id_mapping = {}
    mel_tz = pytz.timezone("Australia/Melbourne")

    for row in bookings:
        try:
            date = datetime.strptime(row["Date"], "%d/%m/%Y").date()
            start = datetime.strptime(row["start_time"], "%I:%M %p").time()
            end = datetime.strptime(row["end_time"], "%I:%M %p").time()
            start_iso = mel_tz.localize(datetime.combine(date, start)).isoformat()
            end_iso = mel_tz.localize(datetime.combine(date, end)).isoformat()

            therapist = row.get("Therapist", "")
            therapist_info = therapist_colors.get(therapist)
            if not therapist_info:
                continue

            event = {
                "id": row["id"],
                "title": f"{row.get('customer_name', '')} - {row.get('Type', '')}",
                "start": start_iso,
                "end": end_iso,
                "resourceId": therapist_info["id"],
                "backgroundColor": therapist_info["color"],
                "borderColor": therapist_info["color"]
            }
            id_mapping[row["id"]] = row
            events.append(event)
        except Exception as e:
            print("❌ Error parsing booking:", e)

    # 🔹 calendar options
    calendar_options = {
        "schedulerLicenseKey": "GPL-My-Project-Is-Open-Source",
        "initialView": "resourceTimeGridDay",
        "resources": resources,
        "editable": True,
        "selectable": True,
        "droppable": True,
        "eventResizableFromStart": True,
        "nowIndicator": True,
        "slotMinTime": "08:00:00",
        "slotMaxTime": "22:00:00",
        "allDaySlot": False,
        "timeZone": "Australia/Melbourne",
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": ""
        },
        "eventTimeFormat": {
            "hour": "numeric",
            "minute": "2-digit",
            "hour12": True
        }
    }

    # 🔹 show calendar + drag drop handle
    result = calendar(events=events, options=calendar_options, key="calendar-fresha")
    if result and isinstance(result, dict) and result.get("event"):
        event = result["event"]
        event_id = event["id"]
        new_start = datetime.fromisoformat(event["start"])
        new_end = datetime.fromisoformat(event["end"])
        new_resource_id = event.get("resourceId")

        # 🔁 แปลง resourceId → therapist name
        new_therapist = None
        for name, info in therapist_colors.items():
            if info["id"] == new_resource_id:
                new_therapist = name
                break

        if not new_therapist:
            st.error("❌ ไม่พบ Therapist ที่ตรงกับ resourceId ที่เลือก")
        else:
            date_str = new_start.strftime("%d/%m/%Y")
            start_str = new_start.strftime("%I:%M %p")
            end_str = new_end.strftime("%I:%M %p")

            update_response = (
                supabase.table("bookings")
                .update({
                    "Date": date_str,
                    "start_time": start_str,
                    "end_time": end_str,
                    "Therapist": new_therapist
                })
                .eq("id", event_id)
                .eq("store_id", store_id)
                .execute()
            )

            if update_response.status_code == 200:
                st.success(f"✅ อัปเดต Booking สำเร็จ (Therapist: {new_therapist})")
            else:
                st.error("❌ อัปเดตล้มเหลว โปรดลองใหม่")




# ---------- WEEKLY SUMMARY ----------
def weekly_summary():
    st.subheader("📊 Weekly Business Income Summary")

    store_id = st.session_state.get("store_id")
    if not store_id:
        st.error("❌ Store ID not found.")
        return

    # ✅ โหลด bookings เฉพาะร้าน
    bookings_response = (
        supabase.table("bookings").select("*").eq("store_id", store_id).execute()
    )
    bookings = bookings_response.data if bookings_response.data else []
    df = pd.DataFrame(bookings)

    if df.empty:
        st.info("No bookings to summarize.")
        return

    # 🔁 แปลงวันที่
    def try_parse_date(date_str):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except:
                continue
        return None

    df["Date"] = df["Date"].apply(try_parse_date)
    df = df.dropna(subset=["Date"])
    df = df[df["Date"] >= (datetime.now() - timedelta(days=7))]

    if df.empty:
        st.warning("No bookings in the past 7 days.")
        return

    # ✅ โหลดราคาต่อชั่วโมงเฉพาะร้าน
    response = (
        supabase.table("massage_types").select("*").eq("store_id", store_id).execute()
    )
    type_data = response.data if response.data else []
    price_dict = {row["Type"]: float(row["Price-hour"]) for row in type_data}

    # ✅ คำนวณรายได้
    df["Start"] = pd.to_datetime(df["start_time"], format="%I:%M %p")
    df["End"] = pd.to_datetime(df["end_time"], format="%I:%M %p")
    df["Hours"] = (df["End"] - df["Start"]).dt.total_seconds() / 3600
    df["Price/hr"] = df["Type"].map(price_dict)
    df["Base Income"] = df["Hours"] * df["Price/hr"]
    df["Add-on Price"] = pd.to_numeric(df["Add-on Price"], errors='coerce').fillna(0)
    df["Total Income"] = df["Base Income"] + df["Add-on Price"]

    # ✅ เตรียมตารางแสดงผล
    table = df[["Date", "start_time", "Type", "Price/hr", "Hours", "Add-on Price", "Total Income"]].copy()
    table["Date"] = table["Date"].dt.strftime("%d/%m/%Y")
    table["Hours"] = table["Hours"].round(2)
    table["Price/hr"] = table["Price/hr"].round(2)
    table["Add-on Price"] = table["Add-on Price"].round(2)
    table["Total Income"] = table["Total Income"].round(2)

    st.dataframe(table)

    # ✅ สรุปรวมรายวัน
    daily_summary = table.groupby("Date").agg({
        "Total Income": "sum"
    }).reset_index()
    daily_summary["Total Income"] = daily_summary["Total Income"].round(2)

    st.markdown("### 🗓️ Daily Income Summary")
    st.dataframe(daily_summary)

    # ✅ รวมทั้ง 7 วัน
    total_income = daily_summary["Total Income"].sum()
    st.markdown(f"### 🧾 Total Income (7 days): **${total_income:.2f}**")



# ---------- STAFF PAYMENT SUMMARY ----------
def staff_payment_summary():
    st.subheader("💸 Therapist Payment Summary (Last 7 Days)")

    store_id = st.session_state.get("store_id")
    if not store_id:
        st.error("❌ Store ID not found.")
        return

    # ✅ โหลด bookings เฉพาะร้าน
    bookings_response = (
        supabase.table("bookings").select("*").eq("store_id", store_id).execute()
    )
    bookings_data = bookings_response.data or []
    bookings = pd.DataFrame(bookings_data)

    if bookings.empty:
        st.info("No bookings available.")
        return

    # ✅ โหลด therapists เฉพาะร้าน
    response = (
        supabase.table("therapists").select("*").eq("store_id", store_id).execute()
    )
    therapist_data = response.data if response.data else []
    rate_dict = {r["Name"]: float(r["Rate/hour"]) for r in therapist_data}

    # ✅ กรองข้อมูล 7 วันล่าสุด
    bookings["Date"] = pd.to_datetime(bookings["Date"], format="%d/%m/%Y", errors='coerce')
    bookings = bookings.dropna(subset=["Date"])
    recent = bookings[bookings["Date"] >= (datetime.now() - timedelta(days=7))]

    if recent.empty:
        st.warning("No therapist work in the past 7 days.")
        return

    # ✅ คำนวณชั่วโมงทำงาน
    def calc_hours(row):
        try:
            start = datetime.strptime(row["start_time"], "%I:%M %p")
            end = datetime.strptime(row["end_time"], "%I:%M %p")
            return round((end - start).total_seconds() / 3600, 2)
        except:
            return 0

    recent["Hours"] = recent.apply(calc_hours, axis=1)
    recent["Rate"] = recent["Therapist"].map(rate_dict)
    recent["Pay"] = (recent["Hours"] * recent["Rate"]).round(2)

    # ✅ ตารางรายวัน
    table = recent[["Date", "Therapist", "Rate", "Hours", "Pay"]].copy()
    table["Date"] = table["Date"].dt.strftime("%d/%m/%Y")
    st.dataframe(table)

    # ✅ สรุปต่อวัน
    daily = table.groupby("Date").agg({"Pay": "sum"}).reset_index()
    daily["Pay"] = daily["Pay"].round(2)
    st.markdown("### 🗓️ Daily Payment Summary")
    st.dataframe(daily)

    total = daily["Pay"].sum()
    st.markdown(f"### 💰 Total Payroll (7 days): **${total:.2f}**")

# ---------- MANAGE THERAPISTS ----------
def manage_therapists():
    st.subheader("👨‍⚕️ Manage Therapists")

    store_id = st.session_state.get("store_id")
    if not store_id:
        st.error("❌ Store ID not found.")
        return

    # 🔹 โหลดข้อมูลจาก Supabase ตามร้าน
    response = (
        supabase.table("therapists").select("*").eq("store_id", store_id).execute()
    )
    therapist_data = response.data if response.data else []

    # 🔹 สร้างรายชื่อที่มีอยู่แล้ว
    current_names = [r["Name"] for r in therapist_data]

    # 🔹 เพิ่มหมอนวด
    new_name = st.text_input("➕ Therapist Name")
    new_rate = st.number_input("💲 Rate per Hour", min_value=0.0, format="%.2f")

    if st.button("Add Therapist"):
        if new_name and new_name not in current_names:
            try:
                supabase.table("therapists").insert({
                    "Name": new_name,
                    "Rate/hour": new_rate,
                    "store_id": store_id  # ✅ เพิ่มเพื่อรองรับ RLS
                }).execute()
                st.success(f"✅ Added therapist {new_name} at ${new_rate}/hr")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to add therapist: {e}")
        else:
            st.warning("❗ Therapist name already exists or is empty.")

    # 🔹 ลบหมอนวด
    delete_name = st.selectbox("🗑 Delete Therapist", [""] + current_names)
    if st.button("Delete Therapist") and delete_name:
        try:
            supabase.table("therapists").delete()\
                .eq("Name", delete_name)\
                .eq("store_id", store_id)\
                .execute()
            st.success(f"🗑 Deleted therapist: {delete_name}")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error deleting therapist: {e}")

def manage_massage_types():
    st.subheader("🧾 Manage Massage Types & Add-ons")

    store_id = st.session_state.get("store_id")
    if not store_id:
        st.error("❌ Store ID not found.")
        return

    # 🔹 โหลดข้อมูลเฉพาะร้านจาก Supabase
    try:
        response = supabase.table("massage_types").select("*").eq("store_id", store_id).execute()
        data = response.data if response.data else []
    except Exception as e:
        st.error(f"❌ Failed to load massage types: {e}")
        data = []

    # 🔸 แปลงข้อมูลเป็น DataFrame (รองรับกรณี data = [])
    df = pd.DataFrame(data)
    if df.empty:
        df = pd.DataFrame(columns=["Type", "Price-hour", "is_addon"])

    if "is_addon" not in df.columns:
        df["is_addon"] = False

    # 🔸 แสดง Massage Types
    st.markdown("### 🧘 Massage Types (Main Services)")
    massage_df = df[df["is_addon"] == False]
    if not massage_df.empty:
        st.dataframe(massage_df[["Type", "Price-hour"]])
    else:
        st.info("No massage types found.")

    # 🔸 แสดง Add-ons
    st.markdown("### 🌟 Add-ons (Extra Services)")
    addon_df = df[df["is_addon"] == True]
    if not addon_df.empty:
        st.dataframe(addon_df[["Type", "Price-hour"]])
    else:
        st.info("No add-ons found.")

    # 🔸 เพิ่มรายการใหม่
    st.markdown("### ➕ Add New Item")
    new_type = st.text_input("📝 Name")
    new_price = st.number_input("💲 Price per Hour", min_value=0.0, step=1.0)
    is_addon = st.checkbox("🌟 Is this an Add-on?", value=False)

    if st.button("✅ Add"):
        if new_type:
            try:
                supabase.table("massage_types").insert({
                    "Type": new_type,
                    "Price-hour": new_price,
                    "is_addon": is_addon,
                    "store_id": store_id
                }).execute()
                st.success("✅ Item added successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to add item: {e}")
        else:
            st.warning("⚠️ Please enter a name.")

    # 🔸 ลบรายการ
    if not df.empty:
        st.markdown("### 🗑️ Delete Item")
        all_types = [f"{row['Type']} (Add-on)" if row.get("is_addon") else row["Type"] for row in data]
        selected = st.selectbox("🗂️ Select item to delete", all_types)

        if st.button("❌ Delete"):
            for row in data:
                label = f"{row['Type']} (Add-on)" if row.get("is_addon") else row["Type"]
                if label == selected:
                    try:
                        supabase.table("massage_types")\
                            .delete()\
                            .eq("id", row["id"])\
                            .eq("store_id", store_id)\
                            .execute()
                        st.success("✅ Deleted successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to delete item: {e}")


# เวลาหมอนวด (แยกร้านด้วย store_id)
def manage_therapist_times():
    st.subheader("🕒 Therapist Working Hours")

    store_id = st.session_state.get("store_id")
    if not store_id:
        st.error("❌ Store ID not found.")
        return

    # 🔹 โหลดรายชื่อ Therapist เฉพาะร้านนี้
    response = (
        supabase.table("therapists")
        .select("Name")
        .eq("store_id", store_id)
        .execute()
    )
    therapist_data = response.data if response.data else []
    names = [r["Name"] for r in therapist_data]

    if not names:
        st.warning("❗ No therapists found.")
        return

    # 🔹 แบบฟอร์มเลือก Therapist และเวลาทำงาน
    name = st.selectbox("👤 Select Therapist", names)
    t_start = st.time_input("Start Time", value=datetime.strptime("10:00 AM", "%I:%M %p").time())
    t_end = st.time_input("End Time", value=datetime.strptime("06:00 PM", "%I:%M %p").time())

    if st.button("✅ Save Time"):
        try:
            # 🔸 แปลงเวลาเป็น string format "10:00 AM"
            start_str = datetime.strptime(str(t_start), "%H:%M:%S").strftime("%I:%M %p")
            end_str = datetime.strptime(str(t_end), "%H:%M:%S").strftime("%I:%M %p")

            # 🔸 ตรวจว่ามีข้อมูลอยู่แล้วหรือยัง
            existing = (
                supabase.table("therapist_times")
                .select("*")
                .eq("Name", name)
                .eq("store_id", store_id)
                .execute()
                .data
            )

            if existing:
                # อัปเดตเวลา
                supabase.table("therapist_times").update({
                    "Start": start_str,
                    "End": end_str
                }).eq("Name", name).eq("store_id", store_id).execute()
            else:
                # เพิ่มใหม่
                supabase.table("therapist_times").insert({
                    "Name": name,
                    "Start": start_str,
                    "End": end_str,
                    "store_id": store_id
                }).execute()

            st.success(f"✅ Time saved: {start_str} - {end_str}")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Failed to save working time: {e}")

# เวลาเปิดร้าน (แยกร้านด้วย store_id)
def manage_store_hours():
    st.subheader("🏪 Set Store Opening Hours")

    store_id = st.session_state.get("store_id")
    if not store_id:
        st.error("❌ Store ID not found.")
        return

    # 🔹 โหลด store_hours เฉพาะร้านนี้
    response = (
        supabase.table("store_hours")
        .select("*")
        .eq("store_id", store_id)
        .limit(1)
        .execute()
    )
    records = response.data if response.data else []

    # 🔹 ตั้งค่า default เวลา
    try:
        current = records[0]
        default_open = datetime.strptime(current["Open"], "%I:%M %p").time()
        default_close = datetime.strptime(current["Close"], "%I:%M %p").time()
    except:
        default_open = datetime.strptime("10:00 AM", "%I:%M %p").time()
        default_close = datetime.strptime("06:00 PM", "%I:%M %p").time()

    # 🔹 Input สำหรับเวลา
    open_time = st.time_input("🕙 Open Time", value=default_open)
    close_time = st.time_input("🕕 Close Time", value=default_close)

    if st.button("💾 Save Store Hours"):
        open_str = datetime.strptime(str(open_time), "%H:%M:%S").strftime("%I:%M %p")
        close_str = datetime.strptime(str(close_time), "%H:%M:%S").strftime("%I:%M %p")

        try:
            if records:
                # ✅ อัปเดตเวลาเดิม
                supabase.table("store_hours").update({
                    "Open": open_str,
                    "Close": close_str
                }).eq("id", current["id"]).eq("store_id", store_id).execute()
            else:
                # ✅ เพิ่มเวลาใหม่
                supabase.table("store_hours").insert({
                    "Open": open_str,
                    "Close": close_str,
                    "store_id": store_id
                }).execute()

            st.success(f"✅ Saved: {open_str} - {close_str}")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Failed to save store hours: {e}")


def manage_bookings():
    st.subheader("🛠 Manage Bookings")

    store_id = st.session_state.get("store_id")
    if not store_id:
        st.error("❌ Store ID not found.")
        return

    # 🔹 โหลด bookings เฉพาะร้านนี้
    bookings_response = supabase.table("bookings").select("*").eq("store_id", store_id).execute()
    massage_response = supabase.table("massage_types").select("*").eq("store_id", store_id).execute()
    therapist_response = supabase.table("therapists").select("Name").eq("store_id", store_id).execute()

    bookings_data = bookings_response.data if bookings_response.data else []
    massage_data = massage_response.data if massage_response.data else []
    therapist_names = [r["Name"] for r in therapist_response.data] if therapist_response.data else []

    # ✅ แสดงข้อมูลทั้งหมด
    if bookings_data:
        df = pd.DataFrame(bookings_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("📭 No bookings found.")

    # ---------- ADD BOOKING ----------
    st.markdown("---")
    st.subheader("➕ Add New Booking")

    name = st.text_input("Customer Name", key="add_customer_name")
    phone = st.text_input("Phone Number", key="add_customer_phone")
    therapist = st.selectbox("Therapist", therapist_names, key="add_therapist")
    type_names = [r["Type"] for r in massage_data]
    type_selected = st.selectbox("Massage Type", type_names, key="add_type")
    date = st.date_input("Booking Date", key="add_booking_date")

    start_time = st.time_input("Start Time", value=datetime.strptime("10:00 AM", "%I:%M %p").time(), key="start_time_key")
    end_time = st.time_input("End Time", value=datetime.strptime("11:00 AM", "%I:%M %p").time(), key="end_time_key")
    addon_minutes = st.selectbox("Add-on Time (minutes)", [0, 15, 30, 45, 60], key="addon_minutes_key")

    if st.button("✅ Save Booking", key="save_booking_button"):
        try:
            start_str = datetime.strptime(str(start_time), "%H:%M:%S").strftime("%I:%M %p")
            end_str = datetime.strptime(str(end_time), "%H:%M:%S").strftime("%I:%M %p")
            date_str = date.strftime("%d/%m/%Y")

            addon_price = 0
            for row in massage_data:
                if row["Type"] == type_selected:
                    price_per_hour = float(row["Price-hour"])
                    addon_price = round((price_per_hour / 60) * addon_minutes, 2)
                    break

            booking_data = {
                "Date": date_str,
                "start_time": start_str,
                "end_time": end_str,
                "customer_name": name,
                "phone": phone,
                "therapist": therapist,
                "type": type_selected,
                "Add-on": f"{addon_minutes} min" if addon_minutes else "",
                "Add-on Price": addon_price if addon_minutes else 0,
                "store_id": store_id
            }

            supabase.table("bookings").insert(booking_data).execute()
            st.success("✅ Booking added successfully!")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Failed to save booking: {e}")

    # ---------- DELETE BOOKING ----------
    st.markdown("---")
    st.subheader("❌ Delete Existing Booking")

    if not bookings_data:
        st.info("No bookings available to delete.")
        return

    name_to_delete = st.selectbox("Select Booking Name to Delete", [""] + df["customer_name"].unique().tolist(), key="delete_customer_name")
    date_to_delete = st.date_input("Booking Date to Delete", key="delete_booking_date")

    if st.button("Delete Booking", key="delete_booking_button") and name_to_delete:
        try:
            date_str = date_to_delete.strftime("%d/%m/%Y")
            match = next((b for b in bookings_data if b["customer_name"] == name_to_delete and b["Date"] == date_str), None)

            if match and "id" in match:
                supabase.table("bookings").delete().eq("id", match["id"]).eq("store_id", store_id).execute()
                st.success(f"✅ Deleted booking for {name_to_delete} on {date_str}")
                st.rerun()
            else:
                st.warning("⚠️ Booking not found or missing 'id' field.")
        except Exception as e:
            st.error(f"❌ Error deleting booking: {e}")

def auto_archive_old_bookings():
    try:
        today = datetime.today().date()
        store_id = st.session_state.get("store_id")
        if not store_id:
            st.error("❌ Store ID not found.")
            return

        # ✅ ดึงเฉพาะ bookings ของร้านนี้
        response = supabase.table("bookings").select("*").eq("store_id", store_id).execute()
        data = response.data if response.data else []

        to_archive = []
        for row in data:
            try:
                booking_date = datetime.strptime(row["Date"], "%d/%m/%Y").date()
                if booking_date < today:
                    to_archive.append(row)
            except Exception as e:
                print(f"⚠️ Failed to parse date for row: {row} | {e}")

        archived_count = 0
        failed_count = 0

        for row in to_archive:
            try:
                if "id" in row:
                    # ✅ ใส่ store_id ลงไปตอน archive ด้วย
                    archived_data = row.copy()
                    archived_data["store_id"] = store_id

                    supabase.table("archived_bookings").insert(archived_data).execute()
                    supabase.table("bookings").delete().eq("id", row["id"]).eq("store_id", store_id).execute()
                    archived_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"❌ Failed to archive row: {row} | {e}")
                failed_count += 1

        if archived_count > 0:
            st.info(f"📦 Archived {archived_count} past bookings.")
        elif failed_count > 0:
            st.warning(f"⚠️ Found {failed_count} expired bookings but couldn't archive due to missing 'id'.")
        else:
            st.info("📅 No old bookings to archive.")

    except Exception as e:
        st.error(f"❌ Archive failed: {e}")

def view_archived_bookings():
    st.subheader("📦 Archived Bookings")

    store_id = st.session_state.get("store_id")
    if not store_id:
        st.error("❌ Store ID not found.")
        return

    try:
        # ✅ โหลดเฉพาะ bookings ที่ตรงกับ store_id
        response = supabase.table("archived_bookings").select("*").eq("store_id", store_id).execute()
        data = response.data if response.data else []

        if not data:
            st.info("📭 No archived bookings found.")
            return

        df = pd.DataFrame(data)

        # 🔹 แปลงวันที่ให้อ่านง่าย
        if "Date" in df.columns:
            try:
                df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y")
                df = df.sort_values(by="Date", ascending=False)
                df["Date"] = df["Date"].dt.strftime("%d/%m/%Y")
            except:
                pass

        st.dataframe(df)

    except Exception as e:
        st.error(f"❌ Failed to load archived bookings: {e}")


def main():
    if not check_login():
        login()
        return


    st.sidebar.title("🛠 Admin Menu")
    menu = st.sidebar.radio("Select", [
        "Calendar View", "📦 View Archived Bookings", "📊 Weekly Summary", "💸 Staff Payment",
        "👨‍⚕️ Manage Therapists", "💆 Massage Types",
        "🕒 Set Working Hours", "🏪 Store Hours",
        "🛠 Manage Bookings", "🔓 Logout"
    ])





    if menu == "Calendar View":
        auto_archive_old_bookings()  # ✅ ถูกที่
        play_notification_on_new_booking()
        calendar_view()
    elif menu == "📦 View Archived Bookings":
        view_archived_bookings()
    elif menu == "📊 Weekly Summary":
        weekly_summary()
    elif menu == "👨‍⚕️ Manage Therapists":
        manage_therapists()
    elif menu == "💆 Massage Types":
        manage_massage_types()
    elif menu == "🕒 Set Working Hours":
        manage_therapist_times()
    elif menu == "🏪 Store Hours":
        manage_store_hours()
    elif menu == "🛠 Manage Bookings":
        manage_bookings()
    elif menu == "🔓 Logout":
        logout()
    elif menu == "💸 Staff Payment":
        staff_payment_summary()


if __name__ == "__main__":
    main()







