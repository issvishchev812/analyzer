import json

from config import API_KEY, MODEL, SYSTEM_PROMPT

from openrouter import OpenRouter

BATCH_SYSTEM_PROMPT = SYSTEM_PROMPT + """

### Пакетный режим

Тебе передаётся массив сообщений. Проанализируй каждое сообщение отдельно.
Вместо формата ответа выше верни JSON-массив: один объект на каждое входное
сообщение. В каждом объекте должны быть поля message_id, relevant, summary и
reason. Не добавляй Markdown, пояснения, категории или другие поля.
"""


def parse_response(content):
    result = content.strip()

    if result.startswith("```json"):
        result = result[7:]

    if result.startswith("```"):
        result = result[3:]

    if result.endswith("```"):
        result = result[:-3]

    return json.loads(result.strip())


def analyze_text(text, source=""):
    if not API_KEY:
        raise ValueError('Не найден OR_API_KEY в .env')

    prompt = text
    if source:
        prompt = f"Источник: {source}\n\nСообщение:\n{text}"

    with OpenRouter(api_key=API_KEY) as client:
        response = client.chat.send(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

    return parse_response(response.choices[0].message.content)


def analyze_batch(messages, source=""):
    """Анализирует несколько сообщений и возвращает результаты по ID сообщения."""
    if not API_KEY:
        raise ValueError("Не найден OR_API_KEY в .env")

    request_messages = [
        {"message_id": message_id, "text": text}
        for message_id, text in messages
    ]
    prompt = (
        "Проанализируй каждое сообщение из массива. "
        "Верни только корректный JSON-массив. Для каждого входного сообщения "
        "верни один объект с полями message_id, relevant, summary и reason. "
        "message_id должен совпадать с ID входного сообщения. "
        "Не добавляй других объектов или полей.\n\n"
        f"Источник: {source}\n\n"
        f"Сообщения:\n{json.dumps(request_messages, ensure_ascii=False)}"
    )

    with OpenRouter(api_key=API_KEY) as client:
        response = client.chat.send(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": BATCH_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

    result = parse_response(response.choices[0].message.content)
    if not isinstance(result, list):
        raise ValueError("LLM вернула не массив результатов")

    expected_ids = {message_id for message_id, _ in messages}
    analyses = {}

    for item in result:
        if not isinstance(item, dict) or "message_id" not in item:
            raise ValueError("LLM вернула результат без message_id")

        message_id = item["message_id"]
        if isinstance(message_id, str) and message_id.isdigit():
            message_id = int(message_id)
        if message_id not in expected_ids or message_id in analyses:
            raise ValueError("LLM вернула неизвестный или повторный message_id")

        if not isinstance(item.get("relevant"), bool):
            raise ValueError("LLM вернула некорректное поле relevant")

        analyses[message_id] = item

    if set(analyses) != expected_ids:
        raise ValueError("LLM вернула результаты не для всех сообщений")

    return analyses
