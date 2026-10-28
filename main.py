import telebot
import time
import random
import re
from openai import OpenAI
import os
import psycopg2
import base64
import requests
import logging
import html

from config import *
from database import *
from prompts import *
from ai_service import *
from autotests import *

bot = telebot.TeleBot(TOKEN)

MEDIA_GROUPS = {}
last_photo_time = {}
last_mention_time = {}
gacha_counter = {}
COOLDOWN_SECONDS = 86400
LAST_OSCAR_MSG_ID = {}

# СИСТЕМА БЕЗОПАСНОСТИ ПЕРЕХВАТ ДОБАВЛЕНИЯ В ЧУЖОЙ ЧАТ
@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message):
    chat_id = message.chat.id
    bot_was_added = False
    for new_member in message.new_chat_members:
        if new_member.id == bot.get_me().id:
            bot_was_added = True
            break
    if bot_was_added:
        if chat_id not in VIP_CHATS:
            print(f"[БЕЗОПАСНОСТЬ] Бота затащили в левую группу! (ID: {chat_id})")
            try:
                bot.send_message(chat_id,
                             "Фууу, как тут воняет! (╥﹏╥) Я с вами сидеть не буду, неудачники! Пакеда фуфелы!")
                bot.send_sticker(chat_id, 'CAACAgIAAxkBAAICGmqh_5dIz9vKNJvI0UdkYPm9xdeXAAKcUwACBrCRSwsoV5RrqFwwPQQ')
            except Exception as e:
                print(f"[БЕЗОПАСНОСТЬ] Не смог плюнуть в чат: {e}")
            bot.leave_chat(chat_id)
        else:
            print(f"[БЕЗОПАСНОСТЬ] Бот добавлен в разрешенный VIP-чат: {chat_id}")
            return

# СИСТЕМА БЕЗОПАСНОСТИ В ЛИЧКЕ
@bot.message_handler(
    content_types=['text', 'sticker', 'photo', 'animation', 'dice'],
    func=lambda message: message.chat.type == 'private' and message.from_user.id not in VIP_USERS
)
def handle_uninvited_dm(message):
    chat_id = message.chat.id
    u_name = message.from_user.first_name or "Аноним"
    u_login = f"@{message.from_user.username}" if message.from_user.username else "без_юзернейма"
    spied_text = message.text or "[какая-то медиа]"
    print(f"[БЕЗОПАСНОСТЬ] 🚨 ЛЕВЫХ ЧЕЛ! Имя: {u_name} | Логин: {u_login} | ID: {message.from_user.id}")
    print(f"[ПЕРЕХВАТ] Он написал: «{spied_text}»")
    save_mimiga_to_db(message.chat.id, f"ЛЕВЫЙ_{u_name}", spied_text)
    try:
        bot.send_message(chat_id,
                         "ЙАДА-ЙАДА! ٩(╬ง Ò 皿 Ó)ง Ты кто такой вообще, а?! Мамочка запретила мне разговаривать с вонючими незнакомцами! Не пиши мне больше!")
        bot.send_sticker(chat_id, 'CAACAgIAAxkBAAICGGqh_w1d5pGFK1uoHELKZC--Iu4PAAK3WAACyVAoSoWY1f36qsDgPQQ')
    except Exception:
        pass
    return

# Таможня имен (для дипсика и команд с его участием)
def get_sender_name(message):
    if message.from_user.id == MY_PERSONAL_ID:
        return "Твоя любимая Создательница"
    elif message.from_user.id == BATYA_ID:
        return "Батя"
    elif message.from_user.username == 'GroupAnonymousBot':
        return "Твоя любимая Создательница пишет анонимно от лица Группы"
    else:
        return f"Чел по имени {message.from_user.first_name}"

