import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from io import BytesIO

# --- Streamlit Secrets üzerinden Jira erişimi ---
EMAIL = st.secrets["JIRA_EMAIL"]
API_TOKEN = st.secrets["JIRA_API_TOKEN"]
DOMAIN = st.secrets["JIRA_DOMAIN"]

auth = HTTPBasicAuth(EMAIL, API_TOKEN)
headers = {"Accept": "application/json"}

# --- Jira'dan veri çekme ---
@st.cache_data
def fetch_issues(jql, max_results=1000):
    url = f"{DOMAIN}/rest/api/3/search"
    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "summary,status,issuetype,parent,created,customfield_10011,customfield_10043"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Hata: {response.status_code} - {response.text}")
        return {}

# --- Başlık ve genel ayar ---
st.set_page_config(page_title="Jira Vulnerability Dashboard", layout="wide")
st.title("🔐 Vulnerability Management Dashboard")

with st.spinner("Jira'dan veri alınıyor..."):
    data = fetch_issues('project = VM ORDER BY created DESC')

# --- Veri işleme ---
issues = data.get("issues", [])
rows = []
for issue in issues:
    fields = issue["fields"]
    rows.append({
        "Key": issue["key"],
        "Summary": fields["summary"],
        "Status": fields["status"]["name"],
        "Issue Type": fields["issuetype"]["name"],
        "Parent": fields["parent"]["key"] if "parent" in fields else "",
        "Epic Link": fields.get("customfield_10011", ""),
        "Created": fields["created"][:10],
        "Oncelik": fields.get("customfield_10043", "Bilinmiyor")
    })

df = pd.DataFrame(rows)

if not df.empty:
    df["Created"] = pd.to_datetime(df["Created"])
else:
    st.warning("Hiçbir kayıt bulunamadı. Lütfen proje key'inizi ve filtreleri kontrol edin.")
    st.stop()

# --- Filtreleme paneli ---
st.sidebar.header("🔎 Filtreleme")
issue_types = st.sidebar.multiselect("Issue Type", df["Issue Type"].unique(), default=list(df["Issue Type"].unique()))
status_filter = st.sidebar.multiselect("Status", df["Status"].unique(), default=list(df["Status"].unique()))
oncelik_filter = st.sidebar.multiselect("Öncelik", df["Oncelik"].unique(), default=list(df["Oncelik"].unique()))
show_only_subtasks = st.sidebar.checkbox("Sadece Subtask'ları Göster", value=False)

min_date, max_date = df["Created"].min(), df["Created"].max()
date_range = st.sidebar.date_input("Tarih Aralığı", (min_date, max_date))

# --- Filtreleri uygula ---
filtered_df = df[
    (df["Issue Type"].isin(issue_types)) &
    (df["Status"].isin(status_filter)) &
    (df["Oncelik"].isin(oncelik_filter)) &
    (df["Created"] >= pd.to_datetime(date_range[0])) &
    (df["Created"] <= pd.to_datetime(date_range[1]))
]

# --- Subtask filtresi ---
if show_only_subtasks:
    filtered_df = filtered_df[filtered_df["Parent"] != ""]

# --- Detaylı tablo ---
st.subheader("📋 Detaylı Tablo")
st.dataframe(filtered_df, use_container_width=True)

# --- Grafikler ---
st.subheader("📊 Durumlara Göre Dağılım")
st.bar_chart(filtered_df["Status"].value_counts())

st.subheader("📊 Tip Bazlı Dağılım")
st.bar_chart(filtered_df["Issue Type"].value_counts())

st.subheader("📊 Öncelik Dağılımı")
st.bar_chart(filtered_df["Oncelik"].value_counts())

# --- Epic bazlı ilerleme yüzdesi ---
st.subheader("📈 Epic Bazlı İlerleme Yüzdesi")
epic_issues = filtered_df[filtered_df["Epic Link"] != ""]

epic_summary = epic_issues.groupby("Epic Link").agg(
    total_issues=("Key", "count"),
    done_issues=("Status", lambda x: (x == "Done").sum())
).reset_index()

epic_summary["done_issues"] = pd.to_numeric(epic_summary["done_issues"], errors="coerce").fillna(0)
epic_summary["total_issues"] = pd.to_numeric(epic_summary["total_issues"], errors="coerce").fillna(0)

epic_summary["Progress (%)"] = epic_summary.apply(
    lambda row: round(100 * row["done_issues"] / row["total_issues"], 1) if row["total_issues"] > 0 else 0,
    axis=1
)

st.dataframe(epic_summary, use_container_width=True)
st.bar_chart(epic_summary.set_index("Epic Link")["Progress (%)"])

# --- Excel dışa aktarım (fixlenmiş) ---
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="JiraData")
    return output.getvalue()

excel_data = convert_df_to_excel(filtered_df)
st.download_button(
    label="⬇️ Excel olarak indir",
    data=excel_data,
    file_name="jira_raporu.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
