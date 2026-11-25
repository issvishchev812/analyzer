import asyncio

from tg_collector import collect_telegram
from telegram_sender import send_news

async def main():
    print("Запускаем Telegram-коллектор...", flush=True)

    try:
        posts = await collect_telegram()

        print(f"\nСбор завершён. Получено новостей: {len(posts)}")

        for post in posts:

            send_news(post)

            print("\n" + "=" * 50)
            print(f"Источник: {post['source']}")
            print(f"Краткое содержание: {post['summary']}")
            print(f"Ссылка: {post['url']}")
            print(f"Текст: {post['text'][:300]}")
            print(f"Причина: {post['reason']}")


    except KeyboardInterrupt:
        print("\nОстановка коллектора...")

    except Exception as e:
        print(f"Критическая ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
