import streamlit as st
import google.generativeai as genai
import requests
import json
from PIL import Image
from io import BytesIO

# Настройка API
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
HF_TOKEN = st.secrets["HF_TOKEN"]  # Hugging Face токен

# Инициализация состояния игры
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.inventory = ["волшебная палочка", "зелье здоровья"]
    st.session_state.stats = {"сила": 5, "ловкость": 7, "интеллект": 8}
    st.session_state.current_image = None
    st.session_state.current_actions = []
    st.session_state.gemini_chat = None

# Системная инструкция для Gemini (аналог system prompt)
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

# --- Боковая панель ---
with st.sidebar:
    st.header("🎭 Персонаж")
    universe = st.selectbox("Вселенная", ["Гарри Поттер", "Ведьмак", "Киберпанк"])
    character = st.text_input("Имя персонажа", "Гарри")
    
    st.subheader("⚔️ Характеристики")
    for stat in st.session_state.stats:
        st.session_state.stats[stat] = st.slider(stat, 1, 10, st.session_state.stats[stat], disabled=True)
    
    st.subheader("🎒 Инвентарь")
    st.write(st.session_state.inventory)
    
    if st.button("Начать заново"):
        st.session_state.messages = []
        st.session_state.inventory = ["волшебная палочка", "зелье здоровья"]
        st.session_state.current_actions = []
        st.session_state.gemini_chat = None
        st.rerun()

# --- Генерация через Gemini ---
def ask_gemini(action=None):
    model = genai.GenerativeModel("gemini-1.5-flash")
    # Собираем системный промпт с текущими параметрами
    full_prompt = SYSTEM_PROMPT.format(
        universe=universe,
        character=character,
        stats=json.dumps(st.session_state.stats, ensure_ascii=False),
        inventory=", ".join(st.session_state.inventory)
    )
    if action:
        full_prompt += f"\nИгрок выбрал действие: {action}"
    else:
        full_prompt += "\nСгенерируй стартовую сцену."
    
    response = model.generate_content(full_prompt)
    raw = response.text
    # Gemini иногда оборачивает в ```json, убираем
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

# --- Генерация картинки через Hugging Face ---
def generate_image(prompt):
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt + ", digital painting, atmospheric"}
    response = requests.post(API_URL, headers=headers, json=payload)
    if response.status_code == 200:
        return Image.open(BytesIO(response.content))
    else:
        # Если лимит бесплатного тира исчерпан, показываем заглушку
        return None

# --- Основной экран ---
st.title(f"📖 AI-фанфик: {universe}")

# Отображение текущей сцены
if st.session_state.current_image:
    st.image(st.session_state.current_image, caption="Текущая локация")
if st.session_state.messages:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "assistant":
        st.markdown(last_msg["content"])

# Кнопки действий
if st.session_state.current_actions:
    st.subheader("Что делать?")
    cols = st.columns(len(st.session_state.current_actions))
    for i, act in enumerate(st.session_state.current_actions):
        if cols[i].button(act):
            with st.spinner("✨ Генерация продолжения..."):
                data = ask_gemini(act)
                
                # Обновляем историю
                st.session_state.messages.append({"role": "user", "content": act})
                st.session_state.messages.append({"role": "assistant", "content": data["description"]})
                
                # Инвентарь
                for change in data.get("inventory_changes", []):
                    if change.startswith("+"):
                        st.session_state.inventory.append(change[1:])
                    elif change.startswith("-"):
                        item = change[1:]
                        if item in st.session_state.inventory:
                            st.session_state.inventory.remove(item)
                
                # Характеристики
                for stat, delta in data.get("stat_changes", {}).items():
                    if stat in st.session_state.stats:
                        st.session_state.stats[stat] = max(0, st.session_state.stats[stat] + delta)
                
                # Картинка
                img_prompt = data.get("image_prompt", "fantasy world")
                st.session_state.current_image = generate_image(img_prompt)
                st.session_state.current_actions = data["actions"]
                
                st.rerun()

else:
    # Начало игры
    if st.button("Начать приключение"):
        with st.spinner("🌍 Создаём мир..."):
            data = ask_gemini()
            st.session_state.messages.append({"role": "assistant", "content": data["description"]})
            st.session_state.current_image = generate_image(data["image_prompt"])
            st.session_state.current_actions = data["actions"]
            st.rerun()