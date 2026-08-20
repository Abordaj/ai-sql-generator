// =========================================================
// Состояние приложения
// =========================================================

// Здесь после загрузки /api/config будет храниться
// несекретная конфигурация интерфейса.
let appConfig = null;

// Счётчик нужен для создания уникального ID каждой Mermaid-диаграммы.
let mermaidRenderCounter = 0;


// =========================================================
// DOM-элементы
// =========================================================

const promptInput = document.getElementById("prompt");
const charCount = document.getElementById("char-count");

const providerSelect = document.getElementById("provider-select");
const providerBadge = document.getElementById("provider-badge");
const modelSelect = document.getElementById("model-select");

const temperatureSlider = document.getElementById("temperature-slider");
const temperatureValue = document.getElementById("temperature-value");

const generateButton = document.getElementById("generate-button");
const generateButtonText = document.getElementById("generate-button-text");
const buttonLoader = document.getElementById("button-loader");

const errorMessage = document.getElementById("error-message");

const resultsSection = document.getElementById("results-section");

const databaseDescription = document.getElementById("database-description");
const mermaidDiagram = document.getElementById("mermaid-diagram");
const mermaidError = document.getElementById("mermaid-error");

const sqlQuery = document.getElementById("sql-query");
const explanation = document.getElementById("explanation");

const copyButton = document.getElementById("copy-button");


// =========================================================
// Mermaid
// =========================================================

// Mermaid используется только для визуализации ER-диаграммы.
// startOnLoad отключён, потому что диаграммы появляются динамически
// после ответа backend.
mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: "default",
});


// =========================================================
// Вспомогательные функции
// =========================================================

function showError(message) {
    errorMessage.textContent = message;
    errorMessage.hidden = false;
}


function hideError() {
    errorMessage.textContent = "";
    errorMessage.hidden = true;
}


function setLoading(isLoading) {
    generateButton.disabled = isLoading;
    buttonLoader.hidden = !isLoading;

    generateButtonText.textContent = isLoading
        ? "Генерация..."
        : "Сгенерировать";
}


// Человекочитаемые названия провайдеров.
// Значения option при этом остаются такими,
// какие ожидает Flask backend.
function getProviderLabel(provider) {
    const labels = {
        gemini: "Gemini",
        yandexgpt: "YandexGPT",
    };

    return labels[provider] || provider;
}


/**
 * Обновляет визуальный бейдж выбранного LLM-провайдера.
 */
function updateProviderBadge(provider) {
    if (!providerBadge) {
        return;
    }

    // Сначала удаляем классы предыдущего провайдера.
    providerBadge.classList.remove(
        "provider-badge-yandex",
        "provider-badge-gemini"
    );

    if (provider === "gemini") {
        providerBadge.textContent = "G";
        providerBadge.classList.add("provider-badge-gemini");
        return;
    }

    // YandexGPT используется как вариант по умолчанию.
    providerBadge.textContent = "Y";
    providerBadge.classList.add("provider-badge-yandex");
}


// =========================================================
// Работа со списком моделей
// =========================================================

function fillModels(provider) {
    updateProviderBadge(provider);

    modelSelect.innerHTML = "";

    const models = appConfig.models[provider] || [];

    for (const model of models) {
        const option = document.createElement("option");

        option.value = model;
        option.textContent = model;

        modelSelect.appendChild(option);
    }

    // Если для провайдера задана модель по умолчанию,
    // выбираем её автоматически.
    const defaultModel = appConfig.default_models[provider];

    if (defaultModel && models.includes(defaultModel)) {
        modelSelect.value = defaultModel;
    }
}


/**
 * Обновляет значение температуры и заполнение дорожки ползунка.
 */
function updateTemperatureDisplay() {
    const min = Number(temperatureSlider.min);
    const max = Number(temperatureSlider.max);
    const value = Number(temperatureSlider.value);

    // Показываем текущее значение температуры.
    temperatureValue.textContent = value.toFixed(1);

    // Рассчитываем, какой процент дорожки должен быть закрашен.
    const progress = ((value - min) / (max - min)) * 100;

    // Передаём рассчитанный процент в CSS.
    temperatureSlider.style.setProperty(
        "--range-progress",
        `${progress}%`
    );
}


// =========================================================
// Счётчик символов
// =========================================================

function updateCharCount() {
    const currentLength = promptInput.value.length;
    const maximumLength = appConfig?.maximum_input_length;

    if (maximumLength) {
        charCount.textContent = `${currentLength} / ${maximumLength}`;
    } else {
        charCount.textContent = String(currentLength);
    }
}


// =========================================================
// Загрузка конфигурации backend
// =========================================================

async function loadConfig() {
    try {
        const response = await fetch("/api/config");

        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Не удалось загрузить конфигурацию приложения"
            );
        }

        appConfig = data;

        // -----------------------------
        // Провайдеры
        // -----------------------------

        providerSelect.innerHTML = "";

        for (const provider of appConfig.providers) {
            const option = document.createElement("option");

            option.value = provider;
            option.textContent = getProviderLabel(provider);

            providerSelect.appendChild(option);
        }

        providerSelect.value = appConfig.default_provider;

        fillModels(appConfig.default_provider);

        // -----------------------------
        // Температура
        // -----------------------------

        temperatureSlider.min = appConfig.minimum_temperature;
        temperatureSlider.max = appConfig.maximum_temperature;
        temperatureSlider.step = "0.1";
        temperatureSlider.value = appConfig.default_temperature;

        updateTemperatureDisplay();

        temperatureValue.textContent = temperatureSlider.value;

        // -----------------------------
        // Максимальная длина prompt
        // -----------------------------

        promptInput.maxLength = appConfig.maximum_input_length;

        updateCharCount();

    } catch (error) {
        console.error("Ошибка загрузки конфигурации:", error);

        showError(
            "Не удалось загрузить настройки приложения. Обновите страницу."
        );

        generateButton.disabled = true;
    }
}