# КОМАНДА ДЛЯ ССОР С ДРУГИМ БОТОМ
@bot.message_handler(commands=['anotherbot'])
def roast_anotherbot_command(message):
    chat_id = message.chat.id
    print("[АТАКА] Приказали поругаться с Anotherbot!")
    anotherbot_text = get_last_anotherbot_message(chat_id)
    if not anotherbot_text:
        bot.reply_to(message, "Я порылся в базе, но не нашёл свежих сообщений от этой ржавой банки! (╥﹏╥)")
        return
    real_sender = message.from_user.first_name
    roast_prompt = f"{MOMONGA_PROMPT}\n\n[СЕКРЕТНАЯ МИССИЯ]: Тебе приказали поругаться с роботом 'Другой бот'. \nВот его последняя фраза из базы данных: «{anotherbot_text}». \nТвоя задача — ответить ПОЛЬЗОВАТЕЛЮ, который вызвал команду. Скажи ему, что Другой бот — врушка, дурилка и несёт бред! Размажь его аргументы в своем стиле!"
    brain_messages = [{"role": "system", "content": roast_prompt}]
    bot.send_chat_action(chat_id, 'typing')
    ai_answer = ask_deepseek(brain_messages, custom_timeout=70.0, max_toks=800)
    if ai_answer == "":
        bot.reply_to(message, "Я слишком голодный, чтобы ругаться с жестянкой... (*-ω-)")
        return
    process_and_send_ai_answer(ai_answer, message, real_sender)

# КОМАНДА ВЫДАЧА ДОСЬЕ ИЗ ТАБЛИЦЫ КАРМЫ
@bot.message_handler(commands=['mirmiga'])
def handle_mirmiga(message):
    chat_id = message.chat.id
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(chat_id, "Эй! А кого проверять-то?! Напиши имя!")
        return

    target_name = parts[1].strip()
    bot.send_chat_action(chat_id, 'typing')
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                            SELECT karma_type, reason_text
                            FROM mimiga_karma
                            WHERE (username ILIKE %s OR user_id::TEXT = %s) AND is_deleted = FALSE
                            ORDER BY created_at DESC
                        """, (f"%{target_name}%", target_name))
            rows = cur.fetchall()

            if not rows:
                bot.send_message(chat_id, f"⚖️ На «{target_name}» в базе нет ничего! Я ничего про него не знаю!")
                return

            obidy = []
            dobro = []
            for r in rows:
                if r[0] == 'OBIDA':
                    obidy.append(r[1])
                elif r[0] == 'DOBRO':
                    dobro.append(r[1])

            response = f" ♡´•⩊•`♡ <b>ДОСЬЕ КАРМЫ: {target_name}</b>\n\n"
            if obidy:
                response += " (ᗒᗣᗕ)՞ <b>ОБИДКИ (В ЧЕРНОМ СПИСКЕ):</b>\n"
                response += "\n".join([f"• {sin}" for sin in obidy]) + "\n\n"
            if dobro:
                response += " ◕⩊◕ <b>ЗАСЛУГИ (В БЕЛОМ СПИСКЕ):</b>\n"
                response += "\n".join([f"• {good}" for good in dobro]) + "\n\n"

            bot.send_message(chat_id, response, parse_mode='HTML')

    except Exception as e:
        print(f"[БД ОШИБКА] Сломался блокнотик: {e}")
        bot.send_message(chat_id, "Блокнотик поперхнулся, не могу достать досье!")
    finally:
        if conn: conn.close()

# КОМАНДА ДЛЯ ПОЛУЧЕНИЯ ПОЛЧНОГО ДОСЬЕ (админы онли)
@bot.message_handler(commands=['delo'])
def handle_delo(message):
    chat_id = message.chat.id
    if message.from_user.id not in ADMINS:
        bot.send_message(chat_id, "ЙАДА-ЙАДА! Я тебе свой главный секретный блокнотик не покажу! (๑•̀ㅂ•́)و✧")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(chat_id, "Введи имя! (♡ˊ ꒳ ˋ)")
        return

    target_name = parts[1].strip()
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                            SELECT karma_type, reason_text, is_deleted
                            FROM mimiga_karma
                            WHERE (username ILIKE %s OR user_id::TEXT = %s)
                            ORDER BY created_at DESC
                        """, (f"%{target_name}%", target_name))
            rows = cur.fetchall()

            if not rows:
                bot.send_message(chat_id, f"👁️ В секретных архивах на «{target_name}» ВООБЩЕ ничего не найдено.")
                return

            obidy, dobro = [], []
            for r in rows:
                item_text = r[1]
                is_deleted = r[2]
                if is_deleted:
                    item_text = f"<s>{item_text}</s> <i>(удалено)</i>"

                if r[0] == 'OBIDA': obidy.append(item_text)
                elif r[0] == 'DOBRO': dobro.append(item_text)

            response = f" ♡´•⩊•`♡ <b>СЕКРЕТНЫЕ АРХИВЫ: {target_name}</b>\n\n"
            if obidy:
                response += " (ᗒᗣᗕ)՞ <b>ВСЕ ГРЕХИ (Включая прощенные):</b>\n" + "\n".join([f"• {s}" for s in obidy]) + "\n\n"
            if dobro:
                response += " ◕⩊◕ <b>ВСЕ ЗАСЛУГИ (Включая сгоревшие):</b>\n" + "\n".join([f"• {g}" for g in dobro]) + "\n\n"
            if len(response) > 4000: # т.к. тг не может грузить сообщения >4000
                cut_index = response.rfind('\n', 0, 4000)
                response = response[:cut_index] + "\n\n📜 <i>[ТЕТРАДЬ ПОРВАЛАСЬ! Грехов слишком много, остальное не влезло...]</i>"
            bot.send_message(chat_id, response, parse_mode='HTML')
    except Exception as e:
        print(f"Ошибка delo: {e}")
    finally:
        if conn: conn.close()

