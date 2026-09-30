"""
Personal Voice Assistant (Windows) - Final Working Version
============================================================
All commands are flexible. Whatever you say, it will work.
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
# LOGGING
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
# CONFIG
# ==================================================

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "user_name": "Ketan",
    "default_city": "Jaipur",
    "confirm_dangerous": True,
    "whatsapp_load_seconds": 12,
    "shutdown_delay_seconds": 15,
    "listen_timeout": 7,
    "phrase_limit": 10,
    "wake_word_enabled": True,
    "wake_words": ["hello assistant", "hey assistant", "wake up assistant"],
    "ai_model": "claude-3-5-haiku-20241022",
    "ai_fallback": False,
    "contacts": {
        "rahul": "rahul@example.com",
    },
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            return {**DEFAULT_CONFIG, **user_config}
        except Exception as e:
            log.error(f"Config load failed: {e}")
    else:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
    return DEFAULT_CONFIG.copy()


CONFIG = load_config()

USER_NAME = CONFIG["user_name"]
CONFIRM_DANGEROUS = CONFIG["confirm_dangerous"]
WHATSAPP_LOAD_SECONDS = CONFIG["whatsapp_load_seconds"]
SHUTDOWN_DELAY_SECONDS = CONFIG["shutdown_delay_seconds"]
LISTEN_TIMEOUT = CONFIG["listen_timeout"]
PHRASE_LIMIT = CONFIG["phrase_limit"]
DEFAULT_CITY = CONFIG["default_city"]
WAKE_WORDS = [w.lower() for w in CONFIG["wake_words"]]
CONTACTS = CONFIG["contacts"]
AI_MODEL = CONFIG["ai_model"]
AI_FALLBACK = CONFIG["ai_fallback"]

AI_SYSTEM_PROMPT = (
    "You are a personal voice assistant. Answer in at most three short sentences, "
    "plain text only, no markdown, no emojis."
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
# APPS DATABASE
# ==================================================

APPS = {
    "notepad": "notepad",
    "note pad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "paint": "mspaint",
    "ms paint": "mspaint",
    "word": "winword",
    "ms word": "winword",
    "excel": "excel",
    "ms excel": "excel",
    "powerpoint": "powerpnt",
    "power point": "powerpnt",
    "ppt": "powerpnt",
    "chrome": "chrome",
    "google chrome": "chrome",
    "browser": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "code": "code",
    "task manager": "taskmgr",
    "taskmgr": "taskmgr",
    "control panel": "control",
    "terminal": "wt",
    "windows terminal": "wt",
    "snipping tool": "snippingtool",
    "spotify": "spotify",
    "camera": "microsoft.windows.camera:",
    "settings": "ms-settings:",
    "file explorer": "explorer",
    "explorer": "explorer",
    "files": "explorer",
    "cmd": "cmd",
    "command prompt": "cmd",
}

PROCESSES = {
    "chrome": "chrome.exe",
    "browser": "chrome.exe",
    "vs code": "Code.exe",
    "vscode": "Code.exe",
    "code": "Code.exe",
    "edge": "msedge.exe",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "ppt": "POWERPNT.EXE",
    "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe",
    "paint": "mspaint.exe",
    "task manager": "Taskmgr.exe",
    "spotify": "Spotify.exe",
    "camera": "WindowsCamera.exe",
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
assistant_running = True
assistant_active = True
gui_queue = queue.Queue()


# ==================================================
# TTS
# ==================================================

engine = pyttsx3.init()
engine.setProperty("rate", 170)
_tts_lock = threading.Lock()


def speak(text):
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
# LISTEN
# ==================================================

recognizer = sr.Recognizer()
_calibrated = False


def listen(timeout=LISTEN_TIMEOUT, phrase_limit=PHRASE_LIMIT):
    global _calibrated

    try:
        with sr.Microphone() as source:
            if not _calibrated:
                recognizer.adjust_for_ambient_noise(source, duration=0.8)
                _calibrated = True

            print("\nListening...")
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)

    except sr.WaitTimeoutError:
        return ""
    except OSError:
        speak("I cannot find a working microphone.")
        time.sleep(3)
        return ""

    try:
        text = recognizer.recognize_google(audio, language="en-IN").strip()
        print("You:", text)
        log.info(f"USER: {text}")
        gui_queue.put(("user", text))
        return text
    except sr.UnknownValueError:
        print("Could not understand.")
        return ""
    except sr.RequestError:
        speak("Speech recognition not available. Check internet.")
        time.sleep(2)
        return ""


def words_in(text):
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def confirm(question):
    if not CONFIRM_DANGEROUS:
        return True
    speak(question + " Say yes or no.")
    for _ in range(2):
        answer = listen(timeout=5, phrase_limit=4)
        tokens = words_in(answer)
        if tokens & {"yes", "yeah", "yep", "confirm", "sure", "ok", "okay"}:
            return True
        if tokens & {"no", "nope", "cancel", "stop"}:
            return False
    speak("Cancelled.")
    return False


def write_text(text, interval=0.04):
    if pyperclip:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.write(text, interval=interval)


def check_reminders():
    while not reminder_queue.empty():
        speak(reminder_queue.get())


# ==================================================
# WAKE WORD
# ==================================================

def wait_for_wake_word():
    log.info("Waiting for wake word...")
    while assistant_running:
        try:
            check_reminders()
            with sr.Microphone() as source:
                try:
                    audio = recognizer.listen(source, timeout=3, phrase_time_limit=4)
                except sr.WaitTimeoutError:
                    continue
            text = recognizer.recognize_google(audio, language="en-IN").lower().strip()
            for wake in WAKE_WORDS:
                if wake in text:
                    return True
            if "hello" in text or "hey assistant" in text:
                return True
        except (sr.UnknownValueError, sr.RequestError):
            continue
        except Exception as e:
            log.error(f"Wake word error: {e}")
            time.sleep(1)
    return False


# ==================================================
# STANDBY
# ==================================================

def standby_mode():
    speak(f"Okay {USER_NAME}, standby mode. Say Hello when you need me.")
    while assistant_running:
        check_reminders()
        wake = listen().lower().strip()
        if wake in ("hello", "hi", "wake up") or "hello assistant" in wake:
            speak(f"Hello {USER_NAME}, I am back.")
            return


# ==================================================
# APPS - FLEXIBLE OPEN / CLOSE
# ==================================================

def find_app(query):
    """Find best matching app from query."""
    query = query.lower().strip()

    for w in ["open", "launch", "start", "run", "the", "app", "application", "please"]:
        query = re.sub(rf"\b{w}\b", "", query, flags=re.IGNORECASE)
    query = query.strip()

    if not query:
        return None

    if query in APPS:
        return query, APPS[query]

    for key, value in APPS.items():
        if key in query or query in key:
            return key, value

    query_words = set(query.split())
    for key, value in APPS.items():
        key_words = set(key.split())
        if key_words & query_words:
            return key, value

    return None


def open_app(app_query):
    result = find_app(app_query)

    if not result:
        speak("I don't know how to open " + app_query)
        return

    app_name, target = result
    speak("Opening " + app_name)

    try:
        if target.startswith("http"):
            webbrowser.open(target)
        elif target.endswith(":"):
            os.system(f"start {target}")
        else:
            subprocess.run(["cmd", "/c", "start", "", target], capture_output=True)
        time.sleep(1)
    except Exception as e:
        log.error(f"Open error: {e}")
        speak("Could not open " + app_name)


def close_app(app_query):
    query = app_query.lower().strip()
    for w in ["close", "the", "app", "application", "please"]:
        query = re.sub(rf"\b{w}\b", "", query, flags=re.IGNORECASE)
    query = query.strip()

    if query in ("file explorer", "explorer", "files"):
        speak("Closing File Explorer.")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(New-Object -ComObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }"],
            capture_output=True,
        )
        return

    process = PROCESSES.get(query)
    if not process:
        for key, value in PROCESSES.items():
            if key in query or query in key:
                process = value
                break

    if process:
        speak("Closing " + query)
        subprocess.run(["taskkill", "/F", "/IM", process], capture_output=True)
    else:
        speak("I don't know how to close " + query)


def close_all_apps():
    if not confirm("Close all common apps? Unsaved work may be lost."):
        return
    speak("Closing all apps.")
    for process in CLOSE_ALL_LIST:
        subprocess.run(["taskkill", "/F", "/IM", process], capture_output=True)
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(New-Object -ComObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }"],
        capture_output=True,
    )
    speak("Done.")


# ==================================================
# CAMERA / SCREENSHOT
# ==================================================

def open_camera():
    speak("Opening camera.")
    os.system("start microsoft.windows.camera:")


def take_picture():
    speak("Taking a picture.")
    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not camera.isOpened():
        speak("Camera not accessible. Close Camera app first.")
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
            speak("Picture taken.")
            log.info(f"Photo: {path}")
        else:
            speak("Could not take picture.")
    finally:
        camera.release()


def take_screenshot():
    os.makedirs(DATA_FOLDER, exist_ok=True)
    filename = datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    path = os.path.join(DATA_FOLDER, filename)
    pyautogui.screenshot(path)
    speak("Screenshot saved.")
    log.info(f"Screenshot: {path}")


# ==================================================
# YOUTUBE / GOOGLE
# ==================================================

def youtube_open():
    speak("Opening YouTube.")
    webbrowser.open("https://www.youtube.com")


def youtube_play(query=""):
    """Open YouTube and search. If empty query, play random popular songs."""
    query = query.strip().lower() if query else ""

    # If user just said "play a song" or similar, play random popular songs
    empty_queries = (
        "", "a song", "song", "songs", "any song", "random song",
        "music", "some song", "a random song", "the song", "the",
        "a", "an", "some", "any", "random", "something", "anything",
    )

    if query in empty_queries:
        speak("Playing random songs on YouTube.")
        webbrowser.open("https://www.youtube.com/results?search_query=popular+songs+2024")
        return

    speak("Playing " + query + " on YouTube.")
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))


def google_open():
    speak("Opening Google.")
    webbrowser.open("https://www.google.com")


def google_search(query):
    if not query:
        google_open()
        return
    speak("Searching Google for " + query)
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))


# ==================================================
# WHATSAPP
# ==================================================

def whatsapp_message(raw):
    match = re.search(r"search\s+(.+?)\s+and\s+send\s+(?:the\s+)?message\s+(.+)", raw, re.IGNORECASE)
    if not match:
        speak("Say: open WhatsApp and search, contact name, and send message, then your message.")
        return
    contact = match.group(1).strip()
    message = match.group(2).strip()
    if not confirm(f"Send message to {contact}?"):
        return
    try:
        speak("Opening WhatsApp.")
        webbrowser.open("https://web.whatsapp.com")
        time.sleep(WHATSAPP_LOAD_SECONDS)
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(1)
        write_text(contact)
        time.sleep(2)
        pyautogui.press("enter")
        time.sleep(2)
        write_text(message)
        time.sleep(1)
        pyautogui.press("enter")
        speak("Message sent to " + contact)
    except Exception as e:
        log.error(f"WhatsApp error: {e}")
        speak("Could not send WhatsApp message.")


# ==================================================
# JAVA / TYPE
# ==================================================

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
        speak("Tell me the file name.")
        return
    os.makedirs(JAVA_FOLDER, exist_ok=True)
    path = os.path.join(JAVA_FOLDER, class_name + ".java")
    if os.path.exists(path):
        speak("File already exists.")
        os.startfile(path)
        return
    code = f'public class {class_name} {{\n    public static void main(String[] args) {{\n        System.out.println("Hello {USER_NAME}");\n    }}\n}}\n'
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    speak(class_name + ".java created.")
    os.startfile(path)


def open_java_folder():
    os.makedirs(JAVA_FOLDER, exist_ok=True)
    speak("Opening Java folder.")
    os.startfile(JAVA_FOLDER)


def type_text(text):
    speak("Click where to type. Starting in 3 seconds.")
    time.sleep(3)
    write_text(text)


# ==================================================
# SYSTEM
# ==================================================

def shutdown_laptop():
    if not confirm("Shut down the laptop?"):
        speak("Cancelled.")
        return
    speak(f"Shutting down in {SHUTDOWN_DELAY_SECONDS} seconds. Say cancel shutdown.")
    os.system(f"shutdown /s /t {SHUTDOWN_DELAY_SECONDS}")


def restart_laptop():
    if not confirm("Restart the laptop?"):
        speak("Cancelled.")
        return
    speak(f"Restarting in {SHUTDOWN_DELAY_SECONDS} seconds.")
    os.system(f"shutdown /r /t {SHUTDOWN_DELAY_SECONDS}")


def cancel_shutdown():
    os.system("shutdown /a")
    speak("Shutdown cancelled.")


def sleep_laptop():
    speak("Sleeping.")
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
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {text}\n")
    speak("Note saved.")


def read_notes():
    if not os.path.exists(NOTES_FILE):
        speak("No notes yet.")
        return
    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        speak("No notes yet.")
        return
    speak("Last notes:")
    for line in lines[-3:]:
        speak(line)


def tell_help():
    speak("I can open and close apps, play YouTube, search Google, take pictures and screenshots, "
          "set reminders and alarms, tell time, date and weather, look up Wikipedia, save notes, "
          "control volume, send WhatsApp messages, and shut down or restart the laptop.")


# ==================================================
# WEATHER / WIKIPEDIA
# ==================================================

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 80: "light rain showers", 81: "rain showers", 82: "heavy rain showers",
    95: "a thunderstorm", 96: "a thunderstorm with hail",
}


def http_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "VoiceAssistant/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_weather(city=""):
    city = city.strip() or DEFAULT_CITY
    try:
        geo = http_json("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + urllib.parse.quote(city))
        results = geo.get("results")
        if not results:
            speak("Could not find " + city)
            return
        place = results[0]
        weather = http_json(
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={place['latitude']}&longitude={place['longitude']}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
            "weather_code,wind_speed_10m&timezone=auto"
        )["current"]
        desc = WEATHER_CODES.get(weather["weather_code"], "unknown")
        speak(
            f"In {place['name']} it is {round(weather['temperature_2m'])} degrees, "
            f"feels like {round(weather['apparent_temperature'])}, {desc}. "
            f"Humidity {round(weather['relative_humidity_2m'])} percent."
        )
    except Exception as e:
        log.error(f"Weather error: {e}")
        speak("Could not get weather. Check internet.")


def wikipedia_answer(topic):
    topic = topic.strip()
    if not topic:
        speak("What to look up?")
        return
    speak("Looking up " + topic)
    try:
        search = http_json(
            "https://en.wikipedia.org/w/api.php?action=query&list=search"
            "&format=json&srlimit=1&srsearch=" + urllib.parse.quote(topic)
        )
        hits = search.get("query", {}).get("search", [])
        if not hits:
            speak("Nothing found.")
            return
        title = hits[0]["title"]
        page = http_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_")))
        extract = page.get("extract", "").strip()
        if not extract:
            speak("No summary.")
            return
        sentences = re.split(r"(?<=[.!?])\s+", extract)
        speak(" ".join(sentences[:2]))
    except Exception as e:
        log.error(f"Wikipedia: {e}")
        speak("Could not reach Wikipedia.")


# ==================================================
# REMINDERS / ALARMS
# ==================================================

reminder_queue = queue.Queue()
pending_reminders = {}
_reminder_counter = 0

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30,
}
UNIT_SECONDS = {"second": 1, "seconds": 1, "sec": 1, "minute": 60, "minutes": 60, "min": 60, "hour": 3600, "hours": 3600}


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
    rid = _reminder_counter
    t = threading.Timer(seconds, _fire_reminder, args=(rid, message))
    t.daemon = True
    t.start()
    due = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    pending_reminders[rid] = (due, message, t)


def set_reminder(raw):
    match = re.search(
        r"remind me in (\w+)\s+(second|minute|hour|sec|min)s?\s*(?:to|about|that)?\s*(.*)",
        raw, re.IGNORECASE,
    )
    if not match:
        speak("Say: remind me in 10 minutes to drink water.")
        return
    amt_text = match.group(1).lower()
    unit = match.group(2).lower()
    what = match.group(3).strip() or "your reminder"
    amt = int(amt_text) if amt_text.isdigit() else NUMBER_WORDS.get(amt_text)
    if not amt:
        speak("Say number in digits.")
        return
    schedule_reminder(amt * UNIT_SECONDS.get(unit, 60), "Reminder: " + what)
    plural = "" if amt == 1 else "s"
    speak(f"Okay, reminder in {amt} {unit}{plural}.")


def set_alarm(cmd):
    text = cmd.replace(".", "")
    match = re.search(r"alarm\s+(?:for|at)\s+(\d{1,2})(?:[:\s](\d{2}))?\s*(am|pm)?", text)
    if not match:
        speak("Say: set alarm for 7:30 am.")
        return
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3)
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    elif not suffix and hour <= 7:
        hour += 12
    if hour > 23 or minute > 59:
        speak("Invalid time.")
        return
    now = datetime.datetime.now()
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due <= now:
        due += datetime.timedelta(days=1)
    label = due.strftime("%I:%M %p")
    schedule_reminder((due - now).total_seconds(), f"Alarm! It is {label}.")
    speak("Alarm set for " + label)


def list_reminders():
    items = sorted(pending_reminders.values(), key=lambda x: x[0])
    if not items:
        speak("No reminders.")
        return
    speak(f"{len(items)} pending.")
    for due, msg, _ in items:
        speak(f"{due.strftime('%I:%M %p')}: {msg}")


def cancel_reminders():
    for _, _, t in list(pending_reminders.values()):
        t.cancel()
    pending_reminders.clear()
    speak("All reminders cancelled.")


# ==================================================
# EMAIL
# ==================================================

def send_email():
    address = os.environ.get("ASSISTANT_EMAIL")
    password = os.environ.get("ASSISTANT_EMAIL_PASSWORD")
    if not address or not password:
        speak("Email not set up.")
        return
    speak("Who to send?")
    spoken = listen(timeout=6, phrase_limit=5).lower().strip()
    recipient = None
    recipient_name = None
    for name, email_addr in CONTACTS.items():
        if name in spoken:
            recipient = email_addr
            recipient_name = name
            break
    if not recipient:
        speak("Contact not found.")
        return
    speak("Subject?")
    subject = listen(timeout=6, phrase_limit=10)
    if not subject:
        speak("Email cancelled.")
        return
    speak("Message?")
    body = listen(timeout=8, phrase_limit=30)
    if not body:
        speak("Email cancelled.")
        return
    if not confirm(f"Send to {recipient_name}?"):
        return
    try:
        msg = EmailMessage()
        msg["From"] = address
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(address, password)
            s.send_message(msg)
        speak("Email sent.")
    except Exception as e:
        log.error(f"Email: {e}")
        speak("Could not send email.")


# ==================================================
# AI
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
        speak("AI not set up.")
        return
    ai_history.append({"role": "user", "content": question})
    try:
        response = client.messages.create(
            model=AI_MODEL, max_tokens=300, system=AI_SYSTEM_PROMPT, messages=ai_history,
        )
        answer = "".join(b.text for b in response.content if b.type == "text").strip()
        if not answer:
            raise ValueError("Empty")
    except Exception as e:
        log.error(f"AI: {e}")
        ai_history.pop()
        speak("AI not reachable.")
        return
    ai_history.append({"role": "assistant", "content": answer})
    while len(ai_history) > 12:
        del ai_history[0:2]
    speak(answer)


# ==================================================
# COMMAND HANDLER - FLEXIBLE
# ==================================================

def handle(raw):
    command = raw.lower().strip()
    print(f"[DEBUG] Command: {command}")
    log.info(f"[DEBUG] Command: {command}")

    # ============ EXIT / HELLO ============
    if "quit assistant" in command:
        speak(f"Goodbye {USER_NAME}!")
        return False

    if command in ("exit", "bye", "goodbye"):
        speak(f"Okay {USER_NAME}, pausing. Say Hello to resume.")
        return "exit"

    if command in ("hello", "hi", "wake up") or command.startswith("hello"):
        speak(f"Hello {USER_NAME}! How can I help you?")
        return "hello"

    if "standby" in command or "stand by" in command:
        standby_mode()
        return True

    # ============ CANCEL SHUTDOWN ============
    if "cancel shutdown" in command or "cancel restart" in command:
        cancel_shutdown()
        return True

    # ============ AI ============
    if command.startswith("ask ai ") or command.startswith("ask claude ") or command.startswith("ask "):
        question = re.sub(r"^ask (?:ai |claude )?", "", raw, flags=re.IGNORECASE).strip()
        ask_ai(question)
        return True

    if "forget conversation" in command:
        ai_history.clear()
        speak("Cleared.")
        return True

    # ============ REMINDERS ============
    if "remind me" in command:
        set_reminder(raw)
        return True
    if "alarm" in command and ("set" in command or "for" in command):
        set_alarm(command)
        return True
    if "list reminders" in command or "list alarms" in command:
        list_reminders()
        return True
    if "cancel reminders" in command or "cancel alarms" in command:
        cancel_reminders()
        return True

    # ============ EMAIL ============
    if "send email" in command or "send an email" in command or "send mail" in command:
        send_email()
        return True

    # ============ WHATSAPP ============
    if "whatsapp" in command and "search" in command and "message" in command:
        whatsapp_message(raw)
        return True

    # ============ HELP ============
    if "help" in command or "what can you do" in command:
        tell_help()
        return True

    # ============ YOUTUBE ============
    if "youtube" in command or "you tube" in command or "utube" in command:
        if "play" in command or "song" in command or "music" in command or "search" in command:
            query = raw.lower()
            for w in ["open", "youtube", "you tube", "utube", "play", "song", "music",
                      "search", "on", "the", "a", "an", "for", "please"]:
                query = re.sub(rf"\b{w}\b", "", query, flags=re.IGNORECASE)
            query = query.strip()
            youtube_play(query)
        else:
            youtube_open()
        return True

    # ============ PLAY SONG (flexible) ============
    if command.startswith("play "):
        query = raw[5:].strip()
        # Remove all filler words
        query = re.sub(r"\bon youtube\b", "", query, flags=re.IGNORECASE).strip()
        for w in ["song", "songs", "the", "a", "an", "some", "any", "random",
                  "music", "something", "anything"]:
            query = re.sub(rf"\b{w}\b", "", query, flags=re.IGNORECASE).strip()
        query = " ".join(query.split())  # remove extra spaces

        youtube_play(query)
        return True

    # ============ GOOGLE ============
    if "google" in command:
        if "search" in command:
            query = raw.lower()
            for w in ["open", "google", "search", "for", "on", "the", "a", "an", "please"]:
                query = re.sub(rf"\b{w}\b", "", query, flags=re.IGNORECASE)
            query = query.strip()
            google_search(query)
        else:
            google_open()
        return True

    # ============ SEARCH (generic) ============
    if "search" in command and "youtube" not in command and "google" not in command:
        query = raw.lower()
        for w in ["search", "for", "on", "the", "a", "an", "please"]:
            query = re.sub(rf"\b{w}\b", "", query, flags=re.IGNORECASE)
        query = query.strip()
        if query:
            google_search(query)
        return True

    # ============ CAMERA ============
    if "camera" in command:
        open_camera()
        return True

    if "take a picture" in command or "take the picture" in command or "take photo" in command or "take a photo" in command:
        take_picture()
        return True

    if "screenshot" in command or "screen shot" in command:
        take_screenshot()
        return True

    # ============ JAVA ============
    if "java folder" in command:
        open_java_folder()
        return True
    if command.startswith("create a file") or command.startswith("create file"):
        spoken = re.sub(r"^create (?:a )?file", "", command).strip()
        create_java_file(spoken)
        return True

    # ============ TYPE ============
    if command.startswith("type "):
        type_text(raw[5:].strip())
        return True

    # ============ CLOSE ALL ============
    if "close all" in command:
        close_all_apps()
        return True

    # ============ CLOSE APP ============
    if command.startswith("close "):
        app = command[6:].strip()
        close_app(app)
        return True

    # ============ OPEN APP (flexible) ============
    if command.startswith("open ") or command.startswith("launch ") or command.startswith("start "):
        for prefix in ("open ", "launch ", "start "):
            if command.startswith(prefix):
                app = command[len(prefix):].strip()
                break
        if app:
            open_app(app)
        else:
            speak("What should I open?")
        return True

    # ============ POWER ============
    if "shutdown" in command or "shut down" in command:
        shutdown_laptop()
        return True
    if "restart" in command:
        restart_laptop()
        return True
    if "sleep" in command and "laptop" in command:
        sleep_laptop()
        return True

    # ============ VOLUME ============
    if "volume up" in command or "increase volume" in command:
        change_volume("up")
        return True
    if "volume down" in command or "decrease volume" in command:
        change_volume("down")
        return True
    if command == "mute" or "mute volume" in command:
        change_volume("mute")
        return True

    # ============ NOTES ============
    if command.startswith("note ") or command.startswith("take a note "):
        text = re.sub(r"^(?:take a note|note)\s+", "", raw, flags=re.IGNORECASE).strip()
        save_note(text)
        return True
    if "read notes" in command or "read my notes" in command:
        read_notes()
        return True

    # ============ WEATHER ============
    if "weather" in command or "temperature" in command:
        match = re.search(r"(?:in|of|for)\s+([a-z ]+)$", command)
        get_weather(match.group(1) if match else "")
        return True

    # ============ WIKIPEDIA ============
    if command.startswith("wikipedia "):
        wikipedia_answer(raw[10:])
        return True
    if command.startswith("tell me about "):
        wikipedia_answer(raw[14:])
        return True
    if command.startswith("who is "):
        wikipedia_answer(raw[7:])
        return True

    # ============ JOKE ============
    if "joke" in command:
        speak(random.choice(JOKES))
        return True

    # ============ TIME / DATE ============
    if "time" in command and len(command.split()) <= 6:
        speak("Time is " + datetime.datetime.now().strftime("%I:%M %p"))
        return True
    if "date" in command and len(command.split()) <= 6:
        speak("Date is " + datetime.datetime.now().strftime("%d %B %Y"))
        return True

    # ============ UNKNOWN ============
    if AI_FALLBACK and get_ai_client():
        ask_ai(raw)
    else:
        speak(f"Sorry {USER_NAME}, I don't know that command.")

    return True


# ==================================================
# GUI
# ==================================================

def build_gui():
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
        text="Say 'Help' for commands  |  'Exit' to pause  |  'Hello' to resume",
        font=("Segoe UI", 10),
        bg="#1e1e2e",
        fg="#6c7086",
        pady=10,
    )
    footer.pack()

    gui_window.protocol("WM_DELETE_WINDOW", on_gui_close)

    return gui_window


def gui_log(speaker, text):
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
    global assistant_running, assistant_active

    speak(f"Hello {USER_NAME}, I am your personal voice assistant. How can I help you?")
    set_gui_status("Listening...", "#a6e3a1")

    while assistant_running:
        try:
            check_reminders()

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

            if result is False:
                assistant_running = False
                break
            elif result == "exit":
                assistant_active = False
                set_gui_status("Paused - say 'Hello' to wake", "#f9e2af")
                gui_log("system", "Assistant paused. Say 'Hello' to resume.")
                continue
            elif result == "hello":
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
    standby_event.set()
    gui_log("system", "Standby mode. Say 'Hey Assistant' to wake up.")
    set_gui_status("Standby", "#f9e2af")


def stop_assistant():
    global assistant_running, assistant_active
    assistant_running = False
    assistant_active = False
    standby_event.clear()
    gui_log("system", "Stopping assistant...")
    set_gui_status("Stopped", "#f38ba8")


def on_gui_close():
    global assistant_running
    assistant_running = False
    if gui_window:
        gui_window.destroy()


def process_gui_queue():
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
        try:
            assistant_loop()
        except KeyboardInterrupt:
            log.info("Stopped by keyboard.")


if __name__ == "__main__":
    main()