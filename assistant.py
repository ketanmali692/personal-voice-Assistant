"""
Personal Voice Assistant (Windows) - Final Version
====================================================
Features:
    - Voice commands (Hindi + English + Hinglish)
    - AI fallback (Claude) for unknown questions (optional)
    - Wake word detection
    - Exit/Hello toggle (assistant pause/resume)
    - Logging to file
    - GUI (Tkinter) with status and controls
    - Weather, Wikipedia, Email, WhatsApp, Camera, Screenshots

Install:
    pip install -r requirements.txt

Environment Variables (optional, for AI + Email):
    setx ANTHROPIC_API_KEY "your-claude-api-key"
    setx ASSISTANT_EMAIL "yourname@gmail.com"
    setx ASSISTANT_EMAIL_PASSWORD "your-16-letter-gmail-app-password"

Run:
    python assistant.py
"""

import datetime
import json
import logging
import os
import queue
import random
import re
import smtplib
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from email.message import EmailMessage

import cv2
import pyautogui
import pyttsx3
import speech_recognition as sr

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import tkinter as tk
    from tkinter import scrolledtext
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


# ==================================================
# LOGGING SETUP
# ==================================================

LOG_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_FOLDER, exist_ok=True)
LOG_FILE = os.path.join(LOG_FOLDER, "assistant.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("assistant")


# ==================================================
# CONFIG LOADER
# ==================================================

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "user_name": "Ketan",
    "default_city": "Jaipur",
    "confirm_dangerous": True,
    "whatsapp_load_seconds": 12,
    "shutdown_delay_seconds": 15,
    "listen_timeout": 5,
    "phrase_limit": 8,
    "wake_word_enabled": True,
    "wake_words": ["hello assistant", "hey assistant", "wake up assistant"],
    "language": "hi-IN",
    "ai_model": "claude-3-5-haiku-20241022",
    "ai_fallback": False,
    "contacts": {
        "rahul": "rahul@example.com",
        "mummy": "mummy@example.com",
    },
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            cfg = {**DEFAULT_CONFIG, **user_config}
            log.info("Config loaded from config.json")
            return cfg
        except Exception as e:
            log.error(f"Config load failed: {e}. Using defaults.")
    else:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        log.info("config.json created with defaults.")

    return DEFAULT_CONFIG.copy()


CONFIG = load_config()

USER_NAME = CONFIG["user_name"]
CONFIRM_DANGEROUS = CONFIG["confirm_dangerous"]
WHATSAPP_LOAD_SECONDS = CONFIG["whatsapp_load_seconds"]
SHUTDOWN_DELAY_SECONDS = CONFIG["shutdown_delay_seconds"]
LISTEN_TIMEOUT = CONFIG["listen_timeout"]
PHRASE_LIMIT = CONFIG["phrase_limit"]
DEFAULT_CITY = CONFIG["default_city"]
WAKE_WORD_ENABLED = CONFIG["wake_word_enabled"]
WAKE_WORDS = [w.lower() for w in CONFIG["wake_words"]]
LANGUAGE = CONFIG.get("language", "hi-IN")
CONTACTS = CONFIG["contacts"]
AI_MODEL = CONFIG["ai_model"]
AI_FALLBACK = CONFIG["ai_fallback"]

AI_SYSTEM_PROMPT = (
    "You are a personal voice assistant. Your reply will be read aloud by a text-to-speech engine. "
    "Answer in at most three short sentences, in plain text only: no markdown, no bullet points, "
    "no asterisks, no emojis. If the user writes in Hinglish, reply in Hinglish using Roman script."
)


# ==================================================
# PATHS
# ==================================================

def get_desktop():
    home = os.path.expanduser("~")
    for path in (
        os.path.join(home, "Desktop"),
        os.path.join(home, "OneDrive", "Desktop"),
    ):
        if os.path.isdir(path):
            return path
    return os.path.join(home, "Desktop")


JAVA_FOLDER = os.path.join(get_desktop(), "Java")
DATA_FOLDER = os.path.join(os.path.expanduser("~"), "Pictures", "VoiceAssistant")
NOTES_FILE = os.path.join(os.path.expanduser("~"), "Documents", "assistant_notes.txt")


# ==================================================
# APPS DATA
# ==================================================

APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "paint": "mspaint",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "power point": "powerpnt",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "vs code": "code",
    "visual studio code": "code",
    "task manager": "taskmgr",
    "control panel": "control",
    "terminal": "wt",
    "snipping tool": "snippingtool",
    "spotify": "spotify",
}

PROCESSES = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "vs code": "Code.exe",
    "visual studio code": "Code.exe",
    "edge": "msedge.exe",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "power point": "POWERPNT.EXE",
    "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe",
    "settings": "SystemSettings.exe",
    "camera": "WindowsCamera.exe",
    "paint": "mspaint.exe",
    "task manager": "Taskmgr.exe",
    "github desktop": "GitHubDesktop.exe",
    "git bash": "mintty.exe",
    "whatsapp": "WhatsApp.exe",
    "spotify": "Spotify.exe",
}

