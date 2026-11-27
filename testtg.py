import asyncio
from telethon import TelegramClient
from config import API_ID, API_HASH


async def main():
    client = TelegramClient(
        "test_new_account",
        API_ID,
        API_HASH,
        flood_sleep_threshold=0
    )

    await client.connect()

    try:
        phone = input("Номер телефона: ")
        result = await client.send_code_request(phone)

        print("Тип доставки:", type(result.type).__name__)
        print("Следующий способ:", result.next_type)
        print("Таймаут:", result.timeout)

    except Exception as e:
        print(type(e).__name__, str(e))

    finally:
        await client.disconnect()


asyncio.run(main())