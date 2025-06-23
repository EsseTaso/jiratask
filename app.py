import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from io import BytesIO

# --- Streamlit Secrets üzerinden erişim ---
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

# --- Başlat ---
st.set_page_config(page_title="Jira Vulnerability Dashboard", layout="wide")
st.title("🔐 Jira Vulnerability Dashboard")

with st.spinner("Veri çekiliyor..."):
    data = fetch_issues('project = VM ORDER BY created DESC')

# --- Veriyi işle ---
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

# --- Subtask'lara Epic Link ata ---
epic_map = {r["Key"]: [] for r in rows if r["Issue Type"] == "Epic"}
task_map = {}
subtask_map = {}

for r in rows:
    if r["Issue Type"] != "Sub-task" and r["Issue Type"] != "Epic":
        task_map[r["Key"]] = r
        if r["Epic Link"]:
            epic_map.setdefault(r["Epic Link"], []).append(r["Key"])
    elif r["Issue Type"] == "Sub-task" and r["Parent"]:
        subtask_map.setdefault(r["Parent"], []).append(r)

# Subtask'lara Epic Link bağla
for r in rows:
    if r["Issue Type"] == "Sub-task" and r["Parent"] in task_map:
        r["Epic Link"] = task_map[r["Parent"]]["Epic Link"]

df = pd.DataFrame(rows)

if df.empty:
    st.warning("Veri bulunamadı.")
    st.stop()
else:
    df["Created"] = pd.to_datetime(df["Created"])

# --- Hiyerarşik Filtreleme: Epic → Task → Subtask ---
st.sidebar.header("🧩 Epic → Task → Subtask Filtresi")

epic_keys = sorted([e for e in epic_map if e])
selected_epic = st.sidebar.selectbox("Epic Seç", epic_keys) if epic_keys else None

task_keys = epic_map.get(selected_epic, [])
selected_task = st.sidebar.selectbox("Task Seç", task_keys) if task_keys else None

subtask_list = subtask_map.get(selected_task, [])
selected_subtask = st.sidebar.selectbox(
    "Subtask Seç", [s["Key"] for s in subtask_list]) if subtask_list else None

# --- Diğer filtreler ---
st.sidebar.header("🔎 Diğer Filtreler")
issue_types = st.sidebar.multiselect("Issue Type", df["Issue Type"].unique(), default=list(df["Issue Type"].unique()))
status_filter = st.sidebar.multiselect("Status", df["Status"].unique(), default=list(df["Status"].unique()))
oncelik_filter = st.sidebar.multiselect("Öncelik", df["Oncelik"].unique(), default=list(df["Oncelik"].unique()))
min_date, max_date = df["Created"].min(), df["Created"].max()
date_range = st.sidebar.date_input("Tarih Aralığı", (min_date, max_date))

# --- Filtreleri uygula ---
filtered_df = df.copy()

if selected_epic:
    filtered_df = filtered_df[filtered_df["Epic Link"] == selected_epic]

if selected_task:
    filtered_df = filtered_df[(filtered_df["Key"] == selected_task) | (filtered_df["Parent"] == selected_task)]

if selected_subtask:
    filtered_df = filtered_df[filtered_df["Key"] == selected_subtask]

filtered_df = filtered_df[
    (filtered_df["Issue Type"].isin(issue_types)) &
    (filtered_df["Status"].isin(status_filter)) &
    (filtered_df["Oncelik"].isin(oncelik_filter)) &
    (filtered_df["Created"] >= pd.to_datetime(date_range[0])) &
    (filtered_df["Created"] <= pd.to_datetime(date_range[1]))
]

# --- Tablolar ve grafikler ---
st.subheader("📋 Seçilen Kayıtlar")
st.dataframe(filtered_df, use_container_width=True)

st.subheader("📊 Durum Dağılımı")
st.bar_chart(filtered_df["Status"].value_counts())

st.subheader("📊 Tip Dağılımı")
st.bar_chart(filtered_df["Issue Type"].value_counts())

st.subheader("📊 Öncelik Dağılımı")
st.bar_chart(filtered_df["Oncelik"].value_counts())

# --- Epic Bazlı İlerleme ---
st.subheader("📈 Epic Bazlı İlerleme Yüzdesi")

epic_issues = df[df["Epic Link"].notna() & (df["Epic Link"] != "")]
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

# --- Excel Export ---
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