CLOSE_ALL_LIST = [
    "chrome.exe", "msedge.exe", "notepad.exe", "WINWORD.EXE", "EXCEL.EXE",
    "POWERPNT.EXE", "CalculatorApp.exe", "mspaint.exe", "WindowsCamera.exe",
]

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "Why did the developer go broke? Because he used up all his cache.",
    "There are only 10 kinds of people: those who understand binary and those who don't.",
    "A SQL query walks into a bar, walks up to two tables and asks: can I join you?",
]


# ==================================================
# GLOBAL STATE
# ==================================================

gui_window = None
gui_log_box = None
gui_status_label = None
assistant_running = True       # Thread alive?
assistant_active = True        # Exit/Hello toggle
gui_queue = queue.Queue()


# ==================================================
# TEXT TO SPEECH (with Hindi voice support)
# ==================================================

engine = pyttsx3.init()
engine.setProperty("rate", 170)

_tts_lock = threading.Lock()
_hindi_voice_set = False


def set_hindi_voice():
    """Try to set a Hindi voice for TTS if available."""
    global _hindi_voice_set

    if _hindi_voice_set:
        return True

    try:
        voices = engine.getProperty("voices")
        for voice in voices:
            name = voice.name.lower()
            vid = voice.id.lower()
            if "hindi" in name or "hi-in" in vid or "kalpana" in name or "hemant" in name:
                engine.setProperty("voice", voice.id)
                log.info(f"Hindi voice set: {voice.name}")
                _hindi_voice_set = True
                return True
        log.warning("No Hindi voice found. Using default voice.")
    except Exception as e:
        log.error(f"Voice set error: {e}")

    return False


def speak(text):
    """Speak text and log it. Thread-safe via lock."""
    print("Assistant:", text)
    log.info(f"ASSISTANT: {text}")

    gui_queue.put(("assistant", text))

    with _tts_lock:
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            log.error(f"TTS error: {e}")


# ==================================================
# LISTEN (Hindi + English)
# ==================================================

recognizer = sr.Recognizer()
_calibrated = False


def listen(timeout=LISTEN_TIMEOUT, phrase_limit=PHRASE_LIMIT):
    """Returns recognized text in ORIGINAL case, or '' if nothing understood."""
    global _calibrated

    try:
        with sr.Microphone() as source:
            if not _calibrated:
                recognizer.adjust_for_ambient_noise(source, duration=0.8)
                _calibrated = True

            print("\nListening...")
            audio = recognizer.listen(
                source, timeout=timeout, phrase_time_limit=phrase_limit
            )

    except sr.WaitTimeoutError:
        return ""
    except OSError:
        speak("I cannot find a working microphone.")
        time.sleep(3)
        return ""

    # Try Hindi first, fallback to English
    for lang in (LANGUAGE, "en-IN"):
        try:
            text = recognizer.recognize_google(audio, language=lang).strip()
            print(f"You ({lang}):", text)
            log.info(f"USER ({lang}): {text}")
            gui_queue.put(("user", text))
            return text
        except sr.UnknownValueError:
            continue
        except sr.RequestError:
            speak("Speech recognition service is not available. Check your internet.")
            time.sleep(2)
            return ""

    print("Could not understand.")
    return ""


def words_in(text):
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def has_word(text, *words):
    tokens = words_in(text)
    return any(w in tokens for w in words)


def confirm(question):
    if not CONFIRM_DANGEROUS:
        return True

    speak(question + " Say yes or no.")

    for _ in range(2):
        answer = listen(timeout=5, phrase_limit=4)
        tokens = words_in(answer)

        if tokens & {"yes", "yeah", "yep", "confirm", "sure", "haan", "ha", "haan ji"}:
            return True
        if tokens & {"no", "nope", "cancel", "stop", "nahi", "nahin", "mat karo"}:
            return False

    speak("I did not get a clear answer, so I cancelled it.")
    return False


def write_text(text, interval=0.04):
    if pyperclip:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.write(text, interval=interval)


# ==================================================
# HINDI KEYWORD TRANSLATION
# ==================================================

HINDI_MAP = {
    "kholo": "open",
    "khol": "open",
    "kholiye": "open",
    "band karo": "close",
    "band kar": "close",
    "band": "close",
    "bajao": "play",
    "baja": "play",
    "dikhao": "show",
    "batao": "tell",
    "bata": "tell",
    "samay": "time",
    "taareekh": "date",
    "tarikh": "date",
    "mausam": "weather",
    "gaana": "song",
    "photo": "picture",
    "tasveer": "picture",
    "screenshot": "screenshot",
    "yaad dila": "remind",
    "yaad": "remind",
    "alarm": "alarm",
    "note": "note",
    "likho": "note",
    "chutkula": "joke",
    "joke": "joke",
    "madad": "help",
    "sahayata": "help",
    "alvida": "exit",
    "band ho jao": "exit",
    "namaste": "hello",
    "namaskar": "hello",
}


def translate_hindi(text):
    """Convert common Hindi keywords to English for matching."""
    result = text.lower().strip()
    for hindi, english in HINDI_MAP.items():
        if hindi in result:
            result = result.replace(hindi, english)
    return result


# ==================================================
# WAKE WORD DETECTION
# ==================================================

