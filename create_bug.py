import os
import json
import requests
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
    """Получает ID активного спринта"""
    if not JIRA_URL or not auth:
        return None
    url = f"{JIRA_URL.rstrip('/')}/rest/agile/1.0/board/{BOARD_ID}/sprint?state=active"
    try:
        res = requests.get(url, headers=headers, auth=auth, timeout=5)
        print(f"[DEBUG] Sprint Status Code: {res.status_code}")
        if res.status_code == 200:
            sprints = res.json().get("values", [])
            if sprints:
                return sprints[0]["id"]
    except Exception as e:
        print(f"[ERROR] Ошибка спринта: {e}")
    return None

@app.route("/slack/create-bug", methods=["POST"])
def handle_slack_shortcut():
    print("[DEBUG] Получен новый запрос из Slack")
    
    # 1. Считываем данные из Slack
    if "payload" in request.form:
        payload_data = json.loads(request.form["payload"])
        user_name = payload_data.get("user", {}).get("username", "Slack User")
        message_data = payload_data.get("message", {})
        text = message_data.get("text", "Без текста")
    else:
        user_name = request.form.get("user_name", "Slack User")
        text = request.form.get("text", "Без текста")

    summary_text = text if len(text) <= 80 else text[:77] + "..."
    summary = f"[Slack Bug] {summary_text}"
    description = f"**Автор:** @{user_name}\n\n**Описание из треда:**\n{text}"

    # 2. Формируем тело для Jira
    jira_payload = {
        "fields": {
            "project": {"key": PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Bug"}
        }
    }

    # 3. Пробуем привязать активный спринт
    sprint_id = get_active_sprint_id()
    if sprint_id:
        jira_payload["fields"]["customfield_10020"] = sprint_id
        print(f"[DEBUG] Найден активный спринт ID: {sprint_id}")

    # 4. Отправляем запрос в Jira
    jira_api_url = f"{JIRA_URL.rstrip('/')}/rest/api/2/issue"
    try:
        print(f"[DEBUG] Отправка запроса в Jira: {jira_api_url}")
        response = requests.post(jira_api_url, json=jira_payload, headers=headers, auth=auth, timeout=10)
        
        print(f"[DEBUG] Ответ от Jira Status Code: {response.status_code}")
        print(f"[DEBUG] Текст ответа от Jira: {response.text}")

        if response.status_code in [200, 201]:
            issue_key = response.json().get("key")
            issue_url = f"{JIRA_URL.rstrip('/')}/browse/{issue_key}"
            return jsonify({
                "response_type": "in_channel",
                "text": f"✅ Баг создан в Jira: <{issue_url}|{issue_key}>"
            })
        else:
            return jsonify({
                "response_type": "ephemeral",
                "text": f"❌ Ошибка Jira ({response.status_code}): {response.text}"
            })
    except Exception as e:
        print(f"[ERROR] Исключение при отправке в Jira: {e}")
        return jsonify({"response_type": "ephemeral", "text": f"❌ Ошибка сервера: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
