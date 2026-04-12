import sqlite3
from datetime import datetime

DB_PATH = "bot.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
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




class Database:

    def add_user(self, user_id: int, username: str, full_name: str):
        with get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at) VALUES (?,?,?,?)",
                (user_id, username, full_name, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            conn.execute(
                "UPDATE users SET username=?, full_name=? WHERE user_id=?",
                (username, full_name, user_id)
            )

    def get_user(self, user_id: int):
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_rank(self, user_id: int) -> str:
        with get_conn() as conn:
            row = conn.execute("SELECT rank FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row["rank"] if row else "user"

    def set_user_rank(self, user_id: int, rank: str):
        with get_conn() as conn:
            conn.execute("UPDATE users SET rank=? WHERE user_id=?", (rank, user_id))

    def get_all_users(self):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY CASE rank "
                "WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 "
                "WHEN 'moderator' THEN 3 ELSE 4 END"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_users_by_rank(self, ranks: list):
        placeholders = ",".join("?" * len(ranks))
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM users WHERE rank IN ({placeholders})", ranks
            ).fetchall()
        return [dict(r) for r in rows]

 

    def add_suggestion(self, user_id: int, text: str) -> int:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO suggestions (user_id, text, created_at) VALUES (?,?,?)",
                (user_id, text, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
        return cur.lastrowid

    def get_suggestions(self, status: str = None):
        with get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM suggestions WHERE status=? ORDER BY id DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM suggestions ORDER BY id DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_suggestion(self, sugg_id: int):
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM suggestions WHERE id=?", (sugg_id,)).fetchone()
        return dict(row) if row else None

    def update_suggestion(self, sugg_id: int, status: str = None, reply: str = None):
        with get_conn() as conn:
            if status is not None and reply is not None:
                conn.execute(
                    "UPDATE suggestions SET status=?, admin_reply=? WHERE id=?",
                    (status, reply, sugg_id)
                )
            elif status is not None:
                conn.execute("UPDATE suggestions SET status=? WHERE id=?", (status, sugg_id))
            elif reply is not None:
                conn.execute("UPDATE suggestions SET admin_reply=? WHERE id=?", (reply, sugg_id))


    def add_admin_message(self, user_id: int, text: str) -> int:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO admin_messages (user_id, text, created_at) VALUES (?,?,?)",
                (user_id, text, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
        return cur.lastrowid

    def get_admin_messages(self):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM admin_messages ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_admin_message(self, msg_id: int):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM admin_messages WHERE id=?", (msg_id,)
            ).fetchone()
        return dict(row) if row else None

    def mark_message_read(self, msg_id: int):
        with get_conn() as conn:
            conn.execute(
                "UPDATE admin_messages SET status='read' WHERE id=?", (msg_id,)
            )

    def update_message_reply(self, msg_id: int, reply: str):
        with get_conn() as conn:
            conn.execute(
                "UPDATE admin_messages SET admin_reply=?, status='replied' WHERE id=?",
                (reply, msg_id)
            )

   

    def block_user(self, user_id: int):
        with get_conn() as conn:
            conn.execute("UPDATE users SET blocked=1 WHERE user_id=?", (user_id,))

    def unblock_user(self, user_id: int):
        with get_conn() as conn:
            conn.execute("UPDATE users SET blocked=0 WHERE user_id=?", (user_id,))

    def is_blocked(self, user_id: int) -> bool:
        with get_conn() as conn:
            row = conn.execute("SELECT blocked FROM users WHERE user_id=?", (user_id,)).fetchone()
        return bool(row["blocked"]) if row else False

    def get_stats(self):
        with get_conn() as conn:
            total_users    = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            admins         = conn.execute("SELECT COUNT(*) FROM users WHERE rank='admin'").fetchone()[0]
            mods           = conn.execute("SELECT COUNT(*) FROM users WHERE rank='moderator'").fetchone()[0]
            total_suggs    = conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0]
            pending_suggs  = conn.execute("SELECT COUNT(*) FROM suggestions WHERE status='pending'").fetchone()[0]
            total_msgs     = conn.execute("SELECT COUNT(*) FROM admin_messages").fetchone()[0]
            unread_msgs    = conn.execute("SELECT COUNT(*) FROM admin_messages WHERE status='unread'").fetchone()[0]
        return {
            "total_users":   total_users,
            "admins":        admins,
            "mods":          mods,
            "total_suggs":   total_suggs,
            "pending_suggs": pending_suggs,
            "total_msgs":    total_msgs,
            "unread_msgs":   unread_msgs,
        }
