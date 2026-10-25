import re
from config import *
from database import *
from ai_service import *


def run_smoke_autotests(message):
    if message.from_user.id not in [123456789, 987654321]:
        return

    bot.send_message(
        LICHKA_CHAT_ID,
        "️ (⑅˘꒳˘) <b>Запускаю Smoke-автотесты системы (6 проверок)... Ждите!</b>",
        message_thread_id=TEST_THREAD_ID,
        parse_mode='HTML'
    )

    report = ["📊 <b>ОТЧЕТ АВТОТЕСТИРОВАНИЯ (QA Suite):</b>\n"]
    passed = 0
    failed = 0

    # 1. ПРОВЕРКА БАЗЫ ДАННЫХ
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        res = cur.fetchone()
        conn.close()
        assert res[0] == 1, "БД вернула фигню вместо единицы"
        report.append("✅ <b>[DB Connection]:</b> PASSED (Постгрес жив и отвечает)")
        passed += 1
    except Exception as e:
        report.append(f"❌ <b>[DB Connection]:</b> FAILED ({e})")
        failed += 1

    # 2. UNIT-ТЕСТ РЕГУЛЯРОК (Парсер кармы)
    try:
        fake_ai_text = "Йада-йада, ты дурак! [ОБИДА: назвал меня жирной мышью]"
        match = re.search(r'\[\s*ОБИДА.*?(?:[:：])\s*(.*?)\]', fake_ai_text, re.IGNORECASE)
        assert match is not None, "Регулярка ослепла и не нашла тег!"
        assert match.group(1).strip() == "назвал меня жирной мышью", "Текст обиды вырезан криво!"
        report.append("✅ <b>[Regex Karma Parser]:</b> PASSED (Теги вырезаются идеально)")
        passed += 1
    except Exception as e:
        report.append(f"❌ <b>[Regex Karma Parser]:</b> FAILED ({e})")
        failed += 1

    # 3. ПИНГ ИИ (DeepSeek API)
    try:
        test_msg = [{"role": "user", "content": "Ответь одним словом: Мимига"}]
        ai_resp = ask_deepseek(test_msg, max_toks=50, custom_timeout=30.0, enable_thinking=False)
        assert len(ai_resp) > 0, "Дипсик вернул пустую строку (все ключи сдохли или таймаут)"
        report.append(f"✅ <b>[DeepSeek Chat API]:</b> PASSED (Мозг ответил: <i>«{ai_resp.strip()}»</i>)")
        passed += 1
    except Exception as e:
        report.append(f"❌ <b>[DeepSeek Chat API]:</b> FAILED ({e})")
        failed += 1

    # 4. НАТИВНЫЙ ПОИСК В ИНТЕРНЕТЕ (DeepSeek Search API)
    try:
        # 1. Негативный тест: без триггер-слова поиск НЕ должен срабатывать
        empty_res = search_deepseek_web("привет пушистая вредина")
        assert empty_res == "", "Поиск сработал без триггер-слова (жрет деньги зря)!"

        # 2. Позитивный боевой тест: стучимся в /v1/tools/search по триггеру 'погод'
        search_res = search_deepseek_web("погода в Санкт-Петербурге")
        assert "<secret_info>ИНТЕРНЕТ ГОВОРИТ:" in search_res, "DeepSeek Search API вернул пустоту!"

        report.append("✅ <b>[DeepSeek Search API]:</b> PASSED (Интернет и фильтр триггеров работают)")
        passed += 1
    except Exception as e:
        report.append(f"❌ <b>[DeepSeek Search API]:</b> FAILED ({e})")
        failed += 1

    # 5. ТРИГГЕР «ПОКА/ПРИВЕТ» + ОТПРАВКА СТИКЕРА
    try:
        strict_pattern = r'\b(покеда|прощай|хай|салам алейкум|до связи|привет|пивет|пакеда)\b'
        assert re.search(strict_pattern, "ну все, салам алейкум пацаны") is not None, "Регулярка не увидела 'салам алейкум'!"
        assert re.search(strict_pattern, "запиветствовать") is None, "Ложное срабатывание регулярки внутри чужого слова!"

        bot.send_sticker(LICHKA_CHAT_ID, STICKER_POKA, message_thread_id=TEST_THREAD_ID)

        report.append("✅ <b>[Trigger 'ПОКА' & Sticker]:</b> PASSED (Регулярка и стикер работают)")
        passed += 1
    except Exception as e:
        report.append(f"❌ <b>[Trigger 'ПОКА' & Sticker]:</b> FAILED ({e})")
        failed += 1

    # 6. ТРИГГЕР «ФУФЕЛ» + ОТПРАВКА ГИФКИ/СТИКЕРА
    try:
        fufel_pattern = r'\bфуфел\b'
        assert re.search(fufel_pattern, "слышь ты фуфел") is not None, "Не нашла слово 'фуфел'!"
        assert re.search(fufel_pattern, "фуфельный") is None, "Сработала на 'фуфельный', а должна только на 'фуфел'!"

        bot.send_sticker(LICHKA_CHAT_ID, FUFEL_REPLY_STICKER_ID, message_thread_id=TEST_THREAD_ID)

        report.append("✅ <b>[Trigger 'ФУФЕЛ' & Asset]:</b> PASSED (Логика и ответ живы)")
        passed += 1
    except Exception as e:
        report.append(f"❌ <b>[Trigger 'ФУФЕЛ' & Asset]:</b> FAILED ({e})")
        failed += 1

    # ИТОГОВЫЙ САММАРИ
    total = passed + failed
    status_emoji = "🟢 ВСЕ СИСТЕМЫ В НОРМЕ!" if failed == 0 else "🔴 У НАС ПРОБЛЕМЫ!"
    report.append(f"\n<b>ИТОГ: {passed}/{total} успешных тестов.</b>\n{status_emoji}")

    bot.send_message(
        LICHKA_CHAT_ID,
        "\n".join(report),
        message_thread_id=TEST_THREAD_ID,
        parse_mode='HTML'
    )