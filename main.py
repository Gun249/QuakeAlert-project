import requests
from datetime import datetime
from dotenv import load_dotenv
import os
import urllib.parse
import schedule
import time

load_dotenv()
Line_access_Token = os.getenv('line_token')

# ประเทศในอาเซียน
target_countries = [
    "thailand", "myanmar", "burma", "laos", "cambodia", "vietnam",
    "malaysia", "singapore", "indonesia", "philippines",
    "brunei", "timor-leste", "east timor"
]

SENT_IDS_FILE = "sent_quake_ids.txt"


def load_sent_ids():
    if not os.path.exists(SENT_IDS_FILE):
        return set()
    with open(SENT_IDS_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())


def save_sent_id(quake_id):
    with open(SENT_IDS_FILE, "a") as f:
        f.write(f"{quake_id}\n")


# ส่ง Flex Message (Carousel หรือ Bubble)
def broadcast_flex_message(contents, alt_text="แจ้งเตือนแผ่นดินไหว! / Earthquake Alert!"):
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {Line_access_Token}'
    }
    body = {
        "messages": [
            {
                "type": "flex",
                "altText": alt_text,
                "contents": contents
            }
        ]
    }
    response = requests.post(url, headers=headers, json=body)
    if response.status_code == 200:
        print("✅ ส่ง Flex message สำเร็จ")
    else:
        print("❌ Flex message error:", response.text)


# สร้าง Flex Message (Bubble)
def build_flex_message(place, mag, local_time, lat, lon):
    search_query = urllib.parse.quote(f"แผ่นดินไหว {place}")
    map_query = urllib.parse.quote(f"{lat},{lon}")
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "📢 แจ้งเตือนแผ่นดินไหว! / Earthquake Alert!",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#B71C1C"
                },
                {
                    "type": "text",
                    "text": f"📍 พิกัด / Location: {place}",
                    "wrap": True
                },
                {
                    "type": "text",
                    "text": f"📏 ขนาด / Magnitude: {mag} ริกเตอร์"
                },
                {
                    "type": "text",
                    "text": f"🕒 เวลา / Time: {local_time}"
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#D32F2F",
                    "action": {
                        "type": "uri",
                        "label": "🗺️ ดูแผนที่ / View Map",
                        "uri": f"https://www.google.com/maps/search/?api=1&query={map_query}"
                    }
                },
                {
                    "type": "button",
                    "style": "link",
                    "action": {
                        "type": "uri",
                        "label": "📰 อ่านข่าว / More News",
                        "uri": f"https://www.google.com/search?q={search_query}"
                    }
                }
            ]
        }
    }


def get_country_from_place(place):
    try:
        if ',' in place:
            return place.split(",")[-1].strip().lower()
        return place.strip().lower()
    except Exception:
        return ""


def reverse_geocode(lat, lon):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lon, "format": "json"}
        headers = {"User-Agent": "EarthquakeBot/1.0 (your_email@example.com)"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("address", {}).get("country", "").lower()
    except Exception as e:
        print("⚠️ Reverse geocoding error:", e)
    return ""


def main():
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "orderby": "time",
        "limit": 10,
        "minmagnitude": 3
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"❌ ไม่สามารถดึงข้อมูลได้: {response.status_code}")
        return

    try:
        data = response.json()
        print("🌏 ตรวจสอบแผ่นดินไหวล่าสุด...\n")
        sent_ids = load_sent_ids()

        bubbles = []
        latest_time = None

        for quake in data.get("features", []):
            try:
                quake_id = quake.get("id")
                if quake_id in sent_ids:
                    continue

                props = quake.get("properties", {})
                geometry = quake.get("geometry", {})
                coordinates = geometry.get("coordinates", [])

                place = str(props.get("place") or "ไม่ทราบตำแหน่ง")
                mag = props.get("mag")
                timestamp = props.get("time")
                lon = coordinates[0] if len(coordinates) > 0 else None
                lat = coordinates[1] if len(coordinates) > 1 else None

                if None in [mag, timestamp, lat, lon]:
                    print(f"⚠️ ข้ามรายการ (ข้อมูลไม่ครบ): {place}")
                    continue

                country = get_country_from_place(place)
                if not country or country not in target_countries:
                    country = reverse_geocode(lat, lon)

                if country in target_countries:
                    if latest_time is None:
                        latest_time = timestamp
                    elif abs(timestamp - latest_time) > 20 * 60 * 1000:
                        continue

                    local_time = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    bubble = build_flex_message(place, mag, local_time, lat, lon)
                    bubbles.append(bubble)
                    save_sent_id(quake_id)

            except Exception as e:
                print("❌ ERROR ในรายการ:", e)

        if bubbles:
            if len(bubbles) == 1:
                broadcast_flex_message(bubbles[0])
            else:
                flex = {"type": "carousel", "contents": bubbles[:10]}
                broadcast_flex_message(flex, alt_text="แจ้งเตือนแผ่นดินไหวหลายรายการ! / Multiple Earthquake Alerts!")

    except Exception as e:
        print("❌ อ่านข้อมูล JSON ไม่ได้:", e)


# เรียกใช้งานทุก 5 นาที
schedule.every(5).minutes.do(main)

print("🌀 เริ่มต้นระบบแจ้งเตือนแผ่นดินไหวทุก 5 นาที...\n")

while True:
    schedule.run_pending()
    time.sleep(1)
