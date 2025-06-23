import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")
DOMAIN = os.getenv("JIRA_DOMAIN")

auth = HTTPBasicAuth(EMAIL, API_TOKEN)
headers = {"Accept": "application/json"}

def fetch_issues(jql, max_results=1000):
    url = f"{DOMAIN}/rest/api/3/search"
    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "summary,status,issuetype,parent,customfield_10011"
    }
    response = requests.get(url, headers=headers, auth=auth, params=params)
    return response.json() if response.status_code == 200 else {}
