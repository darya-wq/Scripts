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

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_Дело в том, что стандартные **Slash Commands** (`/bug`) в Slack **по определению не умеют работать внутри тредов** — сам Slack штатно запрещает их использование в ветках обсуждений (отсюда и ошибка *«/bug is not supported in threads»*).

Чтобы запускать создание задачи **прямо из треда**, вместо Slash Command нужно использовать **Shortcut (Shortcut / Message Action)**. 

Это настраивается за 2 минуты в том же приложении Slack App и выглядит для пользователя даже удобнее.

---

### Как перенастроить на работу в тредах (Message Shortcut)

#### Шаг 1. Создаем Shortcut в Slack App

1. Перейдите на [api.slack.com/apps](https://api.slack.com/apps) и открыйте ваше приложение.
2. В левом меню выберите раздел **Interactivity & Shortcuts**.
3. Убедитесь, что переключатель **Interactivity** включен (находится в положение *On*).
4. В поле **Request URL** вставьте вашу ссылку с Render:
   `https://ВАШ_СЕРВИС.onrender.com/slack/create-bug`
5. Прокрутите ниже до раздела **Shortcuts** и нажмите **Create New Shortcut**.
6. Выберите вариант **On messages** (Именно он позволяет вызывать действие из любого сообщения/треда) и нажмите *Next*.
7. Заполните поля:
   * **Name:** `Create Bug in Jira`
   * **Short Description:** Создать дефект в Jira из этого сообщения
   * **Callback ID:** `create_bug_shortcut`
8. Нажмите **Save**.
9. Перейдите в левом меню в **Install App** и нажмите **Reinstall to Workspace** (переустановите приложение).

---

#### Шаг 2. Как теперь это использовать в Slack

1. Зайдите в любой **тред** в Slack.
2. Наведите мышку на сообщение, из которого хотите сделать баг-репорт.
3. Нажмите на **три точки (`...`)** в правом углу этого сообщения (или выберите *More actions*).
4. В выпавшем списке выберите **Create Bug in Jira** (если его нет в списке сразу, нажмите *More message shortcuts...* и найдите там).

---

#### Шаг 3. Небольшое обновление в `main.py`

Так как Slack отправляет данные от Shortcut в формате `payload` (JSON внутри form-data), наш файл `main.py` нужно слегка обновить, чтобы он правильно считывал текст из сообщения треда и ссылку на него.

Замените содержимое `main.py` на GitHub на следующий код:

```python
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
headers = {"Accept": "application/json", "Content-Type": "application/json"}

def get_active_sprint_id():
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
        print(f"Ошибка получения спринта: {e}")
    return None

@app.route("/slack/create-bug", methods=["POST"])
def handle_slack_shortcut():
    # Если запрос пришел от Shortcut (Message Action)
    if "payload" in request.form:
        payload_data = json.loads(request.form["payload"])
        
        user_name = payload_data.get("user", {}).get("username", "Slack User")
        message_data = payload_data.get("message", {})
        text = message_data.get("text", "Без текста")
        
        # Ссылка на сообщение/тред
        message_url = payload_data.get("response_url", "")
    else:
        # Резервная обработка обычного POST
        user_name = request.form.get("user_name", "Slack User")
        text = request.form.get("text", "")

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
        
        if response.status_code in [200, 201]:
            issue_key = response.json().get("key")
            issue_url = f"{JIRA_URL.rstrip('/')}/browse/{issue_key}"
            return jsonify({
                "response_type": "in_channel",
                "text": f"✅ Баг создан из треда: <{issue_url}|{issue_key}>"
            })
        else:
            return jsonify({
                "response_type": "ephemeral",
                "text": f"❌ Ошибка Jira API: {response.text}"
            })
    except Exception as e:
        return jsonify({"response_type": "ephemeral", "text": f"❌ Ошибка: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
