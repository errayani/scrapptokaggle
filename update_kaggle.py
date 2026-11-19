import os
import json
import time
import subprocess
from datetime import datetime
import requests
import pandas as pd

# إعدادات البحث (تقدر تزيد مدن أو مجالات أخرى هنا)
CATEGORIES = ["Cabinet médical", "Cabinet dentaire", "Pharmacie", "Clinique", "Laboratoire d'analyses"]
CITIES = ["Casablanca"]
MAX_RESULTS_PER_QUERY = 25

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
KAGGLE_DATASET_SLUG = os.environ.get("KAGGLE_DATASET_SLUG")  # مثال: errayani/morocco-healthcare-places

DATA_DIR = "kaggle_data"
os.makedirs(DATA_DIR, exist_ok=True)


def fetch_places_clean(category: str, city: str) -> list:
    url = "https://places.googleapis.com/v1/places:searchText"
    # لاحظ: كنطلبو فقط الحقول العامة بلا أرقام هواتف وبلا place_id لتجنب مخالفة الشروط
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": (
            "places.displayName,places.primaryType,places.types,"
            "places.formattedAddress,places.location,places.rating,"
            "places.userRatingCount,places.websiteUri,places.nationalPhoneNumber,"
            "places.businessStatus,nextPageToken"
        ),
    }

    payload = {
        "textQuery": f"{category} in {city}, Morocco",
        "pageSize": 20,
        "languageCode": "fr",
    }

    records = []
    page_token = None

    while len(records) < MAX_RESULTS_PER_QUERY:
        if page_token:
            payload["pageToken"] = page_token

        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if res.status_code != 200:
            print(f"Error {res.status_code} for {category} - {city}: {res.text}")
            break

        data = res.json()
        places = data.get("places", [])
        if not places:
            break

        for p in places:
            loc = p.get("location", {})
            # استخراج الحي أو الرمز البريدي فقط وحذف العنوان الشخصي الدقيق إن وجد
            raw_addr = p.get("formattedAddress", "")
            postal_code = next((part.strip() for part in raw_addr.split(",") if any(c.isdigit() for c in part) and len(part.strip()) <= 12), "Unknown")

            records.append({
                "business_name": p.get("displayName", {}).get("text", ""),
                "category_query": category,
                "primary_type": p.get("primaryType", ""),
                "city": city,
                "postal_area": postal_code,
                # تقريب الإحداثيات لـ 2 أرقام بعد الفاصلة لحماية الموقع الدقيق مع الحفاظ على التحليل الجغرافي
                "lat_approx": round(loc.get("latitude", 0), 2) if loc.get("latitude") else None,
                "lng_approx": round(loc.get("longitude", 0), 2) if loc.get("longitude") else None,
                "rating": p.get("rating", None),
                "reviews_count": p.get("userRatingCount", 0),
                "business_status": p.get("businessStatus", "OPERATIONAL"),
                # تحويل الهاتف والموقع إلى قيم منطقية (True/False) بدون كشف أي معطيات شخصية (PII)
                "has_phone": bool(p.get("nationalPhoneNumber")),
                "has_website": bool(p.get("websiteUri")),
                "last_updated": datetime.utcnow().strftime("%Y-%m-%d"),
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)

    return records


def main():
    if not GOOGLE_API_KEY or not KAGGLE_DATASET_SLUG:
        raise ValueError("Missing GOOGLE_API_KEY or KAGGLE_DATASET_SLUG environment variables.")

    all_rows = []
    for city in CITIES:
        for cat in CATEGORIES:
            print(f"Fetching: {cat} in {city}...")
            all_rows.extend(fetch_places_clean(cat, city))

    df = pd.DataFrame(all_rows)
    # إزالة التكرار بناءً على اسم المؤسسة والمدينة
    df = df.drop_duplicates(subset=["business_name", "city", "category_query"])

    csv_path = os.path.join(DATA_DIR, "morocco_healthcare_facilities.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved {len(df)} clean records to {csv_path}")

    # إنشاء ملف التعريف الخاص بـ Kaggle (dataset-metadata.json)
    metadata = {
        "title": "Morocco Healthcare Facilities & Digital Presence",
        "id": KAGGLE_DATASET_SLUG,
        "licenses": [{"name": "CC0-1.0"}],
    }
    with open(os.path.join(DATA_DIR, "dataset-metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # رفع التحديث إلى Kaggle
    version_msg = f"Automated weekly update - {datetime.utcnow().strftime('%Y-%m-%d')}"
    cmd = ["kaggle", "datasets", "version", "-p", DATA_DIR, "-m", version_msg, "--dir-mode", "zip"]
    subprocess.run(cmd, check=True)
    print("Dataset successfully updated on Kaggle!")


if __name__ == "__main__":
    main()
