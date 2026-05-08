import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import sqlite3
import uuid
import edge_tts
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydub import AudioSegment
from deep_translator import GoogleTranslator
from faster_whisper import WhisperModel

# ==========================================
# 1. SQLITE DATABASE CONFIGURATION
# ==========================================
DB_FILE = "database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_db_connection()
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT DEFAULT '',
                gender TEXT DEFAULT '',
                photo_path TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                original_text TEXT,
                audio_path TEXT,
                created_at DATETIME,
                type TEXT DEFAULT 'stt' 
            )
        """)
        conn.commit()
        conn.close()
        print(f"✅ SQLite Database ready: {DB_FILE}")
    except Exception as db_err:
        print(f"❌ Database Init Error: {db_err}")

init_db()

# ==========================================
# 2. FASTAPI APP SETUP
# ==========================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
os.makedirs("temp_tts", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/temp_tts", StaticFiles(directory="temp_tts"), name="temp_tts")

print("⏳ Loading Faster-Whisper 'medium'...")
try:
    stt_model = WhisperModel(
        "medium",
        device="cpu",
        compute_type="int8",
        cpu_threads=12,
        num_workers=4,
        download_root="./models"
    )
    print("✅ Medium Model ready.")
except Exception as load_err:
    print(f"❌ Load Error: {load_err}")


@app.get("/")
async def health_check():
    return {"status": "online"}

# ==========================================
# 3. AUTHENTICATION & PROFILE
# ==========================================
@app.post("/signin")
async def signin(username: str, password: str = "password123"):
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user and user['password'] == password:
            return {"status": "success", "username": username}
        raise HTTPException(status_code=401, detail="Invalid credentials")
    finally:
        conn.close()

@app.post("/signup")
async def signup(username: str, password: str = "password123"):
    conn = get_db_connection()
    try:
        if conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone():
            raise HTTPException(status_code=400, detail="Account exists.")
        conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        conn.commit()
        return {"status": "success"}
    finally:
        conn.close()

@app.get("/profile")
async def get_profile(username: str):
    conn = get_db_connection()
    try:
        user = conn.execute('SELECT username, password, name, gender, photo_path FROM users WHERE username = ?', (username,)).fetchone()
        return dict(user) if user else {}
    finally:
        conn.close()

@app.post("/update_profile")
async def update_profile(
        username: str = Form(...),
        name: str = Form(""),
        password: str = Form(""),
        gender: str = Form(""),
        file: UploadFile = File(None)
):
    conn = get_db_connection()
    try:
        photo_path = ""
        if file:
            os.makedirs(f"uploads/{username}", exist_ok=True)
            photo_path = f"uploads/{username}/profile.jpg"
            with open(photo_path, "wb") as buffer:
                buffer.write(await file.read())

        if photo_path:
            conn.execute(
                "UPDATE users SET name=?, password=?, gender=?, photo_path=? WHERE username=?",
                (name, password, gender, photo_path, username)
            )
        else:
            conn.execute(
                "UPDATE users SET name=?, password=?, gender=? WHERE username=?",
                (name, password, gender, username)
            )
        conn.commit()
        return {"status": "success"}
    finally:
        conn.close()

# ==========================================
# 4. SPEECH TO TEXT (STT) - WITH AUTO-TRANSLATE
# ==========================================
@app.post("/transcribe")
async def transcribe_audio(username: str, lang: str = "en", file: UploadFile = File(...)):
    os.makedirs(f"uploads/{username}", exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    temp_path = f"uploads/{username}/temp_{ts}.m4a"
    wav_path = f"uploads/{username}/{ts}.wav"

    lang_map = {"bangla": "bn", "japanese": "ja", "english": "en", "arabic": "ar", "spanish": "es"}
    target_lang = lang_map.get(lang.lower(), "en")

    try:
        content = await file.read()
        with open(temp_path, "wb") as buffer:
            buffer.write(content)

        audio = AudioSegment.from_file(temp_path).set_frame_rate(16000).set_channels(1)
        audio = audio.apply_gain(-20.0 - audio.dBFS)
        audio.export(wav_path, format="wav")

        # Whisper auto-translate to English first
        segments, info = stt_model.transcribe(wav_path, beam_size=5, language=None, task="translate", vad_filter=True)
        english_text = " ".join([s.text for s in segments]).strip()

        if not english_text:
            if os.path.exists(temp_path): os.remove(temp_path)
            return JSONResponse(content={"text": "No speech detected."})

        if target_lang == "en":
            final_output = english_text
        else:
            final_output = GoogleTranslator(source='en', target=target_lang).translate(english_text)

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO records (username, original_text, audio_path, created_at, type) VALUES (?, ?, ?, ?, ?)",
            (username, final_output, wav_path, datetime.now().isoformat(), 'stt')
        )
        conn.commit()
        conn.close()

        if os.path.exists(temp_path): os.remove(temp_path)
        return JSONResponse(content={"text": final_output})

    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 5. HISTORY ENDPOINT
# ==========================================
@app.get("/history")
async def get_history(username: str):
    conn = get_db_connection()
    try:
        rows = conn.execute('SELECT * FROM records WHERE username = ? ORDER BY id DESC', (username,)).fetchall()
        return JSONResponse(content={"status": "success", "history": [dict(r) for r in rows]})
    finally:
        conn.close()

# ==========================================
# 6. TEXT TO SPEECH (TTS) - ROBUST ACCENT ENGINE
# ==========================================
@app.get("/tts")
async def text_to_speech(text: str, lang: str = "US Manly", username: str = "muradsiam55@gmail.com", target_lang_name: str = "english"):
    request_id = str(uuid.uuid4())
    temp_mp3 = f"temp_tts/temp_{request_id}.mp3"

    # 20+ Global Accents and Regional Tones Mapping
    # 5 Universal Tones mapped to the best native voices
    smart_voice_map = {
        "english": {
            "Male (Standard)": "en-US-AndrewNeural",
            "Male (Soft)": "en-GB-RyanNeural",
            "Female (Standard)": "en-US-EmmaNeural",
            "Female (Soft)": "en-GB-SoniaNeural",
            "Child": "en-US-AnaNeural"
        },
        "bangla": {
            "Male (Standard)": "bn-BD-PradeepNeural",
            "Male (Soft)": "bn-IN-BashkarNeural",
            "Female (Standard)": "bn-BD-NabanitaNeural",
            "Female (Soft)": "bn-IN-TanishaNeural",
            "Child": "bn-BD-NabanitaNeural" # Fallback to soft female as edge-tts lacks a Bangla child
        },
        "japanese": {
            "Male (Standard)": "ja-JP-KeitaNeural",
            "Male (Soft)": "ja-JP-DaichiNeural",
            "Female (Standard)": "ja-JP-NanamiNeural",
            "Female (Soft)": "ja-JP-AoiNeural",
            "Child": "ja-JP-MayuNeural"
        },
        "arabic": {
            "Male (Standard)": "ar-SA-HamedNeural",
            "Male (Soft)": "ar-EG-ShakirNeural",
            "Female (Standard)": "ar-SA-ZariyahNeural",
            "Female (Soft)": "ar-EG-SalmaNeural",
            "Child": "ar-SA-ZariyahNeural"
        },
        "spanish": {
            "Male (Standard)": "es-ES-AlvaroNeural",
            "Male (Soft)": "es-MX-JorgeNeural",
            "Female (Standard)": "es-ES-ElviraNeural",
            "Female (Soft)": "es-MX-DaliaNeural",
            "Child": "es-MX-DaliaNeural"
        }
    }

    # Standardize keys and handle intelligent fallbacks
    target_key = target_lang_name.strip().lower()

    # 1. Get the language group or default to English group
    lang_group = smart_voice_map.get(target_key, smart_voice_map["english"])

    # 2. Selection Logic (SAFE VERSION):
    if lang in lang_group:
        # Perfect match found in the specific language dictionary
        selected_voice = lang_group[lang]
    else:
        # TONE NOT FOUND. Force a fallback to a NATIVE voice for that language.
        # This grabs the very first voice defined in that specific language's dictionary.
        selected_voice = list(lang_group.values())[0]

    # Map target_key to translation code
    lang_code_map = {"bangla": "bn", "japanese": "ja", "english": "en", "arabic": "ar", "spanish": "es"}
    target_code = lang_code_map.get(target_key, "en")

    print(f"DEBUG: Selected Voice -> {selected_voice} | Target Code -> {target_code}")

    try:
        # 1. Translate the text into the target language
        translator = GoogleTranslator(source='auto', target=target_code)
        final_text_to_speak = translator.translate(text)

        # 2. Generate audio with the selected voice
        communicate = edge_tts.Communicate(final_text_to_speak, selected_voice)

        # --- THE FIX: Ensure we wait completely for the save to finish ---
        await communicate.save(temp_mp3)

        # --- THE FIX: Check if file actually exists before returning ---
        if not os.path.exists(temp_mp3):
            print(f"❌ Error: File {temp_mp3} was not created.")
            raise HTTPException(status_code=500, detail="Audio file generation failed")

        # 3. Save Record to History
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO records (username, original_text, audio_path, created_at, type) VALUES (?, ?, ?, ?, ?)",
            (username, final_text_to_speak, temp_mp3, datetime.now().isoformat(), 'tts')
        )
        conn.commit()
        conn.close()

        # Return the verified file
        return FileResponse(temp_mp3, media_type="audio/mpeg")

    except Exception as e:
        # Detailed error printing for your terminal
        print(f"❌ Server Error: {str(e)}")
        if os.path.exists(temp_mp3):
            os.remove(temp_mp3)
        raise HTTPException(
            status_code=500,
            detail="Server error or internet connection issue with Edge-TTS"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)