"""
Database — компонент "сохранение / статус / история" из архитектуры JobHunter.
Обычный код, SQLite, без ИИ.

Хранит:
  - vacancies: сами вакансии + текущий статус
  - history: журнал переходов статуса (аудит: когда, что, почему)

Статусы (status): new -> scored -> (rejected_by_rules | sent_to_llm) ->
                   (rejected_by_llm | notified | applied)

Использование:
    from state import State
    db = State()
    if not db.seen("hh:123456"):
        db.upsert_vacancy(vacancy)
        db.set_status("hh:123456", "scored", score=82, note="rule-based")
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parent.parent / "state.db"


class State:
    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vacancies (
                id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                company TEXT,
                url TEXT,
                raw_json TEXT,
                score INTEGER,
                status TEXT,
                first_seen_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vacancy_id TEXT,
                status TEXT,
                score INTEGER,
                note TEXT,
                at TEXT
            )
            """
        )
        self.conn.commit()

    # -- дедупликация / чтение --------------------------------------------------
    def seen(self, vacancy_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM vacancies WHERE id = ?", (vacancy_id,))
        return cur.fetchone() is not None

    def get(self, vacancy_id: str) -> dict | None:
        cur = self.conn.execute("SELECT raw_json, score, status FROM vacancies WHERE id = ?", (vacancy_id,))
        row = cur.fetchone()
        if not row:
            return None
        raw, score, status = row
        return {"vacancy": json.loads(raw), "score": score, "status": status}

    # -- запись -------------------------------------------------------------
    def upsert_vacancy(self, vacancy: dict, status: str = "new"):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO vacancies (id, source, title, company, url, raw_json, score, status, first_seen_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (
                vacancy["id"], vacancy.get("source", ""), vacancy.get("title", ""),
                vacancy.get("company", ""), vacancy.get("url", ""),
                json.dumps(vacancy, ensure_ascii=False), status, now, now,
            ),
        )
        self.conn.commit()
        self._log(vacancy["id"], status, 0, "вакансия сохранена")

    def set_status(self, vacancy_id: str, status: str, score: int = 0, note: str = ""):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE vacancies SET status = ?, score = ?, updated_at = ? WHERE id = ?",
            (status, score, now, vacancy_id),
        )
        self.conn.commit()
        self._log(vacancy_id, status, score, note)

    def _log(self, vacancy_id: str, status: str, score: int, note: str):
        self.conn.execute(
            "INSERT INTO history (vacancy_id, status, score, note, at) VALUES (?, ?, ?, ?, ?)",
            (vacancy_id, status, score, note, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    # -- совместимость с более старым API (использовалось в первой версии) --
    def mark_seen(self, vacancy_id: str, source: str = "", score: int = 0, status: str = "processed"):
        """Оставлено для обратной совместимости. Предпочтительно: upsert_vacancy + set_status."""
        self.conn.execute(
            "INSERT OR REPLACE INTO vacancies (id, source, title, company, url, raw_json, score, status, first_seen_at, updated_at) "
            "VALUES (?, ?, '', '', '', '{}', ?, ?, ?, ?)",
            (vacancy_id, source, score, status, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    # -- статистика (для JOB_SEARCH_COMPLETED) -------------------------------
    def stats_today(self) -> dict:
        today = datetime.now(timezone.utc).date().isoformat()
        cur = self.conn.execute(
            "SELECT status, COUNT(*) FROM vacancies WHERE updated_at LIKE ? GROUP BY status",
            (f"{today}%",),
        )
        return dict(cur.fetchall())

    def close(self):
        self.conn.close()
