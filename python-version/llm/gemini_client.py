import json
import os

from google import genai
from google.genai import types


class GeminiClient:
    """
    Клиент для обращения к Gemini API.
    """

    def __init__(self):
        # API-ключ берём только из переменной окружения.
        # Он не должен храниться в коде или config.json.
        self.api_key = os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            raise RuntimeError("Не задан GEMINI_API_KEY")

        # Используем актуальный Google Gen AI SDK.
        self.client = genai.Client(api_key=self.api_key)

    def generate_sql(
        self,
        prompt,
        model,
        temperature,
        system_prompt,
    ):
        """
        Отправляет запрос в Gemini и возвращает проверенный
        структурированный результат в виде Python dict.
        """

        # JSON Schema задаёт ожидаемый формат ответа модели.
        # Это снижает вероятность получения произвольного текста.
        response_schema = {
            "type": "object",
            "properties": {
                "database_description": {
                    "type": "string"
                },
                "mermaid_code": {
                    "type": "string"
                },
                "sql_query": {
                    "type": "string"
                },
                "explanation": {
                    "type": "string"
                },
            },
            "required": [
                "database_description",
                "mermaid_code",
                "sql_query",
                "explanation",
            ],
            "additionalProperties": False,
        }

        # System prompt передаётся отдельно от пользовательского текста.
        # Пользовательский запрос остаётся только содержанием задачи.
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            response_mime_type="application/json",
            response_json_schema=response_schema,

            # В приложении не используется Function Calling.
            # Явно отключаем AFC, чтобы SDK не пытался применять
            # механизм автоматического вызова функций.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )

        try:
            # Один пользовательский запрос соответствует одному
            # обращению к Gemini API.
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

        except Exception as error:
            # Техническую ошибку выводим только в локальный терминал.
            print(
                f"Gemini API error: {type(error).__name__}: {error}"
            )

            raise RuntimeError(
                "Ошибка при обращении к Gemini API"
            ) from error

        model_response = response.text

        if not isinstance(model_response, str) or not model_response.strip():
            raise RuntimeError("Gemini вернул пустой ответ")

        model_response = model_response.strip()

        # Structured output обычно возвращает чистый JSON,
        # но дополнительно обрабатываем возможные Markdown fences.
        if model_response.startswith("```json"):
            model_response = model_response[7:]

        elif model_response.startswith("```"):
            model_response = model_response[3:]

        if model_response.endswith("```"):
            model_response = model_response[:-3]

        model_response = model_response.strip()

        try:
            result = json.loads(model_response)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Gemini вернул некорректный JSON"
            ) from error

        if not isinstance(result, dict):
            raise RuntimeError(
                "Ответ Gemini имеет неправильную структуру"
            )

        required_fields = {
            "database_description",
            "mermaid_code",
            "sql_query",
            "explanation",
        }

        # Backend ожидает именно эти четыре обязательных поля.
        if not required_fields.issubset(result.keys()):
            raise RuntimeError(
                "Ответ Gemini не содержит обязательных полей"
            )

        for field in required_fields:
            if (
                not isinstance(result[field], str)
                or not result[field].strip()
            ):
                raise RuntimeError(
                    "Ответ Gemini содержит некорректные данные"
                )

        # Возвращаем только данные, которые ожидает app.py.
        return {
            "database_description": result["database_description"],
            "mermaid_code": result["mermaid_code"],
            "sql_query": result["sql_query"],
            "explanation": result["explanation"],
        }