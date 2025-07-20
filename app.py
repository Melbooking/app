import streamlit as st
from supabase import create_client
from datetime import datetime, timedelta, time
import pytz
import yagmail
import os

# ------------------ Load Secrets ------------------
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
EMAIL = st.secrets["EMAIL_SENDER"]
APP_PASSWORD = st.secrets["EMAIL_APP_PASSWORD"]
supabase = create_client(url, key)
melbourne_tz = pytz.timezone("Australia/Melbourne")

# ------------------ Set Page Config ------------------
st.set_page_config(page_title="MelBooking - Booking", layout="centered")

import uuid

# ✅ ตรวจสอบว่าเป็น UUID จริงหรือไม่
def is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False

query_params = st.query_params
store_id = (query_params.get("store_id") or [None])[0]
store_slug = (query_params.get("store_slug") or [None])[0]

# ✅ ตรวจสอบและโหลดข้อมูลร้าน
if store_id and is_valid_uuid(store_id):
    store_data = supabase.table("stores").select("id").eq("id", store_id).limit(1).execute()
elif store_slug:
    store_data = supabase.table("stores").select("id").eq("store_slug", store_slug).limit(1).execute()
else:
    st.error("❌ กรุณาเข้าผ่านลิงก์ที่มี store_id หรือ store_slug")
    st.stop()

if not store_data.data:
    st.error("❌ ไม่พบร้านในระบบ กรุณาตรวจสอบลิงก์อีกครั้ง")
    st.stop()

# ✅ ใช้ store_id ที่ได้จาก Supabase
store_id = store_data.data[0]["id"]

# ------------------ Email Function ------------------
def send_confirmation_email(name, phone, email, massage_type, therapist, date, start, end, note, addon_names):
    body = f"""
    🙏 Thank you for booking with MelBooking!

    👤 Name: {name}
    📞 Phone: {phone}
    📧 Email: {email}
    💆 Massage: {massage_type}
    🧴 Add-ons: {addon_names if addon_names else 'None'}
    🦶 Therapist: {therapist}
    🗓 Date: {date.strftime('%A, %d %B %Y')}
    ⏰ Time: {start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}
    ✏️ Note: {note if note else 'None'}

    We'll see you soon! ❤️
    """
    yag = yagmail.SMTP(EMAIL, EMAIL_APP_PASSWORD)
    yag.send(to=email, subject="🧴 Massage Booking Confirmed", contents=body)

# ------------------ Get Store Open/Close ------------------
def get_store_hours():
    try:
        response = supabase.table("store_hours").select("Open, Close").eq("store_id", store_id).limit(1).execute()
        data = response.data
        if data:
            open_time = datetime.strptime(data[0]["Open"], "%I:%M %p").time()
            close_time = datetime.strptime(data[0]["Close"], "%I:%M %p").time()
            return open_time, close_time
    except:
        pass
    return time(10, 0), time(20, 0)

# ------------------ Booking Page ------------------
def booking_page():
    st.title("💆 MelBooking")

    therapists = [t["Name"] for t in supabase.table("therapists").select("*").eq("store_id", store_id).execute().data]
    massage_types_data = supabase.table("massage_types").select("*").eq("store_id", store_id).execute().data
    main_massage_types = [m for m in massage_types_data if not m.get("is_addon", False)]
    addon_types = [a for a in massage_types_data if a.get("is_addon", False)]

    today = datetime.now(melbourne_tz).date()

    with st.form("booking_form", clear_on_submit=True):
        name = st.text_input("👤 Full Name")
        phone = st.text_input("📞 Phone Number")
        email = st.text_input("📧 Email Address")

        display_list = [f"{m['Type']} (${m['Price/hour']}/hr)" for m in main_massage_types]
        selected_index = st.selectbox("💆 Massage Type", range(len(display_list)), format_func=lambda i: display_list[i])
        massage_type = main_massage_types[selected_index]["Type"]
        base_price = float(main_massage_types[selected_index]["Price/hour"])

        selected_addons = st.multiselect("➕ Add-ons (optional)", options=addon_types,
                                         format_func=lambda a: f"{a['Type']} (+${a['Price/hour']})")

        therapist = st.selectbox("🧑‍⚕️ Therapist", therapists)
        date = st.date_input("📅 Select Date", min_value=today)
        duration_text = st.selectbox("⏱ Duration", ["30 mins", "45 mins", "1 hour", "1.5 hours", "2 hours"])
        durations = {"30 mins": 30, "45 mins": 45, "1 hour": 60, "1.5 hours": 90, "2 hours": 120}
        duration = durations[duration_text]

        note = st.text_area("✏️ Special Request (optional)")

        store_open, store_close = get_store_hours()
        start_dt = melbourne_tz.localize(datetime.combine(date, store_open))
        end_limit = melbourne_tz.localize(datetime.combine(date, store_close)) - timedelta(minutes=duration)

        available_times = []
        time_map = {}

        while start_dt <= end_limit:
            display = start_dt.strftime("%I:%M %p")
            available_times.append(display)
            time_map[display] = start_dt
            start_dt += timedelta(minutes=15)

        selected_time_str = st.selectbox("🕒 Available Time", available_times) if available_times else None
        confirm = st.form_submit_button("✅ Confirm Booking")

        if confirm and selected_time_str:
            if not email.strip():
                st.error("📧 Please enter a valid email address.")
                return
            if not phone.strip():
                st.error("📞 Please enter your phone number.")
                return

            start_dt = time_map[selected_time_str]
            end_dt = start_dt + timedelta(minutes=duration)

            addon_price = sum(float(a["Price/hour"]) for a in selected_addons)
            addon_names = ", ".join(a["Type"] for a in selected_addons)

            supabase.table("bookings").insert({
                "store_id": store_id,
                "Date": start_dt.strftime("%d/%m/%Y"),
                "start_time": start_dt.strftime("%I:%M %p"),
                "end_time": end_dt.strftime("%I:%M %p"),
                "customer_name": name,
                "Therapist": therapist,
                "phone": phone,
                "Type": massage_type,
                "add_on": addon_names,
                "Add-on Price": addon_price
            }).execute()

            send_confirmation_email(name, phone, email, massage_type, therapist, date, start_dt, end_dt, note, addon_names)
            st.success(f"🎉 Booking confirmed on {date.strftime('%d/%m/%Y')} at {selected_time_str} with {therapist}")

# ------------------ Run ------------------
booking_page()