// =========================================================
// Отрисовка Mermaid
// =========================================================

async function renderMermaid(mermaidCode) {
    mermaidDiagram.innerHTML = "";
    mermaidError.hidden = true;

    /*
     * LLM иногда возвращает Mermaid-код внутри Markdown-блока:
     *
     * ```mermaid
     * erDiagram
     * ...
     * ```
     *
     * Mermaid.js ожидает только сам код диаграммы,
     * поэтому перед рендерингом удаляем Markdown-обёртку.
     */
    let cleanMermaidCode = String(mermaidCode || "").trim();

    cleanMermaidCode = cleanMermaidCode
        .replace(/^```mermaid\s*/i, "")
        .replace(/^```\s*/i, "")
        .replace(/\s*```$/i, "")
        .trim();

    /*
     * Для текущего приложения LLM должна возвращать ER-диаграмму.
     * Если перед erDiagram модель добавила поясняющий текст,
     * отбрасываем всё, что находится перед началом диаграммы.
     */
    const erDiagramIndex = cleanMermaidCode
        .toLowerCase()
        .indexOf("erdiagram");

    if (erDiagramIndex !== -1) {
        cleanMermaidCode = cleanMermaidCode.slice(erDiagramIndex);
    }

    if (!cleanMermaidCode) {
        mermaidError.textContent =
            "Модель не вернула код ER-диаграммы.";
        mermaidError.hidden = false;
        return;
    }

    try {
        mermaidRenderCounter += 1;

        const diagramId =
            `mermaid-diagram-${mermaidRenderCounter}`;

        const { svg } = await mermaid.render(
            diagramId,
            cleanMermaidCode
        );

        /*
         * innerHTML используется только для SVG,
         * который сформировала библиотека Mermaid.
         */
        mermaidDiagram.innerHTML = svg;
    } catch (error) {
        console.error(
            "Ошибка Mermaid:",
            error,
            "\nКод диаграммы:",
            cleanMermaidCode
        );

        mermaidError.textContent =
            "Не удалось отобразить ER-диаграмму.";

        mermaidError.hidden = false;
    }
}


// =========================================================
// Отображение результата
// =========================================================

async function displayResults(result) {
    // Ответ LLM выводится как текст через textContent.
    // Это не позволяет содержимому SQL или explanation
    // интерпретироваться браузером как HTML.
    databaseDescription.textContent = result.database_description;
    sqlQuery.textContent = result.sql_query;
    explanation.textContent = result.explanation;

    resultsSection.hidden = false;

    await renderMermaid(result.mermaid_code);

    // После генерации прокручиваем страницу к результату.
    resultsSection.scrollIntoView({
        behavior: "smooth",
        block: "start",
    });
}


// =========================================================
// Генерация SQL
// =========================================================

async function generateSql() {
    hideError();

    const prompt = promptInput.value.trim();
    const provider = providerSelect.value;
    const model = modelSelect.value;
    const temperature = Number(temperatureSlider.value);

    if (!prompt) {
        showError("Введите запрос для генерации SQL.");
        promptInput.focus();
        return;
    }

    if (!provider) {
        showError("Выберите провайдера.");
        return;
    }

    if (!model) {
        showError("Выберите модель.");
        return;
    }

    if (
        appConfig &&
        prompt.length > appConfig.maximum_input_length
    ) {
        showError(
            `Запрос слишком длинный. Максимум: ${appConfig.maximum_input_length} символов.`
        );

        return;
    }

    setLoading(true);

    try {
        const response = await fetch("/api/generate", {
            method: "POST",

            headers: {
                "Content-Type": "application/json",
            },

            body: JSON.stringify({
                prompt,
                provider,
                model,
                temperature,
            }),
        });

        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }

        const data = await response.json();

        if (!response.ok) {
            showError(
                data.error || "Не удалось выполнить генерацию."
            );

            return;
        }

        await displayResults(data);

    } catch (error) {
        console.error("Ошибка запроса к backend:", error);

        showError(
            "Не удалось связаться с сервером. Попробуйте ещё раз."
        );

    } finally {
        setLoading(false);
    }
}


// =========================================================
// Копирование SQL
// =========================================================

async function copySql() {
    const sql = sqlQuery.textContent;

    if (!sql) {
        return;
    }

    try {
        await navigator.clipboard.writeText(sql);

        const previousText = copyButton.textContent;

        copyButton.textContent = "Скопировано";

        setTimeout(() => {
            copyButton.textContent = previousText;
        }, 1500);

    } catch (error) {
        console.error("Не удалось скопировать SQL:", error);

        showError(
            "Не удалось скопировать SQL в буфер обмена."
        );
    }
}


// =========================================================
// События интерфейса
// =========================================================

providerSelect.addEventListener("change", () => {
    if (!appConfig) {
        return;
    }

    fillModels(providerSelect.value);
});


temperatureSlider.addEventListener(
    "input",
    updateTemperatureDisplay
);


promptInput.addEventListener("input", () => {
    updateCharCount();
});


generateButton.addEventListener("click", () => {
    generateSql();
});


copyButton.addEventListener("click", () => {
    copySql();
});


// Дополнительно разрешаем запуск генерации через Ctrl + Enter.
promptInput.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key === "Enter") {
        event.preventDefault();

        if (!generateButton.disabled) {
            generateSql();
        }
    }
});


// =========================================================
// Инициализация страницы
// =========================================================

// Получаем конфигурацию только после загрузки интерфейса.
// API-ключи через этот endpoint не передаются.
loadConfig();