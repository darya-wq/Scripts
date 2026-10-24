def process_jira_creation(user_name, text, response_url):
    """Фоновая функция создания тикета и ответа в Slack"""
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

    # Отправляем ответ обратно в Slack через response_url с правильными заголовками
    if response_url:
        slack_headers = {"Content-Type": "application/json"}
        slack_payload = {
            "text": msg,
            "response_type": "in_channel"  # Видно всем в канале/треде
        }
        res = requests.post(response_url, json=slack_payload, headers=slack_headers, timeout=5)
        print(f"[DEBUG] Ответ Slack на response_url Code: {res.status_code}, Body: {res.text}")
