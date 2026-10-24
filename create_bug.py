import os
import json
import requests
import threading
from flask import Flask, request, jsonify
from requests.auth import HTTPBasicAuth

app = Flask(__name__)

JIRA_URL = os.getenv("JIRA_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")
BOARD_ID = os.getenv("JIRA_BOARD_ID", "1")

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN) if JIRA_EMAIL and JIRA_API_TOKEN else None
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def get_active_sprint_id():
    """Запрашивает ID активного спринта из Jira"""
    if not JIRA_URL or not auth:
        return None
    url = f"{JIRA_URL.rstrip('/')}/rest/agile/1.0/board/{BOARD_ID}/sprint?state=active"
    try:
        res = requests.get(url, headers=headers, auth=auth, timeout=5)
        if res.status_code == 200:
            sprints = res.json().get("values", [])
            if sprints:
                return sprints[0]["id"]
    except Exception as e:
        print(f"[ERROR] Ошибка получения спринта: {e}")
    return None

def process_jira_creation(user_name, text, response_url, thread_ts):
    """Фоновая функция создания тикета и отправки ответа в тред Slack"""
    summary_text = text if len(text) <= 80 else text[:77] + "..."
    summary = f"[Slack Bug] {summary_text}"
    description = f"**Автор:** @{user_name}\n\n**Описание из треда:**\n{text}"

    jira_payload = {
        "fields": {
            "project": {"key": PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Bug"}
        }
    }

    sprint_id = get_active_sprint_id()
    if sprint_id:
        jira_payload["fields"]["customfield_10020"] = sprint_id

    jira_api_url = f"{JIRA_URL.rstrip('/')}/rest/api/2/issue"
    try:
        response = requests.post(jira_api_url, json=jira_payload, headers=headers, auth=auth, timeout=10)
        print(f"[DEBUG] Ответ от Jira Status Code: {response.status_code}")

        if response.status_code in [200, 201]:
            issue_key = response.json().get("key")
            issue_url = f"{JIRA_URL.rstrip('/')}/browse/{issue_key}"
            msg = f"✅ Баг создан в Jira: <{issue_url}|{issue_key}>"
        else:
            msg = f"❌ Ошибка создания в Jira ({response.status_code}): {response.text}"
    except Exception as e:
        msg = f"❌ Ошибка сервера: {str(e)}"

    # Отправляем ответ в Slack
    if response_url:
        slack_headers = {"Content-Type": "application/json"}
        slack_payload = {
            "text": msg,
            "response_type": "in_channel"
        }
        # Если есть thread_ts, направляем ответ именно в тред этого сообщения
        if thread_ts:
            slack_payload["thread_ts"] = thread_ts

        res = requests.post(response_url, json=slack_payload, headers=slack_headers, timeout=5)
        print(f"[DEBUG] Ответ Slack на response_url Code: {res.status_code}")

@app.route("/slack/create-bug", methods=["POST"])
def handle_slack_shortcut():
    thread_ts = None
    response_url = None
    user_name = "Slack User"
    text = "Без текста"

    if "payload" in request.form:
        payload_data = json.loads(request.form["payload"])
        user_name = payload_data.get("user", {}).get("username", "Slack User")
        message_data = payload_data.get("message", {})
        text = message_data.get("text", "Без текста")
        response_url = payload_data.get("response_url")
        
        # Определение родительского треда:
        # Если тред уже существует, берем thread_ts. Если нет, берем timestamp самого сообщения (ts)
        thread_ts = message_data.get("thread_ts") or message_data.get("ts")

    # Фоновая обработка
    threading.Thread(
        target=process_jira_creation, 
        args=(user_name, text, response_url, thread_ts)
    ).start()

    # Мгновенный ответ Slack
    return jsonify({"response_type": "ephemeral", "text": "⏳ Создаю баг в Jira..."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