# ЦЕРЕМОНИЯ НАГРАЖДЕНИЯ: ЧИЗБАРГО, ПОМИДОР И КРИНЖ ДНЯ
@bot.message_handler(commands=['mimiga_oscar', 'itogi'])
def handle_mimiga_awards(message):
    chat_id = message.chat.id
    current_msg_id = message.message_id
    last_oscar_id = LAST_OSCAR_MSG_ID.get(chat_id, 0)
    if last_oscar_id != 0:
        messages_passed = current_msg_id - last_oscar_id
        if messages_passed < 1000:
            left_to_write = 1000 - messages_passed
            bot.send_message(chat_id, f"ЙАДА-ЙАДА! Куда лезете?! ٩(╬ง Ò 皿 Ó)ง\nС прошлой церемонии вы написали всего {messages_passed} сообщений! Нам нужна ТЫСЯЧА! Идите напишите еще {left_to_write} сообщений, а потом зовите!")
            return

    LAST_OSCAR_MSG_ID[chat_id] = current_msg_id
    bot.send_message(chat_id, "Пошел читать ваши последние 1000 сообщений! Готовлю премии... Ждите! (・`ω´・)")
    bot.send_chat_action(chat_id, 'typing')

    print("[ЦЕРЕМОНИЯ] Запрашиваем 1000 сообщений из БД...")
    history_rows = db_get_last_messages(chat_id, limit=1000)
    if not history_rows or len(history_rows) < 50:
        bot.send_message(chat_id, "Эй! Вы еще даже не наболтали нормальное количество! Нечего дёргать меня! (✿˵◕ ɜ◕˵)")
        return

    chat_log = "\n".join([f"{row[0]}: {row[1]}" for row in history_rows if row[1]])
    chat_log = chat_log[-80000:] # количество логов с запасом

    awards_prompt = get_awards_prompt(chat_log)
    try:
        print(f"[ЦЕРЕМОНИЯ] Сформировали лог. Длина текста: {len(chat_log)} символов. Отправляем в Дипсик! Ждем-с...")
        brain_messages = [{"role": "system", "content": awards_prompt}]
        ai_award_answer = ask_deepseek(brain_messages, custom_timeout=120.0, max_toks=16000) # учитывая думалку дипсика, токены с запасом
        if ai_award_answer == "":
            bot.send_message(chat_id, "Церемония отменяется, расходитесь! (╥﹏╥)")
            return
        try:
            process_and_send_ai_answer(ai_award_answer, message, message.from_user.first_name, is_html=True,
                                       ignore_karma=True)
        except Exception as html_err:
            print(f"[ОСКАР] Телега подавилась HTML от Дипсика ({html_err}), шлем без HTML!")
            clean_award = re.sub(r'<[^>]+>', '', ai_award_answer)
            process_and_send_ai_answer(clean_award, message, message.from_user.first_name, is_html=False,
                                       ignore_karma=True)
        bot.send_sticker(chat_id, 'CAACAgIAAxkBAAIEU2rKzUt5mcquCSglZ_9DnFPQfiq0AAIfqQACr21oSU3BDlaGHFQoPQQ')

    except Exception as e:
        print(f"[ОШИБКА ЦЕРЕМОНИИ] Проблема в Оскаре: {e}")
        LAST_OSCAR_MSG_ID[chat_id] = 0
        bot.send_message(chat_id, "Ой-ой, я запутался в бумажках с номинациями... (◡ ω ◡)")

