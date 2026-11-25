"""Переносит позиции чатов к последним сообщениям."""

import argparse
import asyncio
import fcntl
import random
import time
from pathlib import Path

from telethon.errors import FloodWaitError

from config import CHAT_DELAY_MAX, CHAT_DELAY_MIN
from state import load_state, save_state


LOCK_FILE = Path(__file__).parent / "collector.lock"


async def main(dry_run):
    # Та же блокировка, что и у коллектора: одновременно работать нельзя.
    with open(LOCK_FILE, "a", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Коллектор уже работает. Остановите его и повторите запуск.")
            return

        state = load_state()
        remaining = state.get("_flood_wait_until", 0) - time.time()
        if remaining > 0:
            print(f"Действует FloodWait: осталось {remaining:.0f} секунд.")
            return

        # Импорт после блокировки: при импорте создаётся Telethon-клиент.
        from tg_collector import CHATS, client

        positions = {}
        errors = []
        try:
            await client.start()
            for index, chat in enumerate(dict.fromkeys(CHATS)):
                if index:
                    await asyncio.sleep(random.uniform(CHAT_DELAY_MIN, CHAT_DELAY_MAX))

                try:
                    messages = await client.get_messages(chat, limit=1)
                    if not messages:
                        print(f"{chat}: сообщений нет, позиция не изменится")
                        continue

                    message = messages[0]
                    old_id = state.get(str(chat))
                    if old_id is not None and message.id < old_id:
                        raise ValueError("последний ID меньше сохранённого")

                    positions[str(chat)] = message.id
                    print(
                        f"{chat}: {old_id} → {message.id}, "
                        f"дата последнего сообщения: {message.date.isoformat()}"
                    )
                except FloodWaitError:
                    raise
                except Exception as error:
                    errors.append(str(chat))
                    print(f"Ошибка чата {chat}: {error}")

            if errors:
                print("Есть ошибки получения чатов. Позиции не изменены.")
            elif not dry_run:
                state.update(positions)
                save_state(state)
                print(f"Позиции обновлены: {len(positions)} чатов.")
            else:
                print("Предварительный просмотр завершён. Позиции не изменены.")

        except FloodWaitError as error:
            state["_flood_wait_until"] = time.time() + error.seconds
            save_state(state)
            print(f"FloodWait: {error.seconds} секунд. Позиции не изменены.")
        finally:
            if client.is_connected():
                await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="показать позиции без их записи"
    )
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
