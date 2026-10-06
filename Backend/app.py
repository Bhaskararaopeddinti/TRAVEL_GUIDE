import os
import time
import tempfile
import base64
import re
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv, find_dotenv
from google import genai
import requests

# Load environment variables from .env (checking Backend/ and root directory)
current_dir = Path(__file__).resolve().parent
load_dotenv(current_dir / ".env")
load_dotenv(current_dir.parent / ".env")
load_dotenv(find_dotenv(usecwd=True))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MURF_API_KEY = os.getenv("MURF_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
PORT = int(os.getenv("PORT", 5000))

app = Flask(__name__)

# Allowed origins for CORS (Production Render Frontend + Localhost environments)
ALLOWED_ORIGINS = [
    "https://travel-guide-frontend-uswz.onrender.com",
    "http://127.0.0.1:5000",
    "http://localhost:5000",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://localhost",
    "http://127.0.0.1",
]

render_origin_pattern = re.compile(r"^https:\/\/.*\.onrender\.com$")

CORS(
    app,
    resources={
        r"/*": {
            "origins": ALLOWED_ORIGINS + [render_origin_pattern],
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    },
    supports_credentials=True
)

@app.after_request
def add_cors_headers(response):
    """Ensure CORS headers are consistently applied, including on error responses."""
    origin = request.headers.get("Origin")
    if origin:
        if (
            origin in ALLOWED_ORIGINS
            or origin.endswith(".onrender.com")
            or "localhost" in origin
            or "127.0.0.1" in origin
        ):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

PROMPTS = {
    "Summary": """
You are a professional tourist guide.
Provide a high-level overview of "{place}" in {language}.

Focus on:
- The historical significance
- Why the place is famous
- Key architectural or cultural highlights

Keep the explanation concise, engaging, and easy to follow.
Avoid excessive details and dates.
Limit the response to around 200 words.

Respond ONLY in {language}.
""",

    "Detailed": """
You are a professional tourist guide.
Provide a detailed and immersive explanation of "{place}" in {language}.

Cover:
- Historical background and timeline
- Architectural design and unique features
- Cultural importance and notable events
- Interesting facts and visitor insights

Explain concepts clearly and in a storytelling manner.
Include relevant details and examples to create a rich experience.
Limit the response to around 400 words.

Respond ONLY in {language}.
"""
}

class GeminiUnavailableError(Exception):
    """Raised when Gemini upstream is unavailable or experiencing temporary high demand."""
    pass


def is_gemini_temporary_error(err):
    err_str = str(err).lower()
    return any(keyword in err_str for keyword in [
        "503", "unavailable", "high demand", "resourceexhausted", "quota", "429", "deadline"
    ])


def generate_description(place, answer_type, language):
    if not client:
        raise ValueError("GEMINI_API_KEY is not configured. Please set it in your .env file.")

    prompt_template = PROMPTS.get(answer_type, PROMPTS["Summary"])
    prompt = prompt_template.format(place=place, language=language)

    # Models to try in order of fallback in case of high demand
    models_to_try = [
        GEMINI_MODEL,
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-3.1-flash-lite",
        "gemini-1.5-flash",
    ]
    seen = set()
    candidate_models = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

    last_error = None
    all_temporary_errors = True

    for model_name in candidate_models:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                last_error = e
                temp_error = is_gemini_temporary_error(e)
                if not temp_error:
                    all_temporary_errors = False

                print(f"[Gemini] Model '{model_name}' attempt {attempt + 1}/{max_retries} failed: {e}")

                if temp_error and attempt < max_retries - 1:
                    sleep_time = 1.0 * (attempt + 1)
                    print(f"[Gemini] High demand / 503 detected. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    # Move to next fallback model
                    break

    if last_error:
        if all_temporary_errors or is_gemini_temporary_error(last_error):
            raise GeminiUnavailableError(
                "Gemini is temporarily experiencing high demand. Please try again."
            )
        raise last_error

    raise RuntimeError("Failed to generate description from Gemini.")


def generate_speech(text, voice_id, locale):
    # Check if Murf key is missing or still masked with asterisks
    if not MURF_API_KEY or MURF_API_KEY.startswith("*") or "YOUR_" in MURF_API_KEY:
        print("[Murf] Notice: MURF_API_KEY is not set or contains asterisks/placeholders in .env. Skipping Murf API call.")
        return None, "Murf API key is missing or masked. Update MURF_API_KEY in .env with your unmasked key."

    url = "https://global.api.murf.ai/v1/speech/stream"
    headers = {
        "api-key": MURF_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "voice_id": voice_id,
        "text": text,
        "locale": locale,
        "model": "FALCON",
        "format": "MP3",
        "sampleRate": 24000,
        "channelType": "MONO"
    }

    temp_path = None
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
                temp_path = temp_audio.name
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        temp_audio.write(chunk)
            print(f"[Murf] Speech generated successfully for voice '{voice_id}' ({locale}).")
            return temp_path, None
        else:
            err_msg = f"Murf API responded with status {response.status_code}: {response.text}"
            print(f"[Murf Error] {err_msg}")
            return None, err_msg
    except Exception as e:
        print(f"[Murf Error] Request failed: {e}")
        return None, str(e)


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "Travel Guide Backend is running successfully!",
        "endpoints": {
            "/health": "GET - Server health check",
            "/generate-audio-guide": "POST - Generate travel guide & audio"
        }
    })


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


@app.route("/health", methods=["GET", "OPTIONS"])
def health_check():
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify({
        "status": "ok",
        "gemini_configured": bool(GEMINI_API_KEY),
        "murf_configured": bool(MURF_API_KEY and not MURF_API_KEY.startswith("*"))
    })


@app.route("/generate-audio-guide", methods=["POST", "OPTIONS"])
def generate_audio_guide():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body provided."}), 400

    place = str(data.get("place", "")).strip()
    answer_type = str(data.get("answerType", "")).strip() or "Summary"
    language = str(data.get("language", "")).strip() or "English"
    voice_id = str(data.get("voiceId", "")).strip() or "Matthew"
    locale = str(data.get("locale", "")).strip() or "en-US"

    if not place:
        return jsonify({"error": "Destination place name is required."}), 400

    try:
        text_description = generate_description(place, answer_type, language)
    except GeminiUnavailableError as e:
        print(f"[Gemini 503] {e}")
        return jsonify({
            "error": "Gemini is temporarily experiencing high demand. Please try again.",
            "description": "",
            "audioBase64": "",
            "audioNotice": "Gemini is temporarily unavailable due to high demand. Please try again in a few moments."
        }), 503
    except ValueError as e:
        print(f"[Config Error] {e}")
        return jsonify({
            "error": str(e),
            "description": "",
            "audioBase64": "",
            "audioNotice": str(e)
        }), 500
    except Exception as e:
        print(f"[Error] Failed to generate description: {e}")
        return jsonify({
            "error": "Failed to generate description. Please try again.",
            "description": "",
            "audioBase64": "",
            "audioNotice": None
        }), 500

    encoded_audio = ""
    audio_path, speech_notice = generate_speech(text_description, voice_id, locale)

    if audio_path and os.path.exists(audio_path):
        try:
            with open(audio_path, "rb") as f:
                encoded_audio = base64.b64encode(f.read()).decode("utf-8")
        finally:
            try:
                os.unlink(audio_path)
            except Exception:
                pass

    return jsonify({
        "description": text_description,
        "audioBase64": encoded_audio,
        "audioNotice": speech_notice if not encoded_audio else None
    })


@app.errorhandler(400)
def handle_bad_request(e):
    return jsonify({"error": getattr(e, "description", "Bad Request")}), 400


@app.errorhandler(404)
def handle_not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def handle_server_error(e):
    return jsonify({"error": "An internal server error occurred. Please try again."}), 500


@app.errorhandler(503)
def handle_service_unavailable(e):
    return jsonify({
        "error": "Gemini is temporarily unavailable. Please try again.",
        "description": "",
        "audioBase64": "",
        "audioNotice": "Gemini is temporarily unavailable due to high demand. Please try again in a few moments."
    }), 503


@app.errorhandler(Exception)
def handle_general_exception(e):
    print(f"[Unhandled Exception] {e}")
    return jsonify({"error": "An unexpected server error occurred. Please try again."}), 500


if __name__ == "__main__":
    print(f"Starting Travel Guide Backend on http://127.0.0.1:{PORT}")
    print(f"- Gemini API: {'Configured' if GEMINI_API_KEY else 'Missing (check .env)'}")
    print(f"- Murf API: {'Configured' if (MURF_API_KEY and not MURF_API_KEY.startswith('*')) else 'Unmasked key needed in .env'}")
    app.run(host="0.0.0.0", port=PORT, debug=True)