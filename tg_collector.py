import asyncio
import time
import random

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from config import API_ID, API_HASH, TABLE_NAME
from state import (
    load_state,
    save_state,
    get_text_hash,
    load_processed,
    mark_as_processed
)

from llm_processor import analyze_text

from excel_parser import get_chat_names

CHATS = get_chat_names(TABLE_NAME)
CHATS.append('https://t.me/testovyichat52')

client = TelegramClient(
    "chat-analyzer.session",
    API_ID,
    API_HASH,
    flood_sleep_threshold=0,
    request_retries=1
)


async def collect_telegram():

    print("1. Начинаем сбор...", flush=True)

    posts = []
    state = load_state()
    processed = load_processed()

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

    for chat in CHATS:

        print(f"3. Обрабатываем чат: {chat}", flush=True)

        try:
            await asyncio.sleep(random.uniform(3, 5))

            entity = await client.get_input_entity(chat)

            last_id = state.get(str(chat), 0)

            print(f"Последний ID: {last_id}", flush=True)

            async for message in client.iter_messages(
                    entity,
                    min_id=last_id,
                    reverse=True,
                    limit=15,
                    wait_time=2
            ):

                if not message.message:
                    state[str(chat)] = message.id
                    save_state(state)
                    continue

                text = message.message.lower()

                text_hash = get_text_hash(text)

                processed_key = f"{chat}:{message.id}"

                if processed_key in processed:
                    state[str(chat)] = message.id
                    save_state(state)
                    continue

                try:
                    analysis = analyze_text(text)

                    if (
                        not isinstance(analysis, dict)
                        or "relevant" not in analysis
                    ):
                        raise ValueError("Некорректный ответ LLM")

                    print(
                        f"LLM: чат={chat}, ID={message.id}, "
                        f"relevant={analysis['relevant']}",
                        flush=True
                    )

                except Exception as e:
                    print(
                        f"Ошибка анализа {chat}, ID {message.id}: {e}",
                        flush=True
                    )
                    break

                if analysis["relevant"]:
                    username = str(chat).rstrip("/").split("/")[-1]

                    url = f"https://t.me/{username}/{message.id}"

                    posts.append({
                        "source": chat,
                        "source_type": "telegram_chat",
                        "chat_title": getattr(entity, "title", str(chat)),
                        "external_id": str(message.id),
                        "message_id": message.id,
                        "text": message.message,
                        "url": url,
                        "published_at": message.date.isoformat(),
                        "text_hash": text_hash,
                        "relevant": analysis["relevant"],
                        "summary": analysis.get("summary", ""),
                        "category": analysis.get("category", ""),
                        "reason": analysis.get("reason", "")
                    })

                print(f"4. Сохраняем обработанное сообщение ID={message.id}", flush=True)

                mark_as_processed(processed_key)
                processed.add(processed_key)

                print(f"5. Обновляем state.json, ID={message.id}", flush=True)

                state[str(chat)] = message.id
                save_state(state)

                print(f"6. Сообщение ID={message.id} полностью обработано", flush=True)

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
