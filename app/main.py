import os
from dotenv import load_dotenv
import uuid
import wave
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None

load_dotenv()

app = FastAPI()

# Serve the static frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

GENERATED_DIR = os.path.join(os.path.dirname(__file__), "..", "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

def wave_file(filename: str, pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def get_genai_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if genai is None:
        raise RuntimeError("google-genai package is not installed")
    if not api_key:
        # Helpful message: if you're running from the notebook the key may be set there
        raise RuntimeError("GEMINI_API_KEY not set in environment. If you have it in a Jupyter notebook, put it in a .env file or export it in your shell. Example: export GEMINI_API_KEY=...")
    # ensure the environment variable is set for the library
    os.environ["GEMINI_API_KEY"] = api_key
    return genai.Client()


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(os.path.dirname(__file__), "..", "static", "index.html"), "r") as f:
        return HTMLResponse(content=f.read())


@app.post("/generate")
async def generate(text: Optional[str] = Form(None), prompt_file: Optional[UploadFile] = File(None)):
    """Generate TTS audio from a text prompt or uploaded file. Returns JSON with audio URL."""
    if not text and not prompt_file:
        raise HTTPException(status_code=400, detail="Provide 'text' field or upload a file (prompt_file)")

    if prompt_file:
        content = (await prompt_file.read()).decode("utf-8")
    else:
        content = text

    try:
        client = get_genai_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # First, create a short transcript if the provided text is a short instruction
    # Otherwise, use the content directly.
    try:
        # Attempt to generate a transcript if the content looks like an instruction
        transcript_resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=content,
        )
        transcript = transcript_resp.text if hasattr(transcript_resp, "text") else content

        tts_resp = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=transcript,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
            ),
        )
        data = tts_resp.candidates[0].content.parts[0].inline_data.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    file_name = f"{uuid.uuid4().hex}.wav"
    file_path = os.path.abspath(os.path.join(GENERATED_DIR, file_name))
    wave_file(file_path, data)

    url_path = f"/generated/{file_name}"
    return {"audio_url": url_path}


@app.get("/generated/{file_name}")
async def serve_generated(file_name: str):
    path = os.path.abspath(os.path.join(GENERATED_DIR, file_name))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="audio/wav")