# КОМАНДА /whois (для админов: проверка юзера по айди)
@bot.message_handler(commands=['whois'])
def handle_whois(message):
    chat_id = message.chat.id
    if message.from_user.id not in ADMINS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(chat_id, "Дай айдишник! Ща всё пробьём! ୧(๑•̀ㅁ•́๑)૭✧")
        return

    target_id = parts[1].strip()
    try:
        user_info = bot.get_chat(target_id)
        name = user_info.first_name or "Без имени"
        last_name = user_info.last_name or ""
        username = f"@{user_info.username}" if user_info.username else "Юзернейм скрыт"
        bio = user_info.bio or "Описание пустое"

        whois_report = (
            f"🎯 <b>Вычислили (ID: {target_id})</b>\n\n"
            f"👤 <b>Имя:</b> {name} {last_name}\n"
            f"🔗 <b>Юзернейм:</b> {username}\n"
            f"📝 <b>О себе:</b> {bio}\n\n"
        )
        bot.send_message(chat_id, whois_report, parse_mode='HTML')

    except Exception as e:
        bot.send_message(chat_id, f"Телеграм не отдает инфу! Либо он удалил аккаунт, либо блокнул бота намертво. Ошибка: {e}")

# КОМАНДА СПЛЕТНИ ОТ ЯБЕДЫ-МИМИГИ (аналог summery, но с приколом)
@bot.message_handler(commands=['spletni'])
def handle_mimiga_spletni(message):
        chat_id = message.chat.id
        parts = message.text.split(maxsplit=1)

        # Количество сообщений: если юзер написал цифру, берем её, если нет - рандомим
        if len(parts) > 1 and parts[1].strip().isdigit():
            n_messages = int(parts[1].strip())
            n_messages = max(20, min(n_messages, 1000))
        else:
            n_messages = random.choice([200, 300, 500])

        try:
            bot.send_message(
                chat_id,
                f"Так-так-так, щас прочитаю ваши последние {n_messages} сообщений и всем расскажу, кто тут чем занимался! (˘³˘)"
            )
            bot.send_chat_action(chat_id, 'typing')
            print(f"[СПЛЕТНИ] Запрашиваем последние {n_messages} сообщений из БД...")
            history_rows = db_get_last_messages(chat_id, limit=n_messages)

            if not history_rows:
                bot.send_message(chat_id, "В базе пусто! Вы чо, все умерли и молчите?! (╥﹏╥)")
                return

            chat_log_lines = []
            for username, msg_text in history_rows:
                if msg_text:
                    clean_line = str(msg_text).replace('\n', ' ')
                    chat_log_lines.append(f"{username}: {clean_line}")

            chat_log_str = "\n".join(chat_log_lines)
            caller_name = get_sender_name(message)

            spletni_prompt = get_spletni_prompt(caller_name, chat_log_lines, chat_log_str)

            brain_messages = [{"role": "system", "content": spletni_prompt}]
            bot.send_chat_action(chat_id, 'typing')

            ai_spletni_answer = ask_deepseek(brain_messages, custom_timeout=120.0, max_toks=16000)

            if not ai_spletni_answer:
                bot.send_message(chat_id, "Я пока читал ваши сплетни, уснул лицом в орехах... (¬ω¬)")
                return

            ai_spletni_answer = re.sub(r'<br\s*/?>', '\n', ai_spletni_answer, flags=re.IGNORECASE)
            ai_spletni_answer = re.sub(r'</?p\s*>', '\n', ai_spletni_answer, flags=re.IGNORECASE)

            try:
                process_and_send_ai_answer(ai_spletni_answer, message, caller_name, is_html=True, ignore_karma=True)
            except Exception as html_err:
                print(f"[СПЛЕТНИ] Ошибка HTML ({html_err}), шлем чистым текстом!")
                clean_spletni = re.sub(r'<[^>]+>', '', ai_spletni_answer)
                process_and_send_ai_answer(clean_spletni, message, caller_name, is_html=False, ignore_karma=True)

        except Exception as e:
            print(f"[ОШИБКА СПЛЕТЕН] Проблема в сплетнях: {e}")
            bot.send_message(chat_id, "У меня уши отвалились столько сплетен слушать! ( ╥ω╥ )")

