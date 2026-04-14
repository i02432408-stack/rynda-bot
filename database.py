import os
import sqlite3
from datetime import datetime


DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    def get_conn():
        conn = psycopg2.connect(DATABASE_URL)
        return conn

    PLACEHOLDER = "%s"
    AUTOINCREMENT = "SERIAL PRIMARY KEY"
    IGNORE = "ON CONFLICT DO NOTHING"

else:
    def get_conn():
        conn = sqlite3.connect("bot.db")
        conn.row_factory = sqlite3.Row
        return conn

    PLACEHOLDER = "?"
    AUTOINCREMENT = "INTEGER PRIMARY KEY AUTOINCREMENT"
    IGNORE = "OR IGNORE"


def _row_to_dict(row, cursor=None):
    """Универсальный перевод строки в dict для SQLite и PostgreSQL."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):          # sqlite3.Row
        return dict(row)
    if cursor is not None:             # psycopg2 tuple
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))
    return row


def init_db():
    if DATABASE_URL:
        _init_pg()
    else:
        _init_sqlite()


def _init_sqlite():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                username  TEXT    DEFAULT '',
                full_name TEXT    DEFAULT '',
                rank      TEXT    DEFAULT 'user',
                blocked   INTEGER DEFAULT 0,
                joined_at TEXT
            );
            CREATE TABLE IF NOT EXISTS suggestions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                text        TEXT,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT,
                admin_reply TEXT
            );
            CREATE TABLE IF NOT EXISTS admin_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                text        TEXT,
                status      TEXT DEFAULT 'unread',
                created_at  TEXT,
                admin_reply TEXT
            );
        """)
        try:
            conn.execute("ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN state TEXT DEFAULT NULL")
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('recruitment', '1')"
            )
            conn.commit()
        except Exception:
            pass


