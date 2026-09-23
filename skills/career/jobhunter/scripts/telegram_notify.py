"""
Отправка уведомлений о вакансиях в Telegram через Bot API.

Нужны переменные окружения:
  TELEGRAM_BOT_TOKEN — токен от @BotFather
  TELEGRAM_CHAT_ID   — id чата, куда слать (ваш личный чат с ботом; узнать можно,
                        написав боту что угодно и открыв
                        https://api.telegram.org/bot<TOKEN>/getUpdates)

Запуск для проверки:
    python telegram_notify.py --test
"""

import argparse
import os

import requests

API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _token_and_chat():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Не заданы TELEGRAM_BOT_TOKEN и/или TELEGRAM_CHAT_ID")
    return token, chat_id


def send_message(text: str) -> dict:
    token, chat_id = _token_and_chat()
    url = API_BASE.format(token=token, method="sendMessage")
    resp = requests.post(
        url,
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def send_document(file_path: str, caption: str = "") -> dict:
    token, chat_id = _token_and_chat()
    url = API_BASE.format(token=token, method="sendDocument")
    with open(file_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"document": f},
            timeout=30,
        )
    resp.raise_for_status()
    return resp.json()


def notify_vacancy(vacancy: dict, score: int, reason: str, cover_letter: str, applied: bool, apply_detail: str):
    status_line = "✅ Отклик отправлен автоматически" if applied else "✉️ Черновик готов — отправьте сами"
    text = (
        f"<b>{vacancy.get('title', '')}</b>\n"
        f"{vacancy.get('company', '')} · {vacancy.get('salary', '') or 'зарплата не указана'}\n"
        f"Источник: {vacancy.get('source', '')}\n"
        f"Соответствие: {score}/100 — {reason}\n"
        f"{vacancy.get('url', '')}\n\n"
        f"<b>Сопроводительное:</b>\n{cover_letter}\n\n"
        f"{status_line}"
        + (f"\n({apply_detail})" if apply_detail else "")
    )
    return send_message(text)


def notify_daily_summary(checked: int, matched: int):
    return send_message(f"За сегодня проверено вакансий: {checked}, подходящих найдено: {matched}.")


def notify_job_search_completed(stats: dict):
    """
    Финальное событие workflow: JOB_SEARCH_COMPLETED (см. PROTOCOL.md).
    stats — dict вида {"checked": 42, "matched": 8, "great": 3, "applied": 1}.
    Это то же сообщение, которое JobHunter Workflow отдаёт "наверх" в Hermes,
    а Hermes пересылает в Telegram (в реальной интеграции с Hermes этот вызов
    делает сам Hermes; если run.py запускается напрямую — шлём сами).
    """
    text = (
        "🔎 <b>JOB_SEARCH_COMPLETED</b>\n"
        f"Проверено вакансий: {stats.get('checked', 0)}\n"
        f"Подходят: {stats.get('matched', 0)}\n"
        f"Отлично подходят: {stats.get('great', 0)}\n"
        f"Откликов отправлено автоматически: {stats.get('applied', 0)}"
    )
    return send_message(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Отправить тестовое сообщение")
    args = parser.parse_args()
    if args.test:
        result = send_message("JobHunter: тестовое сообщение, всё работает 🎯")
        print(result)
