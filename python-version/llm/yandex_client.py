import json
import os

from openai import OpenAI


class YandexClient:
    """
    Клиент для обращения к YandexGPT через OpenAI-compatible API.
    """

    def __init__(self):
        # Секреты получаем только из переменных окружения.
        # Они не должны храниться в исходном коде или config.json.
        self.api_key = os.getenv("YANDEX_API_KEY")
        self.folder_id = os.getenv("YANDEX_FOLDER_ID")

        if not self.api_key:
            raise RuntimeError("Не задан YANDEX_API_KEY")

        if not self.folder_id:
            raise RuntimeError("Не задан YANDEX_FOLDER_ID")

        # Yandex AI Studio предоставляет OpenAI-compatible endpoint,
        # поэтому для работы можно использовать официальный OpenAI SDK.
        #
        # Folder ID передаётся как project, чтобы SDK сформировал
        # необходимый заголовок OpenAI-Project.
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://ai.api.cloud.yandex.net/v1",
            project=self.folder_id,
            timeout=30.0,
        )

    def generate_sql(
        self,
        prompt,
        model,
        temperature,
        system_prompt,
    ):
        """
        Отправляет пользовательскую задачу в YandexGPT и возвращает
        проверенный структурированный результат в виде Python dict.
        """

        # Имя модели хранится в config.json без Folder ID.
        # Перед вызовом API формируем полный URI модели.
        model_uri = f"gpt://{self.folder_id}/{model}"

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        # Схема фиксирует формат результата.
        # Это снижает вероятность того, что модель вернёт свободный текст
        # вместо объекта, который ожидает backend приложения.
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "sql_generation_result",
                "schema": {
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
                },
            },
        }

        try:
            # Один пользовательский запрос соответствует одному
            # обращению к LLM.
            response = self.client.chat.completions.create(
                model=model_uri,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
            )

        except Exception as error:
            # Не передаём наружу исходный текст ошибки API,
            # поскольку он потенциально может содержать служебные детали.
            raise RuntimeError(
                "Ошибка при обращении к YandexGPT"
            ) from error

        # Проверяем, что API действительно вернул хотя бы один ответ.
        if not response.choices:
            raise RuntimeError("YandexGPT вернул пустой ответ")

        model_response = response.choices[0].message.content

        if not isinstance(model_response, str) or not model_response.strip():
            raise RuntimeError("YandexGPT вернул пустой ответ")

        model_response = model_response.strip()

        # Structured output должен вернуть чистый JSON,
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
                "YandexGPT вернул некорректный JSON"
            ) from error

        if not isinstance(result, dict):
            raise RuntimeError(
                "Ответ YandexGPT имеет неправильную структуру"
            )

        required_fields = {
            "database_description",
            "mermaid_code",
            "sql_query",
            "explanation",
        }

        # Проверяем именно обязательные поля, а не все значения объекта.
        if not required_fields.issubset(result.keys()):
            raise RuntimeError(
                "Ответ YandexGPT не содержит обязательных полей"
            )

        for field in required_fields:
            if (
                not isinstance(result[field], str)
                or not result[field].strip()
            ):
                raise RuntimeError(
                    "Ответ YandexGPT содержит некорректные данные"
                )

        # Возвращаем только ожидаемые приложением поля.
        return {
            "database_description": result["database_description"],
            "mermaid_code": result["mermaid_code"],
            "sql_query": result["sql_query"],
            "explanation": result["explanation"],
        }