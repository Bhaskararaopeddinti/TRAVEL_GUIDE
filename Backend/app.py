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


def generate_speech(text, voice_id="Matthew", locale="en-US"):
    murf_api_key = os.getenv("MURF_API_KEY", "").strip()

    # Check if Murf key exists and is non-empty
    if not murf_api_key:
        print("[Murf] Configured: False (MURF_API_KEY is not set or empty in environment)")
        return "", "Murf API key is not configured in Render environment variables."

    print("[Murf] Configured: True")
    print("[Murf] Request started")

    clean_text = (text or "").strip()
    if not clean_text:
        print("[Murf] Warning: Empty text provided. Skipping audio generation.")
        return "", "No text provided for audio generation."

    url = "https://global.api.murf.ai/v1/speech/stream"
    headers = {
        "api-key": murf_api_key,
        "Content-Type": "application/json"
    }

    v_id = voice_id or "Matthew"
    loc = locale or "en-US"

    payload = {
        "text": clean_text,
        "voiceId": v_id,
        "voice_id": v_id,
        "locale": loc,
        "model": "falcon-2",
        "format": "MP3",
        "sampleRate": 24000,
        "channelType": "MONO"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"[Murf] Response status: {response.status_code}")
        print(f"[Murf] Response content type: {response.headers.get('Content-Type', 'unknown')}")

        # If falcon-2 returns 400 with model message, fallback to FALCON
        if response.status_code == 400 and "model" in response.text.lower():
            print("[Murf] 'falcon-2' model rejected. Retrying with 'FALCON'...")
            payload["model"] = "FALCON"
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            print(f"[Murf] Fallback response status: {response.status_code}")

        if response.status_code == 200:
            audio_bytes = response.content
            if audio_bytes and len(audio_bytes) > 50:
                encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")
                print(f"[Murf] Audio generated successfully ({len(audio_bytes)} bytes).")
                return encoded_audio, None
            else:
                print("[Murf Error] Response was status 200 but audio payload was empty.")
                return "", "Murf returned empty audio data."
        else:
            safe_err = response.text[:200].replace(murf_api_key, "[REDACTED]")
            print(f"[Murf Error] API error status: {response.status_code}")
            print(f"[Murf Error] Safe response: {safe_err}")
            return "", f"Murf audio is temporarily unavailable (Status {response.status_code})."

    except requests.exceptions.Timeout:
        print("[Murf Error] Request timed out after 30 seconds.")
        return "", "Murf audio request timed out."
    except Exception as e:
        safe_exc = str(e).replace(murf_api_key, "[REDACTED]")
        print(f"[Murf Error] Request exception: {safe_exc}")
        return "", "Murf audio is temporarily unavailable."


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
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    murf_key = os.getenv("MURF_API_KEY", "").strip()
    return jsonify({
        "status": "ok",
        "gemini_configured": bool(gemini_key),
        "murf_configured": bool(murf_key)
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

    encoded_audio, speech_notice = generate_speech(text_description, voice_id, locale)

    return jsonify({
        "description": text_description,
        "audioBase64": encoded_audio or "",
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