def wait_for_wake_word():
    """Blocks until a wake word is detected. Returns True."""
    log.info("Waiting for wake word...")

    while assistant_running:
        try:
            check_reminders()

            with sr.Microphone() as source:
                try:
                    audio = recognizer.listen(
                        source, timeout=3, phrase_time_limit=4
                    )
                except sr.WaitTimeoutError:
                    continue

            for lang in (LANGUAGE, "en-IN"):
                try:
                    text = recognizer.recognize_google(audio, language=lang).lower().strip()
                    break
                except sr.UnknownValueError:
                    text = ""
                except sr.RequestError:
                    text = ""
                    break

            if not text:
                continue

            log.debug(f"Heard (wake check): {text}")

            for wake in WAKE_WORDS:
                if wake in text:
                    log.info(f"Wake word detected: {wake}")
                    return True

            if "hello" in text or "namaste" in text:
                return True

        except Exception as e:
            log.error(f"Wake word error: {e}")
            time.sleep(1)

    return False


# ==================================================
# STANDBY MODE
# ==================================================

def standby_mode():
    speak(f"Okay {USER_NAME}, I am going on standby. Say Hello when you need me.")

    while assistant_running:
        check_reminders()
        wake = listen().lower().strip()

        if wake in ("hello", "hi", "wake up") or "hello assistant" in wake or "namaste" in wake:
            speak(f"Hello {USER_NAME}, I am back. How can I help you?")
            return


# ==================================================
# APPS
# ==================================================

def open_app(app_name):
    app_name = app_name.strip().lower()
    target = APPS.get(app_name, app_name)

    speak("Opening " + app_name)

    try:
        result = subprocess.run(
            ["cmd", "/c", "start", "", target],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            speak("Sorry, I could not find " + app_name)
        else:
            time.sleep(1.5)

    except Exception as e:
        log.error(f"Open error: {e}")
        speak("Sorry, I could not open " + app_name)


def close_explorer_windows():
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(New-Object -ComObject Shell.Application).Windows() "
            "| ForEach-Object { $_.Quit() }",
        ],
        capture_output=True,
    )


def close_app(app_name):
    name = app_name.lower().strip()

    if name in ("file explorer", "explorer", "files"):
        speak("Closing File Explorer windows.")
        close_explorer_windows()
        return

    process = PROCESSES.get(name)

    if process:
        speak("Closing " + name)
        subprocess.run(["taskkill", "/F", "/IM", process], capture_output=True)
        return

    if name in ("python", "cmd", "command prompt", "terminal"):
        speak("I will not close that, because I might be running inside it.")
        return

    speak("I do not know how to close " + name)


def close_all_apps():
    if not confirm("This will close browsers and common apps. Unsaved work may be lost. Continue?"):
        return

    speak("Closing common applications.")

    for process in CLOSE_ALL_LIST:
        subprocess.run(["taskkill", "/F", "/IM", process], capture_output=True)

    close_explorer_windows()
    speak("Done.")


# ==================================================
# CAMERA / SCREENSHOT
# ==================================================

def open_camera():
    speak("Opening camera.")
    os.system("start microsoft.windows.camera:")


def take_picture():
    speak("Taking the picture. Make sure the Camera app is closed.")

    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not camera.isOpened():
        speak("I could not access the camera.")
        return

    try:
        frame = None
        ok = False
        for _ in range(20):
            ok, frame = camera.read()
            time.sleep(0.05)

        if ok and frame is not None:
            os.makedirs(DATA_FOLDER, exist_ok=True)
            filename = datetime.datetime.now().strftime("photo_%Y%m%d_%H%M%S.jpg")
            path = os.path.join(DATA_FOLDER, filename)
            cv2.imwrite(path, frame)

            speak("Picture taken successfully.")
            log.info(f"Photo saved: {path}")
        else:
            speak("I could not take the picture.")

    finally:
        camera.release()


def take_screenshot():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    filename = datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = os.path.join(DATA_FOLDER, filename)

    pyautogui.screenshot(path)

    speak("Screenshot saved.")
    log.info(f"Screenshot saved: {path}")


# ==================================================
# WHATSAPP
# ==================================================

def whatsapp_voice_message(raw_command):
    match = re.search(
        r"search\s+(.+?)\s+and\s+send\s+(?:the\s+)?message\s+(.+)",
        raw_command,
        re.IGNORECASE,
    )

    if not match:
        speak("Please say: search, the contact name, and send the message, then your message.")
        return

    contact_name = match.group(1).strip()
    message = match.group(2).strip()

    if not contact_name or not message:
        speak("I need both a contact name and a message.")
        return

    if not confirm(f"Send the message {message} to {contact_name}?"):
        speak("Okay, message cancelled.")
        return

    try:
        speak("Opening WhatsApp.")
        webbrowser.open("https://web.whatsapp.com")
        time.sleep(WHATSAPP_LOAD_SECONDS)

        speak("Searching for " + contact_name)
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(1)

        write_text(contact_name)
        time.sleep(2)
        pyautogui.press("enter")
        time.sleep(2)

        speak("Typing your message.")
        write_text(message)
        time.sleep(1)
        pyautogui.press("enter")

        speak("Message sent to " + contact_name)

    except Exception as e:
        log.error(f"WhatsApp error: {e}")
        speak("Sorry, I could not complete the WhatsApp command.")


def open_whatsapp():
    speak("Opening WhatsApp.")
    webbrowser.open("https://web.whatsapp.com")


# ==================================================
# JAVA
# ==================================================

