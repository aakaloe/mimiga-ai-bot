import psycopg2
import time
import os
import logging
from config import *

def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "chat"),
            user=os.getenv("DB_USER", "anotherbot_user"),
            password=os.getenv("DB_PASS"),
            host="localhost",
            port="5432"
        )
        return conn
    except Exception as e:
        logging.error(f"Не могу подключиться к БД: {e}")
        return None

def create_karma_table():
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mimiga_karma (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    username TEXT,
                    karma_type TEXT, -- Сюда пишем 'OBIDA' или 'DOBRO'
                    reason_text TEXT, -- Текст за что дали
                    is_deleted BOOLEAN DEFAULT FALSE, -- Флаг мягкого удаления
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            print("[БД] Таблица КАРМЫ создана и готова судить грешников!")
    except Exception as e:
        print(f"[БД ОШИБКА] Не смогли построить карму: {e}")
    finally:
        conn.close()

def db_save_karma(user_id, username, karma_type, reason_text):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            if karma_type == 'OBIDA':
                cur.execute(
                    "UPDATE mimiga_karma SET is_deleted = TRUE WHERE user_id = %s AND karma_type = 'DOBRO'",
                    (user_id,)
                )
                print(f"[КАРМА] {username} нас разозлил! Все его добрые дела аннулированы (is_deleted = TRUE)!")

            cur.execute(
                "INSERT INTO mimiga_karma (user_id, username, karma_type, reason_text) VALUES (%s, %s, %s, %s)",
                (user_id, username, karma_type, reason_text)
            )
            conn.commit()
    except Exception as e:
        print(f"[БД ОШИБКА] Проблема с записью кармы: {e}")
    finally:
        if conn: conn.close()

def db_get_karma(user_id, karma_type):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reason_text FROM mimiga_karma WHERE user_id = %s AND karma_type = %s AND is_deleted = FALSE ORDER BY created_at DESC",
                (user_id, karma_type)
            )
            rows = cur.fetchall()
            return [r[0] for r in rows]
    except Exception as e:
        print(f"[БД ОШИБКА] Проблема с чтением кармы: {e}")
        return []
    finally:
        if conn: conn.close()

def db_forgive_user(user_id):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE mimiga_karma SET is_deleted = TRUE WHERE user_id = %s AND karma_type = 'OBIDA'",
                (user_id,)
            )
            conn.commit()
            print("[БД] Обидка софт-удалена (is_deleted=True)! Амнистия прошла успешно!")
    except Exception as e:
        print(f"[БД ОШИБКА] Не смогли простить грешника: {e}")
    finally:
        if conn: conn.close()

def db_get_last_messages(chat_id, limit=40):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT username, message_text
                FROM messages
                WHERE chat_id = %s
                  AND created_at > COALESCE(
                      (SELECT cleared_at FROM chat_memory_clears WHERE chat_id = %s),
                      '1970-01-01'::timestamp
                  )
                ORDER BY created_at DESC
                LIMIT %s
            """
            cur.execute(sql, (chat_id, chat_id, limit))
            rows = cur.fetchall()
            return rows[::-1]
    except Exception as e:
        print(f"[БД ОШИБКА] Не смог достать историю: {e}")
        return []
    finally:
        if conn:
            conn.close()

def db_get_album_files(mg_id):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT file_id FROM album_log WHERE media_group_id = %s", (mg_id,))
            rows = cur.fetchall()
            return [r[0] for r in rows]
    except Exception as e:
        print(f"[БД ОШИБКА] Не смогли взять альбом из базы: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_last_anotherbot_message(chat_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT message_text FROM public.messages
            WHERE chat_id = %s AND username = 'anotherbot'
            ORDER BY created_at DESC LIMIT 1;
        """, (chat_id,))

        row = cur.fetchone()
        conn.close()
        print(row)
        if row:
            return row[0]
        return None
    except Exception as e:
        print(f"[БД ОШИБКА] Не смогли прочитать базу: {e}")
        return None

def save_mimiga_to_db(chat_id, username, text):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO public.messages (chat_id, username, message_text, created_at)
            VALUES (%s, %s, %s, NOW());
        """, (chat_id, username, text))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[БД ОШИБКА] Белка не смогла записать себя: {e}")