def _init_pg():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   BIGINT PRIMARY KEY,
                username  TEXT    DEFAULT '',
                full_name TEXT    DEFAULT '',
                rank      TEXT    DEFAULT 'user',
                blocked   INTEGER DEFAULT 0,
                joined_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT,
                text        TEXT,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT,
                admin_reply TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_messages (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT,
                text        TEXT,
                status      TEXT DEFAULT 'unread',
                created_at  TEXT,
                admin_reply TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cur.execute(
            "INSERT INTO settings (key, value) VALUES ('recruitment', '1') "
            "ON CONFLICT (key) DO NOTHING"
        )
        # Миграция колонки state
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS state TEXT DEFAULT NULL
        """)
        conn.commit()




def _exec(sql: str, params=(), fetchone=False, fetchall=False, lastrowid=False):
    """Выполняет SQL совместимо с SQLite и PostgreSQL."""
    if DATABASE_URL:
        sql = sql.replace("?", "%s")
        sql = sql.replace("INSERT OR IGNORE", "INSERT")
        sql = sql.replace("OR IGNORE", "")
        # Для INSERT с lastrowid добавляем RETURNING id
        if lastrowid and sql.strip().upper().startswith("INSERT"):
            if "RETURNING" not in sql.upper():
                sql = sql.rstrip("; ") + " RETURNING id"
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            result = None
            if lastrowid:
                row = cur.fetchone()
                result = row[0] if row else None
            elif fetchone:
                row = cur.fetchone()
                result = _row_to_dict(row, cur) if row else None
            elif fetchall:
                rows = cur.fetchall()
                result = [_row_to_dict(r, cur) for r in rows]
            conn.commit()
            return result
        finally:
            conn.close()
    else:
        conn = get_conn()
        try:
            cur = conn.execute(sql, params)
            result = None
            if lastrowid:
                result = cur.lastrowid
            elif fetchone:
                row = cur.fetchone()
                result = _row_to_dict(row) if row else None
            elif fetchall:
                result = [_row_to_dict(r) for r in cur.fetchall()]
            conn.commit()
            return result
        finally:
            conn.close()




class Database:

    def add_user(self, user_id: int, username: str, full_name: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if DATABASE_URL:
            _exec(
                "INSERT INTO users (user_id, username, full_name, joined_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (user_id) DO NOTHING",
                (user_id, username, full_name, now)
            )
        else:
            _exec(
                "INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, username, full_name, now)
            )
        _exec(
            "UPDATE users SET username=?, full_name=? WHERE user_id=?",
            (username, full_name, user_id)
        )

    def get_user(self, user_id: int):
        return _exec("SELECT * FROM users WHERE user_id=?", (user_id,), fetchone=True)

    def get_user_rank(self, user_id: int) -> str:
        row = _exec("SELECT rank FROM users WHERE user_id=?", (user_id,), fetchone=True)
        return row["rank"] if row else "user"

    def set_user_rank(self, user_id: int, rank: str):
        _exec("UPDATE users SET rank=? WHERE user_id=?", (rank, user_id))

    def get_all_users(self):
        return _exec(
            "SELECT * FROM users ORDER BY "
            "CASE rank WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 "
            "WHEN 'moderator' THEN 3 ELSE 4 END",
            fetchall=True
        ) or []

    def get_users_by_rank(self, ranks: list):
        placeholders = ",".join(["?"] * len(ranks))
        return _exec(
            f"SELECT * FROM users WHERE rank IN ({placeholders})",
            ranks, fetchall=True
        ) or []

    def is_blocked(self, user_id: int) -> bool:
        row = _exec("SELECT blocked FROM users WHERE user_id=?", (user_id,), fetchone=True)
        return bool(row["blocked"]) if row else False

    def get_user_state(self, user_id: int):
        row = _exec("SELECT state FROM users WHERE user_id=?", (user_id,), fetchone=True)
        return row["state"] if row and row.get("state") else None

    def set_user_state(self, user_id: int, state):
        _exec("UPDATE users SET state=? WHERE user_id=?", (state, user_id))

    def block_user(self, user_id: int):
        _exec("UPDATE users SET blocked=1 WHERE user_id=?", (user_id,))

    def unblock_user(self, user_id: int):
        _exec("UPDATE users SET blocked=0 WHERE user_id=?", (user_id,))

   

    def add_suggestion(self, user_id: int, text: str) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return _exec(
            "INSERT INTO suggestions (user_id, text, created_at) VALUES (?, ?, ?)",
            (user_id, text, now), lastrowid=True
        )

    def get_suggestions(self, status: str = None):
        if status:
            return _exec(
                "SELECT * FROM suggestions WHERE status=? ORDER BY id DESC",
                (status,), fetchall=True
            ) or []
        return _exec("SELECT * FROM suggestions ORDER BY id DESC", fetchall=True) or []

    def get_suggestion(self, sugg_id: int):
        return _exec("SELECT * FROM suggestions WHERE id=?", (sugg_id,), fetchone=True)

    def update_suggestion(self, sugg_id: int, status: str = None, reply: str = None):
        if status is not None and reply is not None:
            _exec("UPDATE suggestions SET status=?, admin_reply=? WHERE id=?",
                  (status, reply, sugg_id))
        elif status is not None:
            _exec("UPDATE suggestions SET status=? WHERE id=?", (status, sugg_id))
        elif reply is not None:
            _exec("UPDATE suggestions SET admin_reply=? WHERE id=?", (reply, sugg_id))



    def add_admin_message(self, user_id: int, text: str) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return _exec(
            "INSERT INTO admin_messages (user_id, text, created_at) VALUES (?, ?, ?)",
            (user_id, text, now), lastrowid=True
        )

    def get_admin_messages(self):
        return _exec(
            "SELECT * FROM admin_messages ORDER BY id DESC", fetchall=True
        ) or []

    def get_admin_message(self, msg_id: int):
        return _exec(
            "SELECT * FROM admin_messages WHERE id=?", (msg_id,), fetchone=True
        )

    def mark_message_read(self, msg_id: int):
        _exec("UPDATE admin_messages SET status='read' WHERE id=?", (msg_id,))

    def update_message_reply(self, msg_id: int, reply: str):
        _exec(
            "UPDATE admin_messages SET admin_reply=?, status='replied' WHERE id=?",
            (reply, msg_id)
        )



    def get_setting(self, key: str, default="1") -> str:
        row = _exec("SELECT value FROM settings WHERE key=?", (key,), fetchone=True)
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        if DATABASE_URL:
            _exec(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value=?",
                (key, value, value)
            )
        else:
            _exec(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )

    

    def get_stats(self):
        def count(sql, params=()):
            if DATABASE_URL:
                conn = get_conn()
                try:
                    cur = conn.cursor()
                    cur.execute(sql.replace("?", "%s"), params)
                    return cur.fetchone()[0]
                finally:
                    conn.close()
            else:
                conn = get_conn()
                try:
                    return conn.execute(sql, params).fetchone()[0]
                finally:
                    conn.close()

        return {
            "total_users":   count("SELECT COUNT(*) FROM users"),
            "admins":        count("SELECT COUNT(*) FROM users WHERE rank='admin'"),
            "mods":          count("SELECT COUNT(*) FROM users WHERE rank='moderator'"),
            "total_suggs":   count("SELECT COUNT(*) FROM suggestions"),
            "pending_suggs": count("SELECT COUNT(*) FROM suggestions WHERE status='pending'"),
            "total_msgs":    count("SELECT COUNT(*) FROM admin_messages"),
            "unread_msgs":   count("SELECT COUNT(*) FROM admin_messages WHERE status='unread'"),
        }