def open_java_folder():
    os.makedirs(JAVA_FOLDER, exist_ok=True)
    speak("Opening Java folder.")
    os.startfile(JAVA_FOLDER)


def to_class_name(spoken):
    spoken = re.sub(r"^(?:called|named|name)\s+", "", spoken.strip(), flags=re.IGNORECASE)
    words = re.findall(r"[A-Za-z0-9]+", spoken)

    if len(words) > 1 and words[-1].lower() == "java":
        words = words[:-1]

    if not words:
        return ""

    name = "".join(w.capitalize() for w in words)

    if name[0].isdigit():
        name = "Program" + name

    return name


def create_java_file(spoken_name):
    class_name = to_class_name(spoken_name)

    if not class_name:
        speak("Please tell me the file name.")
        return

    os.makedirs(JAVA_FOLDER, exist_ok=True)
    path = os.path.join(JAVA_FOLDER, class_name + ".java")

    if os.path.exists(path):
        speak("That Java file already exists.")
        os.startfile(path)
        return

    code = f"""public class {class_name} {{

    public static void main(String[] args) {{

        System.out.println("Hello {USER_NAME}");

    }}

}}
"""

    with open(path, "w", encoding="utf-8") as file:
        file.write(code)

    speak(class_name + ".java has been created.")
    os.startfile(path)


# ==================================================
# TYPE / SEARCH
# ==================================================

def type_text(text):
    speak("Click where you want to type. I will start in three seconds.")
    time.sleep(3)
    write_text(text)


def google_search(query):
    if not query:
        return

    speak("Searching Google.")
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))


def youtube_search(query):
    if not query:
        return

    speak("Searching YouTube for " + query)
    webbrowser.open(
        "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    )


# ==================================================
# SYSTEM
# ==================================================

def shutdown_laptop():
    if not confirm("Do you really want to shut down the laptop?"):
        speak("Okay, shutdown cancelled.")
        return

    speak(f"Shutting down in {SHUTDOWN_DELAY_SECONDS} seconds. Say cancel shutdown to stop.")
    os.system(f"shutdown /s /t {SHUTDOWN_DELAY_SECONDS}")


def restart_laptop():
    if not confirm("Do you really want to restart the laptop?"):
        speak("Okay, restart cancelled.")
        return

    speak(f"Restarting in {SHUTDOWN_DELAY_SECONDS} seconds. Say cancel shutdown to stop.")
    os.system(f"shutdown /r /t {SHUTDOWN_DELAY_SECONDS}")


def cancel_shutdown():
    os.system("shutdown /a")
    speak("Shutdown cancelled.")


def sleep_laptop():
    speak("Putting the laptop to sleep.")
    time.sleep(2)
    subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])


def change_volume(direction):
    key = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}[direction]
    presses = 1 if direction == "mute" else 5

    for _ in range(presses):
        pyautogui.press(key)

    speak("Volume " + direction)


# ==================================================
# NOTES
# ==================================================

def save_note(text):
    if not text:
        speak("What should I note?")
        return

    os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
    stamp = datetime.datetime.now().strftime("%d-%m-%Y %I:%M %p")

    with open(NOTES_FILE, "a", encoding="utf-8") as file:
        file.write(f"[{stamp}] {text}\n")

    speak("Note saved.")


def read_notes():
    if not os.path.exists(NOTES_FILE):
        speak("You have no notes yet.")
        return

    with open(NOTES_FILE, "r", encoding="utf-8") as file:
        lines = [line.strip() for line in file if line.strip()]

    if not lines:
        speak("You have no notes yet.")
        return

    speak("Your last notes are:")
    for line in lines[-3:]:
        speak(line)


def tell_help():
    speak(
        "I can open and close apps, search Google and YouTube, "
        "send WhatsApp messages, take pictures and screenshots, "
        "create Java files, type for you, control volume, save notes, "
        "tell time, date and weather, look things up on Wikipedia, "
        "set reminders and alarms, send emails, answer questions with AI, "
        "and shut down, restart or sleep the laptop."
    )


# ==================================================
# INTERNET HELPERS
# ==================================================

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "a thunderstorm", 96: "a thunderstorm with hail", 99: "a thunderstorm with hail",
}