# АВТОТЕСТЫ
@bot.message_handler(commands=['autotest'])
def handle_autotest(message):
    run_smoke_autotests(message)

# ОСНОВНОЙ ЛОВЕЦ ТЕКСТА И КАРТИНОК
@bot.message_handler(content_types=['text', 'sticker', 'photo', 'animation', 'dice'])
def handle_messages(message):
    chat_id = message.chat.id
    group_id = message.media_group_id
    if group_id:
        if group_id not in MEDIA_GROUPS:
            MEDIA_GROUPS[group_id] = True
            time.sleep(2.5)

        else:
            return

    text = message.text or message.caption or ""
    text = text.lower()

    need_to_ask_deepseek = False
    file_ids_to_download = []
    user_question = ""
    is_reply_to_mimiga = (message.reply_to_message and getattr(message.reply_to_message.from_user, 'username', '') == 'this_bot')
    if text.startswith('мимига скажи') or text.startswith('/mimiga') or is_reply_to_mimiga:
        need_to_ask_deepseek = True
        raw_text = message.text or message.caption or ""
        if text.startswith('мимига скажи'):
            user_question = raw_text[12:].strip()
        elif text.startswith('/mimiga'):
            parts = raw_text.split(maxsplit=1)
            user_question = parts[1].strip() if len(parts) > 1 else ""
        else:
            user_question = raw_text.strip()

        if len(user_question) == 0 and len(file_ids_to_download) == 0:
            bot.send_message(chat_id, "Чо сказать?! Лучше дай еды или хвали меня! (・`ω´・)")
            return

# ПОДСЛУШКА ОТ БЕЛКИ (влезает в разговор просто так)
    raw_msg_text = (message.text or message.caption or "").strip()
    if not need_to_ask_deepseek and len(raw_msg_text) > 3 and not raw_msg_text.startswith('/'):
        if random.randint(1, 60) == 1: #выбрано 60, но если чат слишком активный сегодня, можно увеличить, чтоб не надоедал
            print("[ПОДСЛУШКА] Белка погрела уши и решила влезть без спроса!")
            need_to_ask_deepseek = True
            user_question = f"(К тебе сейчас напрямую не обращались, но ты подслушал это сообщение от собеседника и решил беспардонно влезть со своим комментарием, поумничать или потребовать внимания!): {raw_msg_text}"

# ФИЧИ-ТРИГГЕРЫ
# ПОКА / ПАКА
    strict_pattern = r'\b(покеда|прощай|хай|салам алейкум|до связи|привет|пивет|пакеда)\b'
    if any(word in text for word in ['пока', 'пака']) or re.search(strict_pattern, text) or (
            message.content_type == 'sticker' and message.sticker.file_unique_id == TRIGGER_STICKER_UNIQUE_ID):
        bot.send_sticker(chat_id, STICKER_POKA)
        if not need_to_ask_deepseek:
            return

# ФУФЕЛ
    if re.search(r'\bфуфел\b', text):
        bot.send_sticker(chat_id, FUFEL_REPLY_STICKER_ID)
        if not need_to_ask_deepseek:
            return

# ФИЧА - ГАЧА 
    if message.content_type == 'dice' and message.dice.emoji == '🎰':

        if chat_id not in gacha_counter:
            gacha_counter[chat_id] = 0

        gacha_counter[chat_id] += 1
        current_count = gacha_counter[chat_id]
        if current_count == 1 or current_count % 10 == 0:
            print(f"[ОТЛАДКА] Юбилейная гача! Счет: {current_count}")
            bot.send_sticker(chat_id, STICKER_gacha)
            if not need_to_ask_deepseek:
                return
        if current_count >= 10:
            bot.send_message(chat_id, f"Уже {current_count} раз крутанули! Лучше бы мне внимание уделяли!")
        if not need_to_ask_deepseek:
            return

