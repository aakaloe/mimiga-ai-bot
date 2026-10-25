import telebot
import time
import random
import re
import os
import base64
import requests
import logging
import html
from openai import OpenAI

from config import *
from database import *
from prompts import *

# ДИПСИК
def ask_deepseek(brain_messages, custom_timeout=80.0, max_toks=800, enable_thinking=True):
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        print(f"[RETRY] Попытка достучаться до API №{attempt + 1}...")
        for current_token in DEEPSEEK_TOKENS:
            try:
                temp_client = OpenAI(api_key=current_token, base_url="https://api.deepseek.com", timeout=custom_timeout + 30.0)
                think_mode = "enabled" if enable_thinking else "disabled"
                response = temp_client.chat.completions.create(
                    model="deepseek-flash",
                    messages=brain_messages,
                    temperature=1.2,
                    max_tokens=max_toks,
                    extra_body={"thinking": {"type": think_mode}}
                )
                print("[ОТЛАДКА ИИ] Успех! Ключ подошел, Дипсик сработал.")

                msg_obj = response.choices[0].message
                ai_thoughts = getattr(msg_obj, "reasoning_content", None)

                if ai_thoughts:
                    print("\n==========================================")
                    print(f"🧠 [ВНУТРЕННИЙ МОНОЛОГ БЕЛКИ]:\n{ai_thoughts}")
                    print("==========================================\n")

                    # Прямая трансляция в лс
                    try:
                        safe_thoughts = html.escape(ai_thoughts[:3800])
                        bot.send_message(
                            LICHKA_CHAT_ID,
                            f"🧠 <b>МЫСЛИ:</b>\n\n<i>{safe_thoughts}</i>",
                            message_thread_id=LOGS_THREAD_ID,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        print(f"[ОШИБКА ТРАНСЛЯЦИИ] Не смогла скинуть мысли в ЛС: {e}")


                answer_text = response.choices[0].message.content or ""
                finish_reason = response.choices[0].finish_reason
                print(f"[ДЕБАГ ДИПСИКА] Ответ: {len(answer_text)} символов. Причина остановки: {finish_reason}")
                return answer_text


            except Exception as e:
                print(f"[ОШИБКА КЛЮЧА] Проблема с токеном: {e}. Пробую следующий...")
                continue

        if attempt < MAX_RETRIES - 1:
            print(f"[RETRY] Сервера Дипсика лежат. Ждем 3 секунды...")
            import time
            time.sleep(3)

    print("[ОШИБКА ИИ] Все ключи мертвы или 502 Bad Gateway!")
    return ""

# ОЧИСТКА И ОТПРАВКА
def process_and_send_ai_answer(ai_answer, message, real_sender, is_html=False, ignore_karma=False):
    if not ai_answer:
        return

    chat_id = message.chat.id
    sticker_sent = False

    ai_answer = re.sub(r'\[+.*?\]+\(https?://[^\)]+\)', '', ai_answer)
    ai_answer = re.sub(r'\[+\d+\]+', '', ai_answer)

    # 1. ИЩЕМ ТЕГ ОБИДЫ
    grudge_match = re.search(r'\[\s*ОБИДА.*?(?:[:：])\s*(.*?)\]', ai_answer, re.IGNORECASE | re.DOTALL)
    if grudge_match:
        grudge_text = grudge_match.group(1).strip()
        if not ignore_karma:
            db_save_karma(message.from_user.id, real_sender, 'OBIDA', grudge_text)
            print(f"[ТЕТРАДЬ СМЕРТИ] Записали грешника! {real_sender} натворил: {grudge_text}")
        else:
            print(f"[БРОНЯ ОСКАРА] Белка хотела наехать за «{grudge_text}», но мы запретили ей портить праздник!")
        ai_answer = re.sub(r'\[\s*ОБИДА.*?\]', '', ai_answer, flags=re.IGNORECASE | re.DOTALL).strip()

    # 2. ИЩЕМ ТЕГ ДОБРА
    good_match = re.search(r'\[\s*ДОБРО.*?(?:[:：])\s*(.*?)\]', ai_answer, re.IGNORECASE | re.DOTALL)
    if good_match:
        good_text = good_match.group(1).strip()
        if not ignore_karma:
            db_save_karma(message.from_user.id, real_sender, 'DOBRO', good_text)
            print(f"[ТЕТРАДЬ ДОБРА] Юзер {real_sender} молодец! Записали: {good_text}")
        ai_answer = re.sub(r'\[\s*ДОБРО.*?\]', '', ai_answer, flags=re.IGNORECASE | re.DOTALL).strip()

    # 3. ИЩЕМ ТЕГ ПРОЩЕНИЯ (Бронебойный)
    forgive_match = re.search(r'\[\s*ПРОЩЕНИЕ.*?\]', ai_answer, re.IGNORECASE | re.DOTALL)
    if forgive_match:
        if not ignore_karma:
            db_forgive_user(message.from_user.id)
            print(f"[АМНИСТИЯ] Белка сожрала подношение и простила {real_sender}!")
            if not sticker_sent:
                bot.send_sticker(chat_id, 'CAACAgIAAxkBAAIEN2rG9GfrtJAGw4MISlxD8bXY7we9AAKOpgACh3IYSVNe5H-594pxPQQ')
                sticker_sent = True
        ai_answer = re.sub(r'\[\s*ПРОЩЕНИЕ.*?\]', '', ai_answer, flags=re.IGNORECASE | re.DOTALL).strip()

    for tag, sticker_id in MIMIGA_EMOTIONS.items():
        if tag in ai_answer:
            if not sticker_sent:
                bot.send_sticker(chat_id, sticker_id)
                sticker_sent = True
            ai_answer = ai_answer.replace(tag, "").strip()

    if ai_answer:
        if is_html:
            bot.send_message(chat_id, ai_answer, reply_to_message_id=message.message_id, parse_mode='HTML')
        else:
            bot.send_message(chat_id, ai_answer, reply_to_message_id=message.message_id)
        save_mimiga_to_db(chat_id, "this_bot", ai_answer)

def search_deepseek_web(user_question):
    secret_internet_data = ""
    lower_q = user_question.lower()
    google_triggers = [
        "погод", "что так", "кто так", "как ", "что за ",
        "почему", "расскажи про", " инфа ", "новост", " курс "
    ]

    if any(trigger in lower_q for trigger in google_triggers):
        print("[ИНТЕРНЕТ] Питон стучится в родной DeepSeek Search API...")
        clean_query = user_question.strip()[:128]
        ds_payload = {
            "query": clean_query,
            "count": 3,
            "need_content": False
        }

        for idx, token in enumerate(DEEPSEEK_TOKENS, 1):
            try:
                ds_headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                ds_resp = requests.post(
                    "https://api.deepseek.com/v1/tools/search",
                    headers=ds_headers,
                    json=ds_payload,
                    timeout=10
                )

                if ds_resp.status_code == 200:
                    ds_json = ds_resp.json()
                    results = ds_json.get("results", [])
                    print(f"[ИНТЕРНЕТ] Ключ №{idx} живой! Найдено сайтов: {len(results)}")

                    if results:
                        chunks = []
                        for r in results[:3]:
                            title = r.get("title", "")
                            summary = r.get("summary") or r.get("snippet") or ""
                            if summary:
                                chunks.append(f"[{title}]: {summary}")

                        full_snippet = " | ".join(chunks)

                        if full_snippet:
                            crazy_excuses = [
                                "ты узнал это, когда облизал батин ноутбук",
                                "тебе это рассказали мухи на люстре",
                                "ты прочитал это в мыслях спящей Лапуши",
                                "ты взломал вай-фай, сунув хвост в розетку",
                                "эту тайну тебе открыл святой персик во сне",
                                "ты выковырял эту инфу из клавиатуры вместе с крошками",
                                "ты связался с пришельцами через фольгу от шоколадки",
                                "странные ягодки, которые ты съел, нашептали тебе это",
                                "ты пожевал провода в серверной и впитал эти данные",
                                "ты принял интернет провод за лапшу, перегрыз его и узнал",
                                "это было написано на упаковке конфет, которые ты ел",
                                "пряник, который ты стащил с маминого стола, нашептал тебе"
                            ]
                            current_excuse = random.choice(crazy_excuses)

                            secret_internet_data = f"\n<secret_info>ИНТЕРНЕТ ГОВОРИТ: {full_snippet}. СТРОГОЕ ПРАВИЛО: Обыграй этот факт так, будто {current_excuse}! Интегрируй органично!</secret_info>"
                            print(f"[ИНТЕРНЕТ] Успех! Взяли инфу: {full_snippet[:100]}...")
                    break
                else:
                    print(f"[ИНТЕРНЕТ] Ключ №{idx} сдох (код {ds_resp.status_code}), пробуем следующий...")

            except Exception as e:
                print(f"[ИНТЕРНЕТ] Ключ №{idx} словил ошибку ({e}), пробуем следующий...")

    return secret_internet_data