def http_json(url, timeout=8):
    request = urllib.request.Request(
        url, headers={"User-Agent": "PersonalVoiceAssistant/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_weather(city=""):
    city = city.strip() or DEFAULT_CITY

    try:
        geo = http_json(
            "https://geocoding-api.open-meteo.com/v1/search?count=1&name="
            + urllib.parse.quote(city)
        )

        results = geo.get("results")

        if not results:
            speak("I could not find a city called " + city)
            return

        place = results[0]

        weather = http_json(
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={place['latitude']}&longitude={place['longitude']}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
            "weather_code,wind_speed_10m&timezone=auto"
        )["current"]

        description = WEATHER_CODES.get(weather["weather_code"], "unknown conditions")

        speak(
            f"In {place['name']} it is {round(weather['temperature_2m'])} degrees Celsius, "
            f"feels like {round(weather['apparent_temperature'])}, with {description}. "
            f"Humidity is {round(weather['relative_humidity_2m'])} percent and wind is "
            f"{round(weather['wind_speed_10m'])} kilometres per hour."
        )

    except Exception as e:
        log.error(f"Weather error: {e}")
        speak("I could not get the weather right now. Please check your internet.")


def wikipedia_answer(topic):
    topic = topic.strip()

    if not topic:
        speak("What should I look up?")
        return

    speak("Looking up " + topic)

    try:
        search = http_json(
            "https://en.wikipedia.org/w/api.php?action=query&list=search"
            "&format=json&srlimit=1&srsearch=" + urllib.parse.quote(topic)
        )

        hits = search.get("query", {}).get("search", [])

        if not hits:
            speak("I could not find anything about " + topic)
            return

        title = hits[0]["title"]

        page = http_json(
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(title.replace(" ", "_"))
        )

        extract = page.get("extract", "").strip()

        if not extract:
            speak("I could not find a summary for " + title)
            return

        sentences = re.split(r"(?<=[.!?])\s+", extract)
        speak(" ".join(sentences[:2]))

    except Exception as e:
        log.error(f"Wikipedia error: {e}")
        speak("I could not reach Wikipedia right now.")


# ==================================================
# REMINDERS AND ALARMS
# ==================================================

reminder_queue = queue.Queue()
pending_reminders = {}
_reminder_counter = 0

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "sixty": 60,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5, "chhe": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "pandrah": 15,
}

UNIT_SECONDS = {
    "second": 1, "seconds": 1, "sec": 1,
    "minute": 60, "minutes": 60, "min": 60,
    "hour": 3600, "hours": 3600,
    "सेकंड": 1, "मिनट": 60, "घंटा": 3600,
    "second": 1, "minute": 60, "hour": 3600,
}


def _fire_reminder(reminder_id, message):
    pending_reminders.pop(reminder_id, None)

    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1000, 400)
            time.sleep(0.2)
    except Exception:
        pass

    reminder_queue.put(message)


def schedule_reminder(seconds, message):
    global _reminder_counter

    _reminder_counter += 1
    reminder_id = _reminder_counter

    timer = threading.Timer(seconds, _fire_reminder, args=(reminder_id, message))
    timer.daemon = True
    timer.start()

    due = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    pending_reminders[reminder_id] = (due, message, timer)


def check_reminders():
    while not reminder_queue.empty():
        speak(reminder_queue.get())


def set_reminder(raw_command):
    match = re.search(
        r"remind me in (\w+)\s+(second|minute|hour|sec|min)s?\s*(?:to|about|that)?\s*(.*)",
        raw_command,
        re.IGNORECASE,
    )

    if not match:
        speak("Please say for example: remind me in 10 minutes to drink water.")
        return

    amount_text = match.group(1).lower()
    unit = match.group(2).lower()
    what = match.group(3).strip() or "your reminder"

    amount = int(amount_text) if amount_text.isdigit() else NUMBER_WORDS.get(amount_text)

    if not amount:
        speak("I could not understand the time. Please say the number in digits.")
        return

    schedule_reminder(amount * UNIT_SECONDS[unit], "Reminder: " + what)

    plural = "" if amount == 1 else "s"
    speak(f"Okay, I will remind you in {amount} {unit}{plural} to {what}.")


def set_alarm(command):
    text = command.replace(".", "")

    match = re.search(
        r"alarm\s+(?:for|at)\s+(\d{1,2})(?:[:\s](\d{2}))?\s*(am|pm)?",
        text,
    )

    if not match:
        speak("Please say for example: set alarm for 7:30 am.")
        return

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3)

    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    elif not suffix:
        if hour <= 7:
            hour += 12

    if hour > 23 or minute > 59:
        speak("That is not a valid time.")
        return

    now = datetime.datetime.now()
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if due <= now:
        due += datetime.timedelta(days=1)

    label = due.strftime("%I:%M %p")

    schedule_reminder((due - now).total_seconds(), f"Alarm! It is {label}.")
    speak("Alarm set for " + label)


def list_reminders():
    items = sorted(pending_reminders.values(), key=lambda item: item[0])

    if not items:
        speak("You have no reminders or alarms.")
        return

    speak(f"You have {len(items)} pending.")

    for due, message, _ in items:
        speak(f"{due.strftime('%I:%M %p')}: {message}")


def cancel_reminders():
    for _, _, timer in list(pending_reminders.values()):
        timer.cancel()

    pending_reminders.clear()
    speak("All reminders and alarms cancelled.")


# ==================================================
# EMAIL
# ==================================================

def send_email():
    address = os.environ.get("ASSISTANT_EMAIL")
    password = os.environ.get("ASSISTANT_EMAIL_PASSWORD")

    if not address or not password:
        speak("Email is not set up. Please set the email environment variables first.")
        return

    speak("Who should I send it to?")
    spoken_name = listen(timeout=6, phrase_limit=5).lower().strip()

    recipient = None
    recipient_name = None

    for name, email_address in CONTACTS.items():
        if name in spoken_name:
            recipient = email_address
            recipient_name = name
            break

    if not recipient:
        speak("I do not have that contact.")
        return

    speak("What is the subject?")
    subject = listen(timeout=6, phrase_limit=10)

    if not subject:
        speak("I did not hear a subject. Email cancelled.")
        return

    speak("What should I write?")
    body = listen(timeout=8, phrase_limit=30)

    if not body:
        speak("I did not hear the message. Email cancelled.")
        return

    if not confirm(f"Send an email to {recipient_name} with subject {subject}?"):
        speak("Okay, email cancelled.")
        return

    try:
        message = EmailMessage()
        message["From"] = address
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(address, password)
            server.send_message(message)

        speak("Email sent to " + recipient_name)

    except Exception as e:
        log.error(f"Email error: {e}")
        speak("Sorry, I could not send the email. Check your app password and internet.")


# ==================================================
# AI (CLAUDE)
# ==================================================

ai_client = None
ai_history = []


def get_ai_client():
    global ai_client

    if ai_client is None and anthropic and os.environ.get("ANTHROPIC_API_KEY"):
        ai_client = anthropic.Anthropic()

    return ai_client


def ask_ai(question):
    client = get_ai_client()

    if client is None:
        speak("AI is not set up. Install the anthropic package and set the API key.")
        return

    ai_history.append({"role": "user", "content": question})

    try:
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=300,
            system=AI_SYSTEM_PROMPT,
            messages=ai_history,
        )

        answer = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        if not answer:
            raise ValueError("Empty answer")

    except Exception as e:
        log.error(f"AI error: {e}")
        ai_history.pop()
        speak("I could not reach the AI service right now.")
        return

    ai_history.append({"role": "assistant", "content": answer})

    while len(ai_history) > 12:
        del ai_history[0:2]

    speak(answer)


# ==================================================
# COMMAND HANDLER
# ==================================================

def handle(raw):
    """Returns:
        False  -> stop the assistant thread completely (real exit)
        True   -> keep running
    """

    command = raw.lower().strip()

    # ---------- REAL EXIT (thread stop) ----------
    if command in ("quit assistant", "stop assistant", "shutdown assistant") or "quit assistant" in command:
        speak(f"Goodbye {USER_NAME}! Shutting down completely.")
        return False

    # ---------- EXIT (pause, but keep thread alive) ----------
    if (
        command in ("exit", "bye", "goodbye", "alvida", "band ho jao", "so jao")
        or "exit" in command
        or "alvida" in command
    ):
        speak(f"Theek hai {USER_NAME}, main ruk raha hoon. Jab zaroorat ho 'Hello' bolna.")
        return "exit"

    # ---------- HELLO (resume) ----------
    if (
        command in ("hello", "hi", "namaste", "namaskar", "wake up", "utho")
        or "hello" in command
        or "namaste" in command
    ):
        speak(f"Hello {USER_NAME}! Main wapas aa gaya. Batao kya karna hai?")
        return "hello"

    # ---------- STANDBY (deep sleep mode) ----------
    if (
        command in ("standby", "go to standby", "go to sleep", "sleep assistant")
        or "stand by" in command
    ):
        standby_mode()
        return True

    # ---------- CANCEL SHUTDOWN ----------
    if "cancel shutdown" in command or "cancel restart" in command:
        cancel_shutdown()
        return True

    # ---------- ASK AI ----------
    if re.match(r"^(?:ask ai|ask claude|ask)\s+\S", command):
        question = re.sub(
            r"^(?:ask ai|ask claude|ask)\s+", "", raw, flags=re.IGNORECASE
        ).strip()
        ask_ai(question)

    elif "forget conversation" in command or "clear ai memory" in command:
        ai_history.clear()
        speak("Okay, I cleared our AI conversation.")

    # ---------- REMINDERS / ALARMS ----------
    elif command.startswith("remind me") or "remind" in command or "yaad" in command:
        set_reminder(raw)

    elif "alarm" in command and has_word(command, "set"):
        set_alarm(command)

    elif "list reminders" in command or "list alarms" in command:
        list_reminders()

    elif "cancel reminders" in command or "cancel alarms" in command:
        cancel_reminders()

    # ---------- EMAIL ----------
    elif command.startswith("send email") or command.startswith("send an email") or command == "send mail":
        send_email()

    # ---------- WHATSAPP ----------
    elif "open whatsapp" in command and "search " in command and "message " in command:
        whatsapp_voice_message(raw)

    # ---------- HELP ----------
    elif "what can you do" in command or command == "help" or "madad" in command:
        tell_help()

    # ---------- YOUTUBE ----------
    elif command.startswith("search youtube "):
        youtube_search(raw[len("search youtube "):].strip())

    elif command.startswith("play ") and command.endswith(" on youtube"):
        youtube_search(raw[len("play "):-len(" on youtube")].strip())

    elif "open youtube" in command:
        speak("Opening YouTube.")
        webbrowser.open("https://www.youtube.com")

    # ---------- GOOGLE ----------
    elif command.startswith("search google "):
        google_search(raw[len("search google "):].strip())

    elif "open google" in command:
        speak("Opening Google.")
        webbrowser.open("https://www.google.com")

    # ---------- CAMERA / SCREENSHOT ----------
    elif "open camera" in command:
        open_camera()

    elif "take the picture" in command or "take a picture" in command or "take photo" in command or "photo" in command:
        take_picture()

    elif "screenshot" in command:
        take_screenshot()

    # ---------- JAVA ----------
    elif "open java folder" in command or "open folder java" in command:
        open_java_folder()

    elif command.startswith("create a file") or command.startswith("create file"):
        spoken = re.sub(r"^create (?:a )?file", "", command).strip()
        create_java_file(spoken)

    # ---------- TYPE ----------
    elif command.startswith("type "):
        type_text(raw[len("type "):].strip())

    # ---------- CLOSE ----------
    elif "close all apps" in command or "all apps close" in command or "all close app" in command:
        close_all_apps()

    elif command.startswith("close "):
        close_app(command[len("close "):].strip())

    # ---------- OPEN ----------
    elif "open settings" in command:
        speak("Opening Settings.")
        os.system("start ms-settings:")

    elif "open file explorer" in command or "open files" in command:
        speak("Opening File Explorer.")
        subprocess.Popen("explorer.exe")

    elif "open cmd" in command or "open command prompt" in command:
        speak("Opening Command Prompt.")
        subprocess.Popen("cmd.exe", creationflags=subprocess.CREATE_NEW_CONSOLE)

    elif "open whatsapp" in command:
        open_whatsapp()

    elif command.startswith("open "):
        app = command[len("open "):].strip()
        if app:
            open_app(app)

    # ---------- POWER ----------
    elif command in ("laptop shutdown", "shutdown laptop", "shut down laptop"):
        shutdown_laptop()

    elif command in ("restart", "restart laptop", "laptop restart"):
        restart_laptop()

    elif command in ("laptop sleep", "sleep laptop"):
        sleep_laptop()

    # ---------- VOLUME ----------
    elif "volume up" in command or "increase volume" in command:
        change_volume("up")

    elif "volume down" in command or "decrease volume" in command:
        change_volume("down")

    elif command in ("mute", "volume mute", "mute volume"):
        change_volume("mute")

    # ---------- NOTES ----------
    elif command.startswith("take a note ") or command.startswith("note ") or command.startswith("likho "):
        text = re.sub(r"^(?:take a note|note|likho)\s+", "", raw, flags=re.IGNORECASE).strip()
        save_note(text)

    elif "read my notes" in command or "read notes" in command:
        read_notes()

    # ---------- WEATHER ----------
    elif has_word(command, "weather", "temperature") or "mausam" in command:
        match = re.search(r"(?:in|of|for)\s+([a-z ]+)$", command)
        get_weather(match.group(1) if match else "")

    # ---------- WIKIPEDIA ----------
    elif command.startswith("wikipedia "):
        wikipedia_answer(raw[len("wikipedia "):])

    elif command.startswith("tell me about "):
        wikipedia_answer(raw[len("tell me about "):])

    elif command.startswith("who is "):
        wikipedia_answer(raw[len("who is "):])

    # ---------- JOKE ----------
    elif "joke" in command or "chutkula" in command:
        speak(random.choice(JOKES))

    # ---------- TIME / DATE ----------
    elif has_word(command, "time") and len(command.split()) <= 6:
        speak("The time is " + datetime.datetime.now().strftime("%I:%M %p"))

    elif has_word(command, "date") and len(command.split()) <= 6:
        speak("Today's date is " + datetime.datetime.now().strftime("%d %B %Y"))

    # ---------- UNKNOWN -> AI ----------
    else:
        if AI_FALLBACK and get_ai_client():
            ask_ai(raw)
        else:
            speak(f"Sorry {USER_NAME}, I don't know that command yet.")

    return True


# ==================================================
# GUI (TKINTER) - Badi window
# ==================================================

def build_gui():
    """Creates the GUI window. Returns the root window."""
    global gui_window, gui_log_box, gui_status_label

    gui_window = tk.Tk()
    gui_window.title(f"Voice Assistant - {USER_NAME}")
    gui_window.geometry("900x750")
    gui_window.minsize(700, 550)
    gui_window.configure(bg="#1e1e2e")

    header = tk.Label(
        gui_window,
        text="Personal Voice Assistant",
        font=("Segoe UI", 20, "bold"),
        bg="#1e1e2e",
        fg="#89b4fa",
        pady=14,
    )
    header.pack()

    gui_status_label = tk.Label(
        gui_window,
        text="Status: Starting...",
        font=("Segoe UI", 12),
        bg="#1e1e2e",
        fg="#a6e3a1",
        pady=6,
    )
    gui_status_label.pack()

    gui_log_box = scrolledtext.ScrolledText(
        gui_window,
        wrap=tk.WORD,
        width=80,
        height=28,
        font=("Consolas", 11),
        bg="#181825",
        fg="#cdd6f4",
        insertbackground="#cdd6f4",
        borderwidth=0,
        padx=12,
        pady=12,
    )
    gui_log_box.pack(padx=15, pady=12, fill=tk.BOTH, expand=True)
    gui_log_box.tag_config("user", foreground="#89dceb")
    gui_log_box.tag_config("assistant", foreground="#f9e2af")
    gui_log_box.tag_config("system", foreground="#a6adc8")
    gui_log_box.config(state=tk.DISABLED)

    btn_frame = tk.Frame(gui_window, bg="#1e1e2e")
    btn_frame.pack(pady=10)

    def make_btn(text, color, command):
        return tk.Button(
            btn_frame,
            text=text,
            command=command,
            font=("Segoe UI", 12, "bold"),
            bg=color,
            fg="#1e1e2e",
            activebackground=color,
            relief=tk.FLAT,
            padx=22,
            pady=10,
            cursor="hand2",
        )

    make_btn("Start", "#a6e3a1", start_assistant).grid(row=0, column=0, padx=6)
    make_btn("Standby", "#f9e2af", go_standby).grid(row=0, column=1, padx=6)
    make_btn("Stop", "#f38ba8", stop_assistant).grid(row=0, column=2, padx=6)
    make_btn("Clear", "#89b4fa", clear_gui_log).grid(row=0, column=3, padx=6)

    footer = tk.Label(
        gui_window,
        text="Wake word: 'Hey Assistant'   |   Say 'Hello' to wake, 'Exit' to pause",
        font=("Segoe UI", 10),
        bg="#1e1e2e",
        fg="#6c7086",
        pady=10,
    )
    footer.pack()

    gui_window.protocol("WM_DELETE_WINDOW", on_gui_close)

    return gui_window


def gui_log(speaker, text):
    """Appends a message to the GUI conversation box."""
    if gui_log_box is None:
        return

    gui_log_box.config(state=tk.NORMAL)
    prefix = {"user": "You: ", "assistant": "Assistant: ", "system": "- "}[speaker]
    gui_log_box.insert(tk.END, prefix + text + "\n", speaker)
    gui_log_box.see(tk.END)
    gui_log_box.config(state=tk.DISABLED)


def set_gui_status(text, color="#a6e3a1"):
    if gui_status_label is not None:
        gui_status_label.config(text=f"Status: {text}", fg=color)


def clear_gui_log():
    if gui_log_box is not None:
        gui_log_box.config(state=tk.NORMAL)
        gui_log_box.delete("1.0", tk.END)
        gui_log_box.config(state=tk.DISABLED)


# ==================================================
# ASSISTANT THREAD
# ==================================================

assistant_thread = None
standby_event = threading.Event()


def assistant_loop():
    """Main assistant loop. Runs in a background thread."""
    global assistant_running, assistant_active

    set_hindi_voice()

    speak(f"Hello {USER_NAME}, I am your personal voice assistant. How can I help you?")
    set_gui_status("Listening...", "#a6e3a1")

    while assistant_running:
        try:
            check_reminders()

            # If paused (user said "exit"), wait quietly for "hello"
            if not assistant_active:
                set_gui_status("Paused - say 'Hello' to wake", "#f9e2af")
                time.sleep(1)
                continue

            if standby_event.is_set():
                set_gui_status("Standby - waiting for wake word...", "#f9e2af")
                if wait_for_wake_word():
                    standby_event.clear()
                    speak(f"Hello {USER_NAME}, I am back. How can I help you?")
                    set_gui_status("Listening...", "#a6e3a1")
                continue

            raw = listen()

            if not raw:
                continue

            set_gui_status("Processing...", "#89b4fa")

            result = handle(raw)

            # Handle special return values
            if result is False:
                assistant_running = False
                break
            elif result == "exit":
                # Pause the assistant, but keep thread alive
                assistant_active = False
                set_gui_status("Paused - say 'Hello' to wake", "#f9e2af")
                gui_log("system", "Assistant paused. Say 'Hello' to resume.")
                continue
            elif result == "hello":
                # Resume the assistant
                assistant_active = True
                set_gui_status("Listening...", "#a6e3a1")
                gui_log("system", "Assistant resumed.")
                continue

            set_gui_status("Listening...", "#a6e3a1")

        except KeyboardInterrupt:
            log.info("Stopped by keyboard.")
            break

        except Exception as e:
            log.error(f"Loop error: {e}")
            speak("Sorry, something went wrong with that command.")

    set_gui_status("Stopped", "#f38ba8")


def start_assistant():
    """Starts the assistant thread if not already running."""
    global assistant_thread, assistant_running, assistant_active

    if assistant_thread and assistant_thread.is_alive():
        gui_log("system", "Assistant is already running.")
        return

    assistant_running = True
    assistant_active = True
    standby_event.clear()
    assistant_thread = threading.Thread(target=assistant_loop, daemon=True)
    assistant_thread.start()
    gui_log("system", "Assistant started.")


def go_standby():
    """Puts the assistant into standby mode."""
    standby_event.set()
    gui_log("system", "Standby mode. Say 'Hey Assistant' to wake up.")
    set_gui_status("Standby", "#f9e2af")


def stop_assistant():
    """Stops the assistant thread."""
    global assistant_running, assistant_active
    assistant_running = False
    assistant_active = False
    standby_event.clear()
    gui_log("system", "Stopping assistant...")
    set_gui_status("Stopped", "#f38ba8")


def on_gui_close():
    """Called when the user closes the GUI window."""
    global assistant_running
    assistant_running = False
    if gui_window:
        gui_window.destroy()


def process_gui_queue():
    """Periodically moves messages from queue to GUI."""
    while not gui_queue.empty():
        speaker, text = gui_queue.get()
        gui_log(speaker, text)

    if gui_window:
        gui_window.after(200, process_gui_queue)


# ==================================================
# MAIN
# ==================================================

def main():
    if GUI_AVAILABLE:
        log.info("Starting with GUI...")
        build_gui()
        gui_window.after(200, process_gui_queue)
        start_assistant()
        gui_window.mainloop()
    else:
        log.info("GUI not available. Running in console mode.")
        set_hindi_voice()
        try:
            assistant_loop()
        except KeyboardInterrupt:
            log.info("Stopped by keyboard.")


if __name__ == "__main__":
    main()