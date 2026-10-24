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

def process_jira_creation(user_name, text, response_url, thread_ts, slack_msg_link, issue_type="Bug"):
    """Фоновая функция создания задачи любого типа (Bug / Task / Art)"""
    
    # 1. Берём только первую строку сообщения (до переноса строки)
    first_line = text.split("\n")[0].strip()
    
    # 2. Если первая строка больше 150 символов, обрезаем и добавляем троеточие
    if len(first_line) > 150:
        summary_text = first_line[:147] + "..."
    else:
        summary_text = first_line

    # На случай если первой строкой был только перенос строки
    if not summary_text:
        summary_text = "Новая задача из Slack"
    
    icons = {
        "Bug": "🐛",
        "Task": "📌",
        "Art": "🎨"
    }
    icon = icons.get(issue_type, "📋")
    summary = f"[Slack {issue_type}] {summary_text}"
    
    description = f"**Автор:** @{user_name}\n"
    if slack_msg_link:
        description += f"**Ссылка на Slack:** {slack_msg_link}\n\n"
    else:
        description += "\n"
    description += f"**Описание из треда:**\n{text}"

    jira_payload = {
        "fields": {
            "project": {"key": PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type}
        }
    }

    sprint_id = get_active_sprint_id()
    if sprint_id:
        jira_payload["fields"]["customfield_10020"] = sprint_id

    jira_api_url = f"{JIRA_URL.rstrip('/')}/rest/api/2/issue"
    try:
        response = requests.post(jira_api_url, json=jira_payload, headers=headers, auth=auth, timeout=10)
        print(f"[DEBUG] [{issue_type}] Ответ от Jira Status Code: {response.status_code}")

        if response.status_code in [200, 201]:
            issue_key = response.json().get("key")
            issue_url = f"{JIRA_URL.rstrip('/')}/browse/{issue_key}"
            msg = f"{icon} {issue_type} создан в Jira: <{issue_url}|{issue_key}>"
        else:
            msg = f"❌ Ошибка создания в Jira ({response.status_code}): {response.text}"
    except Exception as e:
        msg = f"❌ Ошибка сервера: {str(e)}"

    if response_url:
        slack_headers = {"Content-Type": "application/json"}
        slack_payload = {
            "text": msg,
            "response_type": "in_channel"
        }
        if thread_ts:
            slack_payload["thread_ts"] = thread_ts

        requests.post(response_url, json=slack_payload, headers=slack_headers, timeout=5)

@app.route("/slack/create-bug", methods=["POST"])
def handle_slack_interactivity():
    """Единый эндпоинт для обработки всех типов тикетов (Bug/Task/Art)"""
    thread_ts = None
    response_url = None
    user_name = "Slack User"
    text = "Без текста"
    slack_msg_link = None
    issue_type = "Bug"

    if "payload" in request.form:
        payload_data = json.loads(request.form["payload"])
        
        callback_id = payload_data.get("callback_id", "")
        if callback_id == "create_task":
            issue_type = "Task"
        elif callback_id == "create_art":
            issue_type = "Art"
        elif callback_id == "create_bug":
            issue_type = "Bug"

        user_name = payload_data.get("user", {}).get("username", "Slack User")
        message_data = payload_data.get("message", {})
        text = message_data.get("text", "Без текста")
        response_url = payload_data.get("response_url")
        
        ts = message_data.get("ts")
        thread_ts = message_data.get("thread_ts") or ts

        team_domain = payload_data.get("team", {}).get("domain")
        channel_id = payload_data.get("channel", {}).get("id")
        
        if team_domain and channel_id and ts:
            clean_ts = ts.replace(".", "")
            slack_msg_link = f"https://{team_domain}.slack.com/archives/{channel_id}/p{clean_ts}"
            if message_data.get("thread_ts"):
                slack_msg_link += f"?thread_ts={message_data.get('thread_ts')}"

    threading.Thread(
        target=process_jira_creation, 
        args=(user_name, text, response_url, thread_ts, slack_msg_link, issue_type)
    ).start()

    return jsonify({"response_type": "ephemeral", "text": f"⏳ Создаю {issue_type} в Jira..."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
