import sqlite3

class DBManager:
    def __init__(self, db_path="db.sqlite3") -> None:
        self.__conn = sqlite3.connect(db_path, check_same_thread=False)
        self.__cursor = self.__conn.cursor()
        # Create users table
        self.__cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT
            )
        """)
        # Create files table with a user_id column
        self.__cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                file_name TEXT,
                hash TEXT UNIQUE,
                file_filters TEXT,
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        self.__cursor.execute("""CREATE TABLE IF NOT EXISTS chunks (
                            id INTEGER PRIMARY KEY,
                            main_file TEXT,
                            hash TEXT,
                            chunk_index INTEGER,
                            file_id TEXT,
                            key TEXT
                        )""")
        self.__cursor.execute("""CREATE TABLE IF NOT EXISTS bot_settings (
                            id INTEGER PRIMARY KEY,
                            domain TEXT,
                            bot_token TEXT,
                            chat_id INTEGER
                        )""")
        # Insert default bot if table is empty
        self.__cursor.execute("SELECT * FROM bot_settings")
        if not self.__cursor.fetchall():
            self.__cursor.execute(
                "INSERT INTO bot_settings (domain, bot_token, chat_id) VALUES(?, ?, ?)",
                ("telegram", None, None)
            )
            self.__conn.commit()

    def add_file(self, user_id: int, file_name: str, file_hash: str) -> None:
        try:
            self.__cursor.execute(
                "INSERT INTO files (file_name, hash, user_id) VALUES (?, ?, ?)",
                (file_name, file_hash, user_id)
            )
            self.__conn.commit()
        except sqlite3.IntegrityError:
            # Raise a custom exception so that the caller (upload route) knows the file exists
            raise Exception("File already exists. Please check your uploads.")

    def add_chunk(self, main_file_hash: str, chunk_hash: str, chunk_index: str, chunk_file_id: str) -> None:
        self.__cursor.execute(
            "INSERT INTO chunks (main_file, hash, chunk_index, file_id) VALUES (?, ?, ?, ?)",
            (main_file_hash, chunk_hash, chunk_index, chunk_file_id)
        )
        self.__conn.commit()

    def del_file(self, file_name: str) -> None:
        self.__cursor.execute("DELETE FROM files WHERE file_name = ?", (file_name,))
        self.__conn.commit()

    def del_chunks(self, main_file_hash: str) -> None:
        self.__cursor.execute("DELETE FROM chunks WHERE main_file = ?", (main_file_hash,))
        self.__conn.commit()

    def get_files(self, user_id: int = None) -> list:
        if user_id:
            self.__cursor.execute("SELECT * FROM files WHERE user_id = ?", (user_id,))
        else:
            self.__cursor.execute("SELECT * FROM files")
        return self.__cursor.fetchall()

    def get_file_by_name(self, name: str) -> list:
        self.__cursor.execute("SELECT * FROM files WHERE file_name = ?", (name,))
        return self.__cursor.fetchall()

    def set_filters(self, file_name: str, filters: list) -> None:
        filters_to_str = ', '.join(map(str, filters))
        self.__cursor.execute("UPDATE files SET file_filters = ? WHERE file_name = ?", (filters_to_str, file_name))
        self.__conn.commit()

    def get_filters(self) -> list:
        self.__cursor.execute("SELECT file_filters FROM files")
        filters_list = []
        for row in self.__cursor.fetchall():
            if row and row[0]:
                filters_list.extend(row[0].split(', '))
        return sorted(set(filters_list))

    def get_filters_by_name(self, filename: str) -> list:
        self.__cursor.execute("SELECT file_filters FROM files WHERE file_name = ?", (filename,))
        filters_list = []
        for row in self.__cursor.fetchall():
            if row and row[0]:
                filters_list.extend(row[0].split(', '))
        return filters_list

    def get_filter_files(self, filter: str) -> list:
        self.__cursor.execute("SELECT * FROM files WHERE file_filters GLOB ?", (f"*{filter}*",))
        return self.__cursor.fetchall()

    def get_chunks(self, main_file_hash: str) -> list:
        self.__cursor.execute("SELECT * FROM chunks WHERE main_file = ?", (main_file_hash,))
        return self.__cursor.fetchall()

    def get_bots(self) -> list:
        self.__cursor.execute("SELECT * FROM bot_settings")
        return self.__cursor.fetchall()

    def edit_bot(self, bot: dict) -> None:
        query = "UPDATE bot_settings SET chat_id = ?, bot_token = ? WHERE id = ?"
        self.__cursor.execute(query, (bot['chat_id'], bot['token'], bot['id']))
        self.__conn.commit()

    def del_bot(self, bot_id: int) -> None:
        self.__cursor.execute("DELETE FROM bot_settings WHERE id = ?", (bot_id,))
        self.__conn.commit()

    def delete_file(self, file_hash: str) -> None:
        try:
            self.__cursor.execute("DELETE FROM files WHERE hash = ?", (file_hash,))
            self.__conn.commit()
        except Exception as e:
            raise Exception(f"Error deleting file from database: {e}")

    def get_user_by_username(self, username: str) -> list:
        self.__cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        return self.__cursor.fetchall()

    def add_user(self, username: str, password: str) -> None:
        try:
            self.__cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            self.__conn.commit()
        except sqlite3.IntegrityError:
            raise Exception("Username already exists.")

