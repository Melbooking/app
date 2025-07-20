import streamlit as st
from supabase import create_client
from datetime import datetime, timedelta, time
import pytz
import yagmail
import uuid

# ------------------ Load Secrets ------------------
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
EMAIL = st.secrets["EMAIL_SENDER"]
EMAIL_APP_PASSWORD = st.secrets["EMAIL_APP_PASSWORD"]
supabase = create_client(url, key)
melbourne_tz = pytz.timezone("Australia/Melbourne")

# ------------------ Set Page Config ------------------
st.set_page_config(page_title="MelBooking - Booking", layout="centered")

def is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False

# ------------------ รับ store_id หรือ store_slug จาก URL ------------------
query_params = st.query_params
store_id = query_params.get("store_id")
store_slug = query_params.get("store_slug") or query_params.get("store")

if store_id and is_valid_uuid(store_id):
    response = supabase.table("stores").select("id").eq("id", store_id).limit(1).execute()
elif store_slug:
    response = supabase.table("stores").select("id").eq("store_slug", store_slug).limit(1).execute()
else:
    st.error("❌ Please access the page using a valid link with store_id or store_slug.")
    st.stop()

if not response or not response.data or not isinstance(response.data, list) or len(response.data) == 0:
    st.error("❌ Store not found. Please check the link again.")
    st.stop()

first_row = response.data[0]
store_id = first_row.get("id")

if not store_id:
    st.error("❌ Invalid store ID. Please verify your store data in Supabase.")
    st.stop()

# ------------------ Email Function ------------------
def send_confirmation_email(name, phone, email, service_type, provider, date, start, end, note, addon_names):
    body = f"""
🙏 Thank you for booking with MelBooking!

👤 Name: {name}
📞 Phone: {phone}
📧 Email: {email}
🛎️ Service: {service_type}
➕ Extras: {addon_names if addon_names else 'None'}
👤 Provider: {provider}
📅 Date: {date.strftime('%A, %d %B %Y')}
⏰ Time: {start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}
✏️ Note: {note if note else 'None'}

We look forward to seeing you! ❤️
"""
    yag = yagmail.SMTP(EMAIL, EMAIL_APP_PASSWORD)
    yag.send(to=email, subject="🛎️ Service Booking Confirmed", contents=body)

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
    st.title("📅 MelBooking: Book Your Service")

    therapists_data = supabase.table("therapists").select("*").eq("store_id", store_id).execute().data or []
    service_types_data = supabase.table("massage_types").select("*").eq("store_id", store_id).execute().data or []
    main_service_types = [m for m in service_types_data if not m.get("is_addon", False)]
    addon_types = [a for a in service_types_data if a.get("is_addon", False)]

    if not therapists_data:
        st.warning("⚠️ No service providers available. Please add them in admin panel.")
        return
    if not main_service_types:
        st.warning("⚠️ No service types found. Please add them in admin panel.")
        return

    providers = [t["Name"] for t in therapists_data]
    today = datetime.now(melbourne_tz).date()

    with st.form("booking_form", clear_on_submit=False):
        name = st.text_input("👤 Full Name")
        phone = st.text_input("📞 Phone Number")
        email = st.text_input("📧 Email Address")

        display_list = [f"{m['Type']} (${m['Price-hour']}/hr)" for m in main_service_types]
        selected_index = st.selectbox("🛎️ Service Type", range(len(display_list)), format_func=lambda i: display_list[i])
        service_type = main_service_types[selected_index]["Type"]
        base_price = float(main_service_types[selected_index]["Price-hour"])

        selected_addons = st.multiselect("➕ Extras (optional)", options=addon_types,
                                         format_func=lambda a: f"{a['Type']} (+${a['Price-hour']})") if addon_types else []

        provider = st.selectbox("👤 Service Provider", providers)
        date = st.date_input("📅 Select Date", min_value=today)
        duration_text = st.selectbox("⏱ Duration", ["30 mins", "45 mins", "1 hour", "1.5 hours", "2 hours"])
        durations = {"30 mins": 30, "45 mins": 45, "1 hour": 60, "1.5 hours": 90, "2 hours": 120}
        duration = durations[duration_text]
        note = st.text_area("✏️ Additional Notes (optional)")

        store_open, store_close = get_store_hours()
        slot_time = melbourne_tz.localize(datetime.combine(date, store_open))
        end_limit = melbourne_tz.localize(datetime.combine(date, store_close)) - timedelta(minutes=duration)

        available_times = []
        time_map = {}

        while slot_time <= end_limit:
            display = slot_time.strftime("%I:%M %p")
            available_times.append(display)
            time_map[display] = slot_time
            slot_time += timedelta(minutes=15)

        selected_time_str = st.selectbox("🕒 Available Time", options=["-- Please select a time --"] + available_times)

        confirm = st.form_submit_button("✅ Confirm Booking")

        if confirm:
            if not selected_time_str or selected_time_str == "-- Please select a time --":
                st.error("❗ Please select a time before confirming.")
                return

            selected_dt = time_map.get(selected_time_str)
            if not selected_dt:
                st.error("❌ Invalid time selected.")
                return

            if not email.strip():
                st.error("📧 Please enter your email address.")
                return
            if not phone.strip():
                st.error("📞 Please enter your phone number.")
                return

            end_dt = selected_dt + timedelta(minutes=duration)
            addon_price = sum(float(a["Price-hour"]) for a in selected_addons)
            addon_names = ", ".join(a["Type"] for a in selected_addons)

            supabase.table("bookings").insert({
                "store_id": store_id,
                "Date": selected_dt.strftime("%d/%m/%Y"),
                "start_time": selected_dt.strftime("%I:%M %p"),
                "end_time": end_dt.strftime("%I:%M %p"),
                "customer_name": name,
                "Therapist": provider,
                "phone": phone,
                "Type": service_type,
                "add_on": addon_names,
                "Add-on Price": addon_price
            }).execute()

            send_confirmation_email(name, phone, email, service_type, provider, date, selected_dt, end_dt, note, addon_names)
            st.success(f"🎉 Booking confirmed on {date.strftime('%d/%m/%Y')} at {selected_time_str} with {provider}")

# ------------------ Run ------------------
booking_page()
