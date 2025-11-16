import os
from dotenv import load_dotenv
import uuid
import wave
import json
from typing import Optional
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi import Body
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

# ------------------------------ Batched Episode Logic ------------------------------

def build_batched_prompt(topics: List[str], hosts: List[Dict[str, str]], durations: Dict[str, int], style: str, total_cap_seconds: Optional[int] = None) -> str:
    """Construct a single prompt asking Gemini to: plan segments, write scripts, and return structured JSON.
    We request JSON so we can parse programmatically and then feed a combined script into a single TTS call.
    """
    host_descriptions = "\n".join([f"- {h.get('name')}: {h.get('persona','')}" for h in hosts])
    topics_list = "\n".join([f"- {t}" for t in topics])
    dur_info = "\n".join([f"{k}={v}s" for k,v in durations.items()])
    total_note = f"Try to keep total under {total_cap_seconds} seconds." if total_cap_seconds else ""
    return f"""
You are an AI radio show writer. Generate a full episode plan AND scripts in JSON only (no extra commentary outside JSON). Requirements:

Hosts (names and personalities):\n{host_descriptions}\n
Topics (in order):\n{topics_list}\n
Segment timing targets (seconds): {dur_info}. {total_note}
Segment order template: cold_open -> for each topic: topic then banter -> ad -> outro.

Return STRICT JSON with this structure ONLY:
{{
  "plan": [
     {{"index": 0, "type": "cold_open", "target_seconds": <int>}},
     {{"index": 1, "type": "topic", "topic": "...", "target_seconds": <int>}},
     {{"index": 2, "type": "banter", "target_seconds": <int>}},
     ...,
     {{"index": N, "type": "ad", "target_seconds": <int>}},
     {{"index": N+1, "type": "outro", "target_seconds": <int>}}
  ],
  "scripts": [
     {{"index": <int>, "type": "cold_open", "approx_seconds": <int>, "script": "MULTI-SPEAKER DIALOGUE"}},
     {{"index": <int>, "type": "topic", "topic": "...", "approx_seconds": <int>, "script": "..."}},
     ...
  ],
  "combined_plaintext": "Concatenate all segments in order. Each line should start with SPEAKER_NAME: text."
}}

Guidelines:
- Style: {style}
- Make each host's voice distinct per their personality.
- Use only host names as prefixes (e.g., Maya: or Rowan: ).
- Keep scripts concise enough for TTS; no markdown.
- Avoid reserved JSON-breaking characters (escape quotes correctly inside JSON values).
- Do not add explanation outside the JSON.
""".strip()


def parse_batched_json(raw_text: str) -> Dict[str, Any]:
    """Attempt to extract JSON object from model output.
    Strategy: find first '{' and last '}' and json.loads that slice."""
    start = raw_text.find('{')
    end = raw_text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")
    snippet = raw_text[start:end+1]
    return json.loads(snippet)


def build_tts_input_from_combined(data: Dict[str, Any]) -> str:
    """Return text to feed to TTS model. We trust 'combined_plaintext' if present; otherwise join scripts."""
    if 'combined_plaintext' in data and isinstance(data['combined_plaintext'], str):
        return data['combined_plaintext']
    # fallback: merge scripts
    scripts = data.get('scripts', [])
    ordered = sorted(scripts, key=lambda x: x.get('index', 0))
    lines = []
    for s in ordered:
        txt = s.get('script', '')
        lines.append(txt)
    return "\n".join(lines)


@app.post('/create_episode_batched')
async def create_episode_batched(payload: Dict[str, Any] = Body(...)):
    """Create a full episode with EXACTLY two Gemini calls:
    1) One text call for plan + all scripts (batched JSON)
    2) One TTS call for the entire combined dialogue

    Payload: {
      topics: [str],
      hosts: [{name: str, persona: str}],
      durations: { segment_type: seconds },
      style: str,
      total_cap_seconds?: int
    }
    Returns: { plan, scripts, audio_url }
    """
    topics = payload.get('topics') or []
    hosts = payload.get('hosts') or []
    durations = payload.get('durations') or {}
    style = payload.get('style', 'radio-friendly')
    total_cap = payload.get('total_cap_seconds')

    if not topics or not hosts:
        raise HTTPException(status_code=400, detail="Provide non-empty 'topics' and 'hosts'")

    try:
        client = get_genai_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # ---- First Gemini call: planning + scripts ----
    prompt = build_batched_prompt(topics, hosts, durations, style, total_cap)
    try:
        text_resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw_text = text_resp.text if hasattr(text_resp, 'text') else str(text_resp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text generation failed: {e}")

    try:
        structured = parse_batched_json(raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse JSON from model output: {e}")

    # ---- Second Gemini call: single TTS for entire episode ----
    tts_input = build_tts_input_from_combined(structured)
    try:
        tts_resp = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=tts_input,
            config=types.GenerateContentConfig(response_modalities=["AUDIO"]),
        )
        data = tts_resp.candidates[0].content.parts[0].inline_data.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {e}")

    file_name = f"episode_{uuid.uuid4().hex}.wav"
    file_path = os.path.abspath(os.path.join(GENERATED_DIR, file_name))
    wave_file(file_path, data)

    return {
        "plan": structured.get('plan'),
        "scripts": structured.get('scripts'),
        "audio_url": f"/generated/{file_name}",
        "model_calls": 2
    }


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