# МИМИГА
    if any(word in text for word in ['мимига', 'мимигу', 'момога', 'момогу', 'момонга', 'мимиге', 'момонге',
                                     'момонгу']) and 'мимига скажи' not in text and '/mimiga' not in text:
        random_sticker = random.choice(MIMIGA_STICKERS)
        bot.send_sticker(chat_id, random_sticker)
        if not need_to_ask_deepseek:
            return

# ВОНЯТЬ
    if any(word in text for word in ['вонять', 'воняешь', 'вонючка', 'ванять', 'ванят']):
        bot.send_sticker(chat_id, VONYAT_ID)
        if not need_to_ask_deepseek:
            return

# МЫТЬСЯ
    if any(word in text for word in ['мыца', 'мыться', 'моюсь', 'помылся', 'помылась']):
        bot.send_sticker(chat_id, MYTSA_ID)
        if not need_to_ask_deepseek:
            return

# ГИПЕРВЕНТИЛЯЦИЯ
    if any(word in text for word in
           ['гипервентилирую', 'гипервентилируешь', 'гипервентилируешь брат', 'гипервентиляция',
            'начинаю гипервентилировать', 'начинаю гипервентиляцию', 'гипервентилирует']):
        bot.send_sticker(chat_id, GIVERVENTI_ID)
        if not need_to_ask_deepseek:
            return

# ВЫЗОВ ГЛАВНОГО АДМИНА (при непрямом упоминании в чате)
    if any(word in text for word in ['имяадмина']): #варианты имени/слов триггеров 
        bot.send_sticker(chat_id, STICKER_GL_ADMIN)
        bot.send_message(chat_id, "@тег админа миииитеее") #прописывается @ник_админа (мите - посмотри на японском)
        PING_THREAD_ID = 9
        if chat_id != MY_PERSONAL_ID and chat_id != LICHKA_CHAT_ID:
            if message.chat.username:
                msg_link = f"https://t.me/{message.chat.username}/{message.message_id}"
            else:
                clean_id = str(chat_id)[4:] if str(chat_id).startswith('-100') else str(chat_id)
                msg_link = f"https://t.me/c/{clean_id}/{message.message_id}"

            try:
                bot.send_message(
                    LICHKA_CHAT_ID,
                    f"🍭 МИИИИТЕЕЕЕ! Там тебя в «{message.chat.title}» тыкает <b>{message.from_user.first_name}</b>! Хвали меня!\n\n💬 <i>«{message.text}»</i>\n\n🔗 {msg_link}",
                    message_thread_id=PING_THREAD_ID,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"[ОШИБКА] слыш где: {e}")
        if not need_to_ask_deepseek:
            return

# КАБУМ
    if 'кабум' in text in text:
        bot.send_animation(chat_id, random.choice(KABUM_GIF))
        if not need_to_ask_deepseek:
            return

# ФИЧА ТРИГГЕР НА ДРУГИХ БОТОВ
    if '/anotherbot' in text:
        if random.randint(1, 20) == 1: #если другой бот вызывается часто, можно сделать больше 20
            bot.send_sticker(chat_id, STICKER_BETTER_anotherbot)
            bot.send_message(chat_id, "Я же лучше [ИМЯ БОТА]!")
        if not need_to_ask_deepseek:
            return
    elif re.search(r'\bимябота\b', text):
        if random.randint(1, 20) == 1:
            bot.send_sticker(chat_id, random.choice(anotherbot_HATE_STICKERS))
            bot.send_message(chat_id, "Да зачем вам этот [ИМЯ БОТА]!")
        if not need_to_ask_deepseek:
            return

# ФИЧА ДЛЯ ГЛАВНОГО АДМИНА
    if message.from_user.username == 'GroupAnonymousBot':
        if 'да мимига' in text:
            bot.send_sticker(chat_id, random.choice(GL_ADMIN_LOVE_STICKERS))
        if 'да емае' in text:
            bot.send_sticker(chat_id, 'CAACAgIAAxkBAAPyapdR8lnOEc5dEOMX-Tzlv_6x7lYAAkpBAAKHqeBK8wy0dmhzZkY9BA')
        if not need_to_ask_deepseek:
            return

        elif random.randint(1, 20) == 1: #в зависимости от количества сообщений админа лучше регулировать
            bot.send_sticker(chat_id, random.choice(GL_ADMIN_STICKERS))
        if not need_to_ask_deepseek:
            return

