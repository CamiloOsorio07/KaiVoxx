import requests
from config.settings import SYSTEM_PROMPT, GROQ_API_URL
import os
import logging

log = logging.getLogger('kaivoxx.groq')
conversation_history = {}

def add_to_history(context_key: str, role: str, content: str, max_len: int = 10):
    history = conversation_history.setdefault(context_key, [])
    if not history:
        history.append({"role": "system", "content": SYSTEM_PROMPT})
    history.append({"role": role, "content": content})
    conversation_history[context_key] = history[-max_len:]

def groq_chat_response(context_key: str, user_prompt: str):
    add_to_history(context_key, "user", user_prompt)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in conversation_history.get(context_key, []):
        if msg["role"] in ("user","assistant"):
            messages.append(msg)
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 300
    }
    headers = {"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY')}", "Content-Type": "application/json"}
    try:
        response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        add_to_history(context_key, "assistant", content)
        return content
    except Exception:
        log.exception("Error Groq IA")
        return "❌ Tuve un problema pensando… inténtalo otra vez 💜"
