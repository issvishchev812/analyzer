import asyncio
import time
import random
import fcntl
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from config import (
    API_ID,
    API_HASH,
    TABLE_NAME,
    MESSAGES_PER_CHAT,
    CHAT_MESSAGE_LIMITS,
    FIRST_RUN_LIMIT,
    LLM_BATCH_SIZE,
    CHAT_DELAY_MIN,
    CHAT_DELAY_MAX,
    SESSION_FILE,
)
from state import (
    load_state,
    save_state,
    get_text_hash,
    load_processed,
    save_processed,
)

from llm_processor import analyze_batch

from excel_parser import get_chat_names

CHATS = get_chat_names(TABLE_NAME)
CHATS.append('https://t.me/testovyichat52')

client = TelegramClient(
    SESSION_FILE,
    API_ID,
    API_HASH,
    flood_sleep_threshold=0,
    request_retries=1
)

LOCK_FILE = Path(__file__).parent / "collector.lock"


def acquire_collector_lock():
    """Не позволяет двум процессам одновременно использовать одну Telegram-сессию."""
    lock_file = open(LOCK_FILE, "w", encoding="utf-8")

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None

    return lock_file


def build_message_url(chat, message_id):
    chat_url = str(chat).rstrip("/")

    if not chat_url.startswith("https://t.me/"):
        return None

    path = chat_url.removeprefix("https://t.me/")

    if path.startswith("+") or path.startswith("joinchat/") or "/" in path:
        return None

    return f"https://t.me/{path}/{message_id}"


async def collect_telegram():

    print("1. Начинаем сбор...", flush=True)

    lock_file = acquire_collector_lock()
    if lock_file is None:
        print(
            "Сбор уже выполняется в другом процессе. Пропускаем запуск.",
            flush=True
        )
        return []

    posts = []
    state = load_state()
    processed = load_processed()

    try:
        wait_until = state.get("_flood_wait_until", 0)

        if time.time() < wait_until:
            remaining = int(wait_until - time.time())

            print(
                f"Telegram на паузе. Осталось {remaining} секунд.",
                flush=True
            )
            return []

        try:
            await client.start()

        except FloodWaitError as e:
            state["_flood_wait_until"] = time.time() + e.seconds
            save_state(state)
            return []

        print("2. Подключились к Telegram!", flush=True)

        for chat_index, chat in enumerate(CHATS):

            print(f"3. Обрабатываем чат: {chat}", flush=True)

            try:
                if chat_index:
                    await asyncio.sleep(
                        random.uniform(CHAT_DELAY_MIN, CHAT_DELAY_MAX)
                    )

                entity = await client.get_entity(chat)
                chat_key = str(chat)
                last_id = state.get(chat_key)

                if last_id is None:
                    print(
                        f"Новый чат. Берём последние {FIRST_RUN_LIMIT} сообщений.",
                        flush=True
                    )
                    messages = [
                        message async for message in client.iter_messages(
                            entity,
                            limit=FIRST_RUN_LIMIT,
                            wait_time=2,
                        )
                    ]
                    messages.reverse()
                else:
                    print(f"Последний ID: {last_id}", flush=True)
                    message_limit = CHAT_MESSAGE_LIMITS.get(
                        chat_key.rstrip("/"), MESSAGES_PER_CHAT
                    )
                    messages = [
                        message async for message in client.iter_messages(
                            entity,
                            min_id=last_id,
                            reverse=True,
                            limit=message_limit,
                            wait_time=2,
                        )
                    ]

                for batch_start in range(0, len(messages), LLM_BATCH_SIZE):
                    batch = messages[batch_start:batch_start + LLM_BATCH_SIZE]
                    messages_to_analyze = [
                        (message.id, message.message)
                        for message in batch
                        if message.message
                        and f"{chat}:{message.id}" not in processed
                    ]

                    try:
                        analyses = {}
                        if messages_to_analyze:
                            analyses = await asyncio.to_thread(
                                analyze_batch,
                                messages_to_analyze,
                                source=str(chat),
                            )
                    except Exception as e:
                        first_id = messages_to_analyze[0][0]
                        print(
                            f"Ошибка анализа {chat}, ID {first_id}: {e}",
                            flush=True,
                        )
                        break

                    for message in batch:
                        processed_key = f"{chat}:{message.id}"

                        if not message.message or processed_key in processed:
                            state[chat_key] = message.id
                            save_state(state)
                            continue

                        analysis = analyses[message.id]
                        text_hash = get_text_hash(message.message)

                        print(
                            f"LLM: чат={chat}, ID={message.id}, "
                            f"relevant={analysis['relevant']}",
                            flush=True,
                        )

                        if analysis["relevant"]:
                            posts.append({
                                "source": chat,
                                "source_type": "telegram_chat",
                                "chat_title": getattr(entity, "title", str(chat)),
                                "external_id": str(message.id),
                                "message_id": message.id,
                                "text": message.message,
                                "url": build_message_url(chat, message.id),
                                "published_at": message.date.isoformat(),
                                "text_hash": text_hash,
                                "relevant": analysis["relevant"],
                                "summary": analysis.get("summary", ""),
                                "reason": analysis.get("reason", ""),
                            })

                        print(
                            f"4. Сохраняем обработанное сообщение ID={message.id}",
                            flush=True,
                        )

                        processed.add(processed_key)
                        save_processed(processed)

                        print(
                            f"5. Обновляем state.json, ID={message.id}",
                            flush=True,
                        )

                        state[chat_key] = message.id
                        save_state(state)

                        print(
                            f"6. Сообщение ID={message.id} полностью обработано",
                            flush=True,
                        )

                print(f"Чат обработан: {chat}", flush=True)

            except FloodWaitError as e:

                state["_flood_wait_until"] = time.time() + e.seconds
                save_state(state)

                print(
                    f"FloodWait: {e.seconds} секунд. "
                    "Останавливаем сбор.",
                    flush=True
                )

                break

            except Exception as e:

                print(f"Ошибка чата {chat}: {e}", flush=True)
                continue

        print(
            f"Сбор завершён. Найдено новостей: {len(posts)}",
            flush=True
        )

        return posts

    finally:
        if client.is_connected():
            await client.disconnect()

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
