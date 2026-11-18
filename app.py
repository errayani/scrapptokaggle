from io import BytesIO
import re
import time
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="ShifaTechno Leads & Kaggle Scraper", layout="wide"
)
st.title("📍 أداة استخراج البيانات (للتسويق و Kaggle)")

# --- القائمة الجانبية ---
with st.sidebar:
    st.header("⚙️ الإعدادات")
    api_key = st.text_input("Google Places API Key", type="password")
    max_results = st.slider("الحد الأقصى للنتائج لكل بحث", 20, 60, 60, step=20)

    st.divider()
    st.subheader("فحص الواتساب (Evolution API)")
    use_evolution = st.checkbox("تفعيل الفحص الحقيقي عبر Evolution API")
    evo_url = st.text_input(
        "رابط السيرفر (URL)",
        value="http://localhost:8080",
        disabled=not use_evolution,
    )
    evo_instance = st.text_input(
        "اسم الانستانس (Instance)", disabled=not use_evolution
    )
    evo_key = st.text_input(
        "Evolution API Key", type="password", disabled=not use_evolution
    )

# --- واجهة البحث ---
col1, col2 = st.columns(2)
with col1:
    activity = st.text_input(
        "النشاط أو المجال (مفرقين بفاصلة)",
        value="Cabinet médical, Cabinet dentaire",
    )
with col2:
    city = st.text_input("المدينة (أو المدن مفرقين بفاصلة)", value="Rabat")

filter_option = st.radio(
    "شنو الأرقام اللي بغيتي يبانو فالجدول؟",
    [
        "أرقام الواتساب المحتملة فقط (06 و 07)",
        "جميع الأرقام (06 و 07 + الفيكس 05)",
        "جميع الأماكن (حتى اللي ما عندهمش رقم - مفيد لـ Kaggle)",
    ],
    horizontal=True,
)


def clean_moroccan_phone(phone_str):
    if not phone_str or phone_str == "ما كاينش":
        return None
    digits = re.sub(r"\D", "", str(phone_str))
    if digits.startswith("0") and len(digits) == 10:
        digits = "212" + digits[1:]
    return digits if (digits.startswith("212") and len(digits) == 12) else None


def verify_whatsapp_numbers(numbers_list, url, instance, key):
    if not numbers_list:
        return set()
    endpoint = f"{url.rstrip('/')}/chat/whatsappNumbers/{instance}"
    headers = {"apikey": key, "Content-Type": "application/json"}
    try:
        res = requests.post(
            endpoint, json={"numbers": numbers_list}, headers=headers, timeout=15
        )
        return {
            item["number"] for item in res.json() if item.get("exists") is True
        }
    except Exception as e:
        st.error(f"خطأ Evolution API: {e}")
        return set()


