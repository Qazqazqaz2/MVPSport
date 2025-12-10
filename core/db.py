import os
import sqlite3
from datetime import datetime
from typing import Dict, Any


DB_FILENAME = "tournaments.db"


def get_db_path() -> str:
    """
    Возвращает путь к файлу БД рядом с модулем core.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, DB_FILENAME)


def get_connection():
    """
    Открывает соединение с БД и инициализирует структуру при первом запуске.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """
    Создаёт таблицы, если их ещё нет.
    """
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT,
            location TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(name, date, location)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            match_uid TEXT NOT NULL,
            wrestler1 TEXT,
            wrestler2 TEXT,
            score1 INTEGER,
            score2 INTEGER,
            winner TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(tournament_id, match_uid),
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
        )
        """
    )

    conn.commit()


def _get_tournament_key(tournament_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Формирует ключ турнира на основе его метаданных.
    """
    return {
        "name": tournament_data.get("name", "").strip() or "Без имени",
        "date": tournament_data.get("date", "").strip() or None,
        "location": tournament_data.get("location", "").strip() or None,
    }


def get_or_create_tournament_id(conn: sqlite3.Connection, tournament_data: Dict[str, Any]) -> int:
    """
    Возвращает ID турнира в БД, создавая запись при необходимости.
    """
    key = _get_tournament_key(tournament_data)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id FROM tournaments
        WHERE name = ? AND (date IS ? OR date = ?) AND (location IS ? OR location = ?)
        """,
        (key["name"], key["date"], key["date"], key["location"], key["location"]),
    )
    row = cur.fetchone()
    if row:
        return row["id"]

    cur.execute(
        """
        INSERT INTO tournaments (name, date, location, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (key["name"], key["date"], key["location"], datetime.utcnow().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def save_tournament_metadata(tournament_data: Dict[str, Any]) -> None:
    """
    Гарантирует наличие записи о турнире в БД.
    Безопасно: при ошибке не ломает работу программы.
    """
    try:
        conn = get_connection()
        with conn:
            get_or_create_tournament_id(conn, tournament_data)
    except Exception as e:
        print(f"[DB] Ошибка при сохранении метаданных турнира: {e}")


def save_match_result(tournament_data: Dict[str, Any], category_name: str, match: Dict[str, Any]) -> None:
    """
    Сохраняет результат конкретного матча в БД (upsert по match_uid).
    """
    try:
        conn = get_connection()
        with conn:
            tournament_id = get_or_create_tournament_id(conn, tournament_data)
            cur = conn.cursor()

            match_uid = str(match.get("id") or f"{category_name}_{match.get('wrestler1')}_{match.get('wrestler2')}")
            wrestler1 = match.get("wrestler1")
            wrestler2 = match.get("wrestler2")
            score1 = int(match.get("score1", 0) or 0)
            score2 = int(match.get("score2", 0) or 0)
            winner = match.get("winner")
            completed = 1 if match.get("completed") else 0
            updated_at = datetime.utcnow().isoformat()

            cur.execute(
                """
                INSERT INTO matches (
                    tournament_id, category, match_uid, wrestler1, wrestler2,
                    score1, score2, winner, completed, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tournament_id, match_uid) DO UPDATE SET
                    category = excluded.category,
                    wrestler1 = excluded.wrestler1,
                    wrestler2 = excluded.wrestler2,
                    score1   = excluded.score1,
                    score2   = excluded.score2,
                    winner   = excluded.winner,
                    completed = excluded.completed,
                    updated_at = excluded.updated_at
                """,
                (
                    tournament_id,
                    category_name,
                    match_uid,
                    wrestler1,
                    wrestler2,
                    score1,
                    score2,
                    winner,
                    completed,
                    updated_at,
                ),
            )
    except Exception as e:
        print(f"[DB] Ошибка при сохранении результата матча: {e}")


def apply_db_results_to_tournament(tournament_data: Dict[str, Any]) -> None:
    """
    Обновляет структуру tournament_data на основе данных из БД:
    для каждого матча по его id/match_uid подтягивает score1/score2/winner/completed.
    Безопасно: при ошибке просто ничего не делает.
    """
    try:
        if not tournament_data or "categories" not in tournament_data:
            return

        conn = get_connection()
        with conn:
            tournament_id = get_or_create_tournament_id(conn, tournament_data)
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM matches WHERE tournament_id = ?",
                (tournament_id,),
            )
            rows = cur.fetchall()

            # Индексируем по match_uid для быстрого доступа
            db_matches = {row["match_uid"]: row for row in rows}

            for cat_name, cat_data in tournament_data.get("categories", {}).items():
                for m in cat_data.get("matches", []):
                    match_uid = str(m.get("id") or f"{cat_name}_{m.get('wrestler1')}_{m.get('wrestler2')}")
                    row = db_matches.get(match_uid)
                    if not row:
                        continue

                    # Переносим данные из БД в структуру турнира
                    m["score1"] = row["score1"] if row["score1"] is not None else 0
                    m["score2"] = row["score2"] if row["score2"] is not None else 0
                    m["winner"] = row["winner"]
                    m["completed"] = bool(row["completed"])
    except Exception as e:
        print(f"[DB] Ошибка при применении результатов из БД к tournament_data: {e}")


