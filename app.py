import streamlit as st
import requests
import json
from PIL import Image
from io import BytesIO

# Ключи
YANDEX_API_KEY = st.secrets["YANDEX_API_KEY"]
YANDEX_FOLDER_ID = st.secrets["YANDEX_FOLDER_ID"]
HF_TOKEN = st.secrets["HF_TOKEN"]

# Инициализация игры
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.inventory = ["волшебная палочка", "зелье здоровья"]
    st.session_state.stats = {"сила": 5, "ловкость": 7, "интеллект": 8}
    st.session_state.current_image = None
    st.session_state.current_actions = []

SYSTEM_PROMPT = """Ты — мастер текстовой RPG. Вселенная: {universe}.
Игрок — {character}. Характеристики: {stats}. Инвентарь: {inventory}.
Отвечай строго в JSON:
{{
  "description": "описание сцены на русском",
  "image_prompt": "короткий промпт на английском для генерации картинки, стиль fantasy art",
  "actions": ["действие 1", "действие 2", "действие 3"],
  "inventory_changes": ["+предмет" или "-предмет", ...],
  "stat_changes": {{"сила": +1, "ловкость": -1}}
}}
Если это начало игры, опиши стартовую локацию."""

# Боковая панель
with st.sidebar:
    st.header("🎭 Персонаж")
    universe = st.selectbox("Вселенная", ["Гарри Поттер", "Ведьмак", "Киберпанк"])
    character = st.text_input("Имя персонажа", "Гарри")
    
    st.subheader("⚔️ Характеристики")
    for stat in st.session_state.stats:
        st.session_state.stats[stat] = st.slider(stat, 1, 10, st.session_state.stats[stat], disabled=True)
    
    st.subheader("🎒 Инвентарь")
    st.write(st.session_state.inventory)
    
    st.subheader("🧠 Генератор текста")
    text_engine = st.radio("Выбери движок", ["YandexGPT", "Hugging Face (бесплатно)"], index=0)
    
    if st.button("Начать заново"):
        st.session_state.messages = []
        st.session_state.inventory = ["волшебная палочка", "зелье здоровья"]
        st.session_state.current_actions = []
        st.rerun()

# --- Функции генерации текста ---

def ask_yandex(action=None):
    system_prompt = SYSTEM_PROMPT.format(
        universe=universe, character=character,
        stats=json.dumps(st.session_state.stats, ensure_ascii=False),
        inventory=", ".join(st.session_state.inventory)
    )
    messages = [{"role": "system", "content": system_prompt}]
    if action:
        messages.append({"role": "user", "content": action})
    else:
        messages.append({"role": "user", "content": "Начни игру."})
    
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {"stream": False, "temperature": 0.9, "maxTokens": 2000},
        "messages": messages
    }
    resp = requests.post(url, headers=headers, json=data)
    resp_json = resp.json()
    
    # Диагностика: если ошибка, показываем сырой ответ
    if "result" not in resp_json:
        st.error(f"❌ YandexGPT вернул ошибку: {resp_json}")
        return None
    raw = resp_json["result"]["alternatives"][0]["message"]["text"]
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

def ask_huggingface(action=None):
    system_prompt = SYSTEM_PROMPT.format(
        universe=universe, character=character,
        stats=json.dumps(st.session_state.stats, ensure_ascii=False),
        inventory=", ".join(st.session_state.inventory)
    )
    prompt = f"{system_prompt}\n"
    if action:
        prompt += f"Игрок выбрал действие: {action}\n"
    else:
        prompt += "Сгенерируй стартовую сцену.\n"
    prompt += "Ответь ТОЛЬКО в JSON:"
    
    API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt}
    resp = requests.post(API_URL, headers=headers, json=payload)
    if resp.status_code != 200:
        st.error(f"❌ Hugging Face text error: {resp.status_code} {resp.text}")
        return None
    result = resp.json()
    # Hugging Face возвращает список или объект
    if isinstance(result, list) and len(result) > 0:
        raw = result[0].get("generated_text", "")
    else:
        raw = result.get("generated_text", "")
    # Ищем JSON в ответе
    try:
        json_start = raw.index("{")
        json_end = raw.rindex("}") + 1
        raw_json = raw[json_start:json_end]
    except ValueError:
        st.error("❌ Не удалось найти JSON в ответе HF")
        return None
    return json.loads(raw_json)

# --- Генерация картинки ---
def generate_image(prompt):
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt + ", digital painting, atmospheric"}
    resp = requests.post(API_URL, headers=headers, json=payload)
    if resp.status_code == 200:
        return Image.open(BytesIO(resp.content))
    else:
        return None

# --- Основной интерфейс ---
st.title(f"📖 AI-фанфик: {universe}")

if st.session_state.current_image:
    st.image(st.session_state.current_image, caption="Текущая локация")
if st.session_state.messages:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "assistant":
        st.markdown(last_msg["content"])

if st.session_state.current_actions:
    st.subheader("Что делать?")
    cols = st.columns(len(st.session_state.current_actions))
    for i, act in enumerate(st.session_state.current_actions):
        if cols[i].button(act):
            with st.spinner("✨ Генерация продолжения..."):
                if text_engine == "YandexGPT":
                    data = ask_yandex(act)
                else:
                    data = ask_huggingface(act)
                if data is None:
                    st.stop()
                
                st.session_state.messages.append({"role": "user", "content": act})
                st.session_state.messages.append({"role": "assistant", "content": data["description"]})
                
                for change in data.get("inventory_changes", []):
                    if change.startswith("+"):
                        st.session_state.inventory.append(change[1:])
                    elif change.startswith("-"):
                        item = change[1:]
                        if item in st.session_state.inventory:
                            st.session_state.inventory.remove(item)
                
                for stat, delta in data.get("stat_changes", {}).items():
                    if stat in st.session_state.stats:
                        st.session_state.stats[stat] = max(0, st.session_state.stats[stat] + delta)
                
                img_prompt = data.get("image_prompt", "fantasy world")
                st.session_state.current_image = generate_image(img_prompt)
                st.session_state.current_actions = data["actions"]
                st.rerun()
else:
    if st.button("Начать приключение"):
        with st.spinner("🌍 Создаём мир..."):
            if text_engine == "YandexGPT":
                data = ask_yandex()
            else:
                data = ask_huggingface()
            if data is None:
                st.stop()
            
            st.session_state.messages.append({"role": "assistant", "content": data["description"]})
            st.session_state.current_image = generate_image(data["image_prompt"])
            st.session_state.current_actions = data["actions"]
            st.rerun()