def search_places(query, activity_label, city_label, key, limit):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key.strip(),
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.internationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount,places.location,places.primaryType,nextPageToken",
    }
    results = []
    next_page_token = None
    max_pages = (limit // 20) + 1

    for _ in range(max_pages):
        if len(results) >= limit:
            break
        payload = {"textQuery": query, "languageCode": "fr", "regionCode": "MA"}
        if next_page_token:
            payload["pageToken"] = next_page_token

        try:
            res = requests.post(
                url, json=payload, headers=headers, timeout=15
            ).json()
        except Exception as e:
            st.error(f"خطأ فالاتصال: {e}")
            break

        if "error" in res:
            st.error(f"خطأ Google API: {res['error'].get('message')}")
            break

        places = res.get("places", [])
        if not places:
            break

        for place in places:
            raw_phone = place.get(
                "internationalPhoneNumber", place.get("nationalPhoneNumber", "")
            )
            clean_phone = clean_moroccan_phone(raw_phone)
            phone_type = (
                (
                    "Mobile (06/07)"
                    if clean_phone.startswith(("2126", "2127"))
                    else "Fixe (05)"
                )
                if clean_phone
                else "Sans numéro"
            )
            loc = place.get("location", {})

            results.append({
                "الاسم": place.get("displayName", {}).get("text", ""),
                "المدينة": city_label,
                "النشاط": activity_label,
                "التصنيف الرسمي": place.get("primaryType", ""),
                "رقم الواتساب": clean_phone or "",
                "النوع": phone_type,
                "العنوان": place.get("formattedAddress", ""),
                "Latitude": loc.get("latitude"),
                "Longitude": loc.get("longitude"),
                "التقييم": place.get("rating"),
                "عدد التقييمات": place.get("userRatingCount", 0),
                "الموقع الإلكتروني": place.get("websiteUri", ""),
                "رابط واتساب مباشر": (
                    f"https://wa.me/{clean_phone}" if clean_phone else ""
                ),
            })

        next_page_token = res.get("nextPageToken")
        if not next_page_token:
            break
        time.sleep(2)

    return results


# --- زر التشغيل ---
run_btn = st.button(
    "🚀 ابدأ استخراج البيانات", type="primary", use_container_width=True
)

if run_btn:
    if not api_key:
        st.warning("⚠️ دخل Google Places API Key فالقائمة الجانبية أولا.")
    elif not activity.strip() or not city.strip():
        st.warning("⚠️ دخل النشاط والمدينة.")
    else:
        activities = [a.strip() for a in activity.split(",") if a.strip()]
        cities = [c.strip() for c in city.split(",") if c.strip()]
        tasks = [
            (f"{act} {ct}", act, ct) for ct in cities for act in activities
        ]

        all_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, (q, act_lbl, ct_lbl) in enumerate(tasks):
            status_text.text(f"🔍 جاري البحث عن: {q} ({idx + 1}/{len(tasks)})...")
            all_data.extend(
                search_places(q, act_lbl, ct_lbl, api_key, max_results)
            )
            progress_bar.progress((idx + 1) / len(tasks))

        status_text.empty()
        progress_bar.empty()

        if all_data:
            df = pd.DataFrame(all_data).drop_duplicates(
                subset=["الاسم", "العنوان"]
            )

            if (
                use_evolution
                and evo_instance
                and evo_key
                and filter_option
                != "جميع الأماكن (حتى اللي ما عندهمش رقم - مفيد لـ Kaggle)"
            ):
                with st.spinner("📱 جاري فحص الأرقام على واتساب..."):
                    phones = df[df["رقم الواتساب"] != ""][
                        "رقم الواتساب"
                    ].tolist()
                    valid_wa = verify_whatsapp_numbers(
                        phones, evo_url, evo_instance, evo_key
                    )
                    df = df[df["رقم الواتساب"].isin(valid_wa)]
            elif filter_option == "أرقام الواتساب المحتملة فقط (06 و 07)":
                df = df[df["النوع"] == "Mobile (06/07)"]
            elif filter_option == "جميع الأرقام (06 و 07 + الفيكس 05)":
                df = df[df["رقم الواتساب"] != ""]

            st.success(f"✅ تم استخراج {len(df)} سجل فريد وجاهز!")
            st.dataframe(
                df,
                column_config={
                    "رابط واتساب مباشر": st.column_config.LinkColumn(
                        "مراسلة سريعة", display_text="فتح في WhatsApp 💬"
                    )
                },
                use_container_width=True,
                hide_index=True,
            )

            c1, c2 = st.columns(2)
            with c1:
                out_xl = BytesIO()
                with pd.ExcelWriter(out_xl, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Leads")
                st.download_button(
                    "📥 تحميل نسخة التسويق (Excel)",
                    out_xl.getvalue(),
                    f"leads_{cities[0]}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True,
                )

            with c2:
                df_k = df[[
                    "الاسم",
                    "المدينة",
                    "النشاط",
                    "التصنيف الرسمي",
                    "العنوان",
                    "Latitude",
                    "Longitude",
                    "التقييم",
                    "عدد التقييمات",
                    "الموقع الإلكتروني",
                ]].copy()
                df_k.columns = [
                    "name",
                    "city",
                    "category_query",
                    "google_primary_type",
                    "address",
                    "latitude",
                    "longitude",
                    "rating",
                    "user_rating_count",
                    "website",
                ]
                df_k["has_website"] = (
                    df_k["website"].fillna("").str.strip() != ""
                )
                st.download_button(
                    "📊 تحميل نسخة Kaggle (CSV)",
                    df_k.to_csv(index=False).encode("utf-8-sig"),
                    f"morocco_{activities[0].replace(' ', '_').lower()}.csv",
                    "text/csv",
                    use_container_width=True,
                )
        else:
            st.warning("⚠️ ما تلقات حتى نتيجة!")
# END OF FILE