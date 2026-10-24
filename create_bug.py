import os
import requests
from flask import Flask, request, jsonify
from requests.auth import HTTPBasicAuth

app = Flask(__name__)

# Данные авторизации в Jira (передаются через переменные окружения)
JIRA_URL = os.getenv("JIRA_URL")  # https://your-domain.atlassian.net
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
PROJECT_KEY = os.getenv("VAMP")  # Например, 'DEV' или 'PROJ'

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {"Accept": "application/json", "Content-Type": "application/json"}


def get_active_sprint_id(board_id):
    """Получает ID текущего активного спринта"""
    url = f"{JIRA_URL}/rest/agile/1.0/board/{board_id}/sprint?state=active"
    response = requests.get(url, headers=headers, auth=auth)
    if response.status_code == 200:
        sprints = response.json().get("values", [])
        if sprints:
            return sprints[0]["id"]
    return None


@app.route("/slack/create-bug", methods=["POST"])
def handle_slack_command():
    # Slack передает данные форматом application/x-www-form-urlencoded
    data = request.form

    user_name = data.get("user_name", "Slack User")
    text = data.get("text", "Без описания")
    channel_id = data.get("channel_id")

    # Формируем заголовок и описание
    summary = f"[Slack Bug] {text[:60]}..." if len(text) > 60 else f"[Slack Bug] {text}"
    description = f"**Автор:** {user_name}\n\n**Описание из Slack:**\n{text}"

    # Получаем ID активного спринта (укажите ID вашей доски/board)
    BOARD_ID = 1
    sprint_id = get_active_sprint_id(BOARD_ID)

    # Тело запроса к Jira API
    payload = {
        "fields": {
            "project": {"key": PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Bug"}
        }
    }

    # Если найден активный спринт — привязываем задачу к нему
    if sprint_id:
        payload["fields"]["customfield_10020"] = sprint_id  # Field ID спринта в Jira (может отличаться)

    # Создаем тикет в Jira
    url = f"{JIRA_URL}/rest/api/2/issue"
    response = requests.post(url, json=payload, headers=headers, auth=auth)

    if response.status_code in [200, 201]:
        issue_key = response.json().get("key")
        issue_url = f"{JIRA_URL}/browse/{issue_key}"
        return jsonify({
            "response_type": "in_channel",
            "text": f"✅ Баг создан в Jira: <{issue_url}|{issue_key}>"
        })
    else:
        return jsonify({
            "response_type": "ephemeral",
            "text": f"❌ Ошибка создания задачи в Jira: {response.text}"
        })


if __name__ == "__main__":
    app.run(port=5000)