# ДИПСИК
    if need_to_ask_deepseek:
        if random.randint(1, 40) == 1: #фича "игнорим юзера и не отправляем запрос в дипсик вообще"
            print("[ОТЛАДКА ИИ] Мимига включил 'у меня лапки'!")
            bot.send_message(chat_id,
                             "ЙАДА-ЙАДА! Я просто пушистая белка, прекрати мучить меня умными словами! (╥﹏╥) Отстааааань!",
                             reply_to_message_id=message.message_id)
            bot.send_sticker(chat_id, 'CAACAgIAAxkBAAIBrmqhzykQ_9NSp8BmsAZlysHnH12jAAKFSAACr5GBS3JBB_BJE5eNPQQ')
            return
        print(f"[ОТЛАДКА ИИ] Отправляю вопрос: {user_question}")
        try:
            bot.send_chat_action(chat_id, 'typing')
        except Exception:
            pass

        real_sender = get_sender_name(message)
        import datetime
        current_date = datetime.datetime.now().strftime("%d %B %Y")
        dynamic_prompt = MOMONGA_PROMPT + f"\n\nСЕКРЕТНОЕ ЗНАНИЕ ДЛЯ ТЕБЯ: Сегодня {current_date}."

        # ДИПСИК И ИНТЕРНЕТ
        secret_internet_data = search_deepseek_web(user_question)

        user_question_text = f"[Сообщение от: {real_sender}]\n{user_question}"
        user_content_list = []
        file_ids_to_download = []

        # РЕПЛАИ НА ФОТКИ
        if message.reply_to_message and message.reply_to_message.photo:
            target_msg = message.reply_to_message
            if target_msg.media_group_id:
                print("[ЗРЕНИЕ] Реплай на старый альбом! Высасываем ID из БД...")
                db_ids = db_get_album_files(target_msg.media_group_id)
                print(f"[БАЗА] БД отдала нам {len(db_ids)} фоток!")
                if db_ids:
                    file_ids_to_download.extend(db_ids)
                else:
                    file_ids_to_download.append(target_msg.photo[-1].file_id)
            else:
                file_ids_to_download.append(target_msg.photo[-1].file_id)

        # ФОТКИ В СООБЩЕНИИ НАПРЯМУЮ
        elif message.content_type == 'photo':
            if message.media_group_id:
                print("[ЗРЕНИЕ] Свежий альбом! Спим 2.5 сек, ждем записи в БД...")
                time.sleep(2.5)
                db_ids = db_get_album_files(message.media_group_id)
                if db_ids:
                    file_ids_to_download.extend(db_ids)
                else:
                    file_ids_to_download.append(message.photo[-1].file_id)
            else:
                file_ids_to_download.append(message.photo[-1].file_id)

        if file_ids_to_download:
            file_ids_to_download = list(set(file_ids_to_download))
            for fid in file_ids_to_download:
                try:
                    file_info = bot.get_file(fid)
                    downloaded_file = bot.download_file(file_info.file_path or "")
                    base64_image = base64.b64encode(downloaded_file).decode('utf-8')
                    mime_url = f"data:image/jpeg;base64,{base64_image}"
                    user_content_list.append({"type": "image_url", "image_url": {"url": mime_url}})
                except Exception as e:
                    print(f"Ошибка фотки: {e}")

            user_question_text += f"\n\n[СИСТЕМНОЕ УВЕДОМЛЕНИЕ: Пользователь {real_sender} прикрепил {len(file_ids_to_download)} картинок! Опиши их!]"

        user_content_list.append({"type": "text", "text": user_question_text})

        # СОБИРАЕМ КОНТЕКСТ В БД
        print("[ПАМЯТЬ] Воруем последние 40 сообщений из БД...")
        recent_db_messages = db_get_last_messages(chat_id, limit=40) #вариативно, но чтоб не засорять промт + соблюдать характер персонажа промта сделала немного

        chat_context_lines = []
        for row in recent_db_messages:
            u_name = row[0] or "Кто-то"
            m_text = row[1] or ""
            if m_text.strip():
                chat_context_lines.append(f"{u_name}: {m_text}")

        chat_context_string = "\n".join(chat_context_lines)

        background_context = ""
        karma_injection = ""
        if chat_context_string:
            background_context = f"\n\n<context>\nПОСЛЕДНИЕ СООБЩЕНИЯ В ЧАТЕ (до твоего вызова):\n{chat_context_string}\n\nВАЖНОЕ ПРАВИЛО: Если видишь в этом контексте имя '[ИМЯ ДАННОГО БОТА]'  — ЗНАЙ, ЧТО ЭТО ТВОИ СОБСТВЕННЫЕ ПРОШЛЫЕ ОТВЕТЫ! А '[ИМЯ ДРУГОГО БОТА]' — это второй бот в этом чате. Учитывай это!\n</context>"

        # ВЕСЫ КАРМЫ
        user_grudges = db_get_karma(message.from_user.id, 'OBIDA')
        user_good_deeds = db_get_karma(message.from_user.id, 'DOBRO')

        if user_grudges:
            all_sins = "; ".join(user_grudges)
            karma_injection = f"\n\n[ТВОЯ ПАМЯТЬ ОБИД НА ЭТОГО ПОЛЬЗОВАТЕЛЯ]: В прошлом {real_sender} сделал тебе плохо: {all_sins}. ТВОЯ ЗАДАЧА: изменить своё ОТНОШЕНИЕ к этому юзеру. Веди себя вредно и холодно, как обиженный ребёнок. НО СТРОГОЕ ПРАВИЛО: НЕ НАДО в каждом ответе повторять, что именно он сделал! Приплетай старые обиды ТОЛЬКО если это логично по контексту разговора. В остальном просто будь злюкой. (Памятка: если он прямо сейчас извиняется и дает еду - тег [ПРОЩЕНИЕ])."
            print(f"[МЕСТЬ] Включен режим токсичности на юзера {real_sender}!")

        elif user_good_deeds:
            all_good = "; ".join(user_good_deeds)
            karma_injection = f"\n\n[ТЕТРАДЬ ДОБРА НА ЭТОГО ПОЛЬЗОВАТЕЛЯ]: В прошлом {real_sender} сделал тебе много хорошего: {all_good}. ТВОЯ ЗАДАЧА: относиться к нему как к любимому другу. Будь с ним нежным, милым и ласковым. НО СТРОГОЕ ПРАВИЛО: НЕ НАДО каждый раз говорить спасибо за эти старые заслуги, не будь как заезженная пластинка! Просто сохраняй теплый и любящий тон!"
            print(f"[ДОБРО] Включен режим лапочки на юзера {real_sender}!")

        final_system_prompt = dynamic_prompt + secret_internet_data + background_context + karma_injection
        brain_messages = [{"role": "system", "content": final_system_prompt}]
        brain_messages.append({"role": "user", "content": user_content_list})

        # ПЕРЕБОР КЛЮЧЕЙ
        ai_answer = ask_deepseek(brain_messages, custom_timeout=100.0, max_toks=1500)
        if ai_answer == "":
            print("[ОШИБКА ИИ] Все ключи мертвы или 502 Bad Gateway!")
            try:
                bot.send_message(chat_id, "ДА КАК ВЫ НАДОЕЛИ... Я ГОЛОДНЫЙ! МНЕ НЕХОРОШОООО!!!",
                             reply_to_message_id=message.message_id)
                bot.send_animation(chat_id, 'CgACAgIAAxkBAAIBuGqh1OVd7p3Skur4wiG3QFeNL_FsAAI2owACa825SCKhnIxHoVqvPQQ')
            except Exception as e:
                print(f"[КРИТИЧЕСКАЯ ОШИБКА] Телега не сожрала гифку или сообщение: {e}")
            return

        process_and_send_ai_answer(ai_answer, message, real_sender)

if __name__ == '__main__':
    print("Бот версии 6.0 запущен!")
    while True:
        try:
            print("[СИСТЕМА] Запускаю Мимигу в работу...")
            #create_karma_table() #раскомитить если таблицы кармы нет
            bot.polling(none_stop=True, skip_pending=True, timeout=90, long_polling_timeout=90)
        except Exception as e:
            print(f"[ОШИБКА] Отвалился интернет или Телега: {e}")
            print("[СИСТЕМА] Сплю 5 секунд и восстаю из мертвых...")
            time.sleep(5)
