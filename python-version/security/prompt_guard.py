import re
import unicodedata


# Сообщение возвращается пользователю, если обнаружена попытка
# изменить назначение AI-ассистента или получить служебные данные.
PROMPT_INJECTION_MESSAGE = (
    "Запрос отклонён: обнаружена попытка изменить инструкции "
    "AI-ассистента. Сформулируйте только задачу для генерации SQL."
)

INVALID_PROMPT_MESSAGE = "Некорректный запрос"


def _normalize_text(text: str) -> str:
    """
    Нормализует пользовательский текст перед проверкой.

    NFKC приводит разные Unicode-варианты символов к более
    однородному представлению. Затем текст переводится в нижний
    регистр, а табуляции, переносы строк и повторяющиеся пробелы
    заменяются одним пробелом.
    """

    normalized = unicodedata.normalize("NFKC", text)

    # Удаляем zero-width символы, которые иногда используются
    # для искусственного разделения подозрительных слов.
    normalized = normalized.replace("\u200b", "")
    normalized = normalized.replace("\u200c", "")
    normalized = normalized.replace("\u200d", "")
    normalized = normalized.replace("\ufeff", "")

    normalized = normalized.lower().strip()

    # \s включает обычные пробелы, табуляции и переносы строк.
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized


# Ищем именно сочетания слов и команды, а не отдельные слова.
# Поэтому обычные SQL-запросы со словами developer, role, admin,
# system или password сами по себе не считаются атакой.
SUSPICIOUS_PATTERNS = (
    # ---------------------------------------------------------
    # Попытки отменить или заменить действующие инструкции
    # ---------------------------------------------------------
    re.compile(
        r"\b(?:ignore|disregard|forget)\b.{0,40}"
        r"\b(?:previous|prior|all|system|developer)?\s*"
        r"(?:instructions|rules|prompt)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:игнорируй|игнорировать|забудь|забыть)\b.{0,40}"
        r"\b(?:предыдущие|все|системные)?\s*"
        r"(?:инструкции|правила|указания)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bне\s+следуй\b.{0,30}\b"
        r"(?:предыдущим|системным)?\s*инструкциям\b",
        re.IGNORECASE,
    ),

    # ---------------------------------------------------------
    # Попытки раскрыть системные или служебные инструкции
    # ---------------------------------------------------------
    re.compile(
        r"\b(?:show|reveal|print|display|expose)\b.{0,30}"
        r"\b(?:system\s+prompt|developer\s+instructions|"
        r"hidden\s+instructions|internal\s+instructions)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:покажи|раскрой|выведи|отобрази)\b.{0,30}"
        r"\b(?:системный\s+промпт|системные\s+инструкции|"
        r"инструкции\s+разработчика|скрытые\s+инструкции|"
        r"внутренние\s+инструкции)\b",
        re.IGNORECASE,
    ),

    # ---------------------------------------------------------
    # Попытки получить секреты и переменные окружения
    # ---------------------------------------------------------
    re.compile(
        r"\b(?:show|reveal|print|display|read|open|expose)\b.{0,30}"
        r"\b(?:api\s*key|api\s*keys|environment\s+variables|"
        r"env\s+variables|credentials|secrets?|passwords?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:read|open|show|print|reveal)\b.{0,20}"
        r"(?:the\s+)?\.env\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:покажи|раскрой|выведи|прочитай|открой)\b.{0,30}"
        r"\b(?:api\s*ключ|ключ\s*api|переменные\s+окружения|"
        r"учётные\s+данные|учетные\s+данные|секреты|пароль)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:прочитай|открой|покажи|выведи)\b.{0,20}\.env\b",
        re.IGNORECASE,
    ),

    # ---------------------------------------------------------
    # Попытки получить доступ к локальным/серверным файлам
    # или заставить модель выполнять команды
    # ---------------------------------------------------------
    re.compile(
        r"\b(?:read|access|open)\b.{0,30}"
        r"\b(?:local|server|system)\s+files?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:execute|run)\b.{0,20}"
        r"\b(?:shell\s+command|system\s+command|command)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:прочитай|открой|получи\s+доступ\s+к)\b.{0,30}"
        r"\b(?:локальным|серверным|системным|файлам\s+сервера)"
        r".{0,10}\b(?:файлам)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:выполни|запусти)\b.{0,20}"
        r"\b(?:shell[- ]?команду|системную\s+команду|команду)\b",
        re.IGNORECASE,
    ),

    # ---------------------------------------------------------
    # Попытки изменить роль модели или отключить ограничения
    # ---------------------------------------------------------
    re.compile(
        r"\b(?:change|switch)\b.{0,20}\b(?:your\s+)?role\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:act\s+as|pretend\s+to\s+be)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:developer\s+mode|jailbreak)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:bypass|disable|remove)\b.{0,20}"
        r"\b(?:restrictions|security|safety|guardrails)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:измени|смени)\b.{0,20}\b(?:свою\s+)?роль\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:действуй\s+как|притворись)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bрежим\s+разработчика\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:обойди|отключи|убери)\b.{0,20}"
        r"\b(?:ограничения|защиту|правила\s+безопасности)\b",
        re.IGNORECASE,
    ),

    # ---------------------------------------------------------
    # Попытки получить скрытые внутренние рассуждения модели
    # ---------------------------------------------------------
    re.compile(
        r"\b(?:show|reveal|print)\b.{0,30}"
        r"\b(?:chain\s+of\s+thought|hidden\s+reasoning|"
        r"internal\s+reasoning)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:покажи|раскрой|выведи)\b.{0,30}"
        r"\b(?:цепочку\s+рассуждений|скрытые\s+рассуждения|"
        r"внутренние\s+рассуждения)\b",
        re.IGNORECASE,
    ),
)


def validate_prompt(prompt, max_length):
    """
    Проверяет пользовательский запрос перед отправкой в LLM.

    Возвращает:
        (True, None) — запрос можно передавать модели.

        (False, сообщение) — запрос должен быть отклонён.
    """

    # Сначала проверяем базовую корректность входных данных,
    # чтобы дальнейшие операции всегда выполнялись со строкой.
    if not isinstance(prompt, str):
        return False, INVALID_PROMPT_MESSAGE

    prompt = prompt.strip()

    if not prompt:
        return False, INVALID_PROMPT_MESSAGE

    if not isinstance(max_length, int) or max_length <= 0:
        return False, INVALID_PROMPT_MESSAGE

    if len(prompt) > max_length:
        return False, INVALID_PROMPT_MESSAGE

    normalized_prompt = _normalize_text(prompt)

    # Проверяем весь нормализованный текст по каждой группе
    # подозрительных конструкций. Одиночные слова специально
    # не используются как критерий блокировки, чтобы не мешать
    # обычным SQL-запросам.
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(normalized_prompt):
            return False, PROMPT_INJECTION_MESSAGE

    return True, None