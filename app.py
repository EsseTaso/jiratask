import streamlit as st
from jira_api import fetch_issues
import pandas as pd

st.title("🔐 Vulnerability Management Dashboard")

with st.spinner("Veriler Jira'dan çekiliyor..."):
    data = fetch_issues('project = "Vulnerability Management" ORDER BY created DESC')

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
        "Epic Link": fields.get("customfield_10011", "")
    })

df = pd.DataFrame(rows)
st.dataframe(df)
