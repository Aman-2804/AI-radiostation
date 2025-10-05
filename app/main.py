import os
import uuid
import wave
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body
import json
import time
import shutil

from pydub import AudioSegment

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None

app = FastAPI()

from dotenv import load_dotenv
import logging


def load_first_env():
    """Attempt to load .env, then env, then env.example. Return loaded path or None."""
    candidates = [
        os.path.join(os.path.dirname(__file__), '..', '.env'),
        os.path.join(os.path.dirname(__file__), '..', 'env'),
        os.path.join(os.path.dirname(__file__), '..', 'env.example'),
    ]
    for p in candidates:
        p = os.path.abspath(p)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            load_dotenv(dotenv_path=p)
            logging.info(f"Loaded env from {p}")
            return p
    # fallback: call with default (loads .env if present)
    load_dotenv()
    return None


# Load environment variables from common files (.env, env, env.example)
loaded_env = load_first_env()

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


def export_mp3_from_segments(segments: list, out_path: str):
    """segments: list of pydub.AudioSegment; export mixed mp3 file to out_path"""
    if not segments:
        raise ValueError("No audio segments to mix")
    # Concatenate with small crossfade
    result = segments[0]
    for seg in segments[1:]:
        result = result.append(seg, crossfade=300)
    # Export as mp3
    result.export(out_path, format="mp3", bitrate="192k")


def plan_episode(topics: list, durations: dict, total_minutes: Optional[int] = None):
    """Create a simple plan of segments given topics and durations mapping.
    durations: dict mapping segment type to seconds, e.g., {"topic":180, "banter":60}
    Returns list of segments with type and length.
    """
    plan = []
    # cold open
    plan.append({"type": "cold_open", "seconds": durations.get("cold_open", 15)})
    # For each topic, add topic + banter
    for t in topics:
        plan.append({"type": "topic", "topic": t, "seconds": durations.get("topic", 180)})
        plan.append({"type": "banter", "seconds": durations.get("banter", 30)})
    # ad + outro
    plan.append({"type": "ad", "seconds": durations.get("ad", 30)})
    plan.append({"type": "outro", "seconds": durations.get("outro", 30)})
    return plan


def write_segment_script(client, segment: dict, hosts: list, style: str = "radio-friendly"):
    """Call Gemini text model to write a short script for the segment."""
    seg_type = segment.get("type")
    if seg_type == "cold_open":
        prompt = f"Write a {style} cold open of {segment.get('seconds',15)} seconds to introduce the show. Hosts: {', '.join([h['name'] for h in hosts])}."
    elif seg_type == "topic":
        prompt = f"Write a {style} {segment.get('seconds',180)} seconds radio script about the topic '{segment.get('topic')}' as a dialogue between the hosts: {', '.join([h['name'] for h in hosts])}. Keep it lively and conversational."
    elif seg_type == "banter":
        prompt = f"Write a {style} {segment.get('seconds',30)} seconds playful banter between the hosts after a topic about {segment.get('topic','the previous topic')}."
    elif seg_type == "ad":
        prompt = f"Write a {style} {segment.get('seconds',30)} seconds ad read that fits the station tone: {style}."
    elif seg_type == "outro":
        prompt = f"Write a {style} {segment.get('seconds',30)} seconds outro closing the show."
    else:
        prompt = f"Write a short {style} segment"

    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return resp.text if hasattr(resp, 'text') else str(resp)


def tts_from_text(client, text: str, hosts: list, filename: str):
    """Use Gemini TTS preview model to synthesize the provided text. For simplicity,
    we'll assign all text to the first host voice. Returns path to saved wav.
    """
    # For MVP: a single-voice TTS; mapping multi-speaker is future work.
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
        ),
    )
    data = response.candidates[0].content.parts[0].inline_data.data
    wave_file(filename, data)
    return filename


def get_genai_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if genai is None:
        raise RuntimeError("google-genai package is not installed")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in environment")
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


@app.post('/create_episode')
async def create_episode(payload: dict = Body(...)):
    """Payload expects:
    { topics: [str], hosts: [{name, persona}], durations: {topic: seconds, banter: seconds, ...}, style: str }
    """
    try:
        client = get_genai_client()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    topics = payload.get('topics', [])
    hosts = payload.get('hosts', [])
    durations = payload.get('durations', {})
    style = payload.get('style', 'radio-friendly')

    if not topics or not hosts:
        raise HTTPException(status_code=400, detail="Provide topics (list) and hosts (list)")

    plan = plan_episode(topics, durations)

    segments_audio = []
    temp_paths = []
    try:
        for i, seg in enumerate(plan):
            script = write_segment_script(client, seg, hosts, style=style)
            # Save TTS wav
            wav_name = f"{uuid.uuid4().hex}.wav"
            wav_path = os.path.abspath(os.path.join(GENERATED_DIR, wav_name))
            tts_from_text(client, script, hosts, wav_path)
            temp_paths.append(wav_path)
            # load into pydub
            audio_seg = AudioSegment.from_file(wav_path)
            # apply a short fade in/out
            audio_seg = audio_seg.fade_in(50).fade_out(50)
            # optionally add background bed — minimal: lower volume a bit
            segments_audio.append(audio_seg)

        # Export final mp3
        out_name = f"episode_{int(time.time())}.mp3"
        out_path = os.path.abspath(os.path.join(GENERATED_DIR, out_name))
        export_mp3_from_segments(segments_audio, out_path)

        return {"audio_url": f"/generated/{out_name}", "plan": plan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # cleanup temp wavs
        for p in temp_paths:
            try:
                os.remove(p)
            except Exception:
                pass


@app.get('/status')
async def status():
    """Return basic status including whether GEMINI_API_KEY is available to the running server (masked)."""
    key = os.environ.get('GEMINI_API_KEY')
    return {
        'gemini_key_loaded': bool(key),
        'gemini_key_masked': (key[:4] + '...' + key[-4:]) if key else None
    }


@app.post('/set_key')
async def set_key(body: dict = Body(...)):
    """Set GEMINI_API_KEY in-memory and optionally persist to project .env.

    Body format: { "key": "...", "persist": true|false }
    """
    key = body.get('key')
    persist = bool(body.get('persist', False))
    if not key:
        raise HTTPException(status_code=400, detail='Missing key in request body')
    os.environ['GEMINI_API_KEY'] = key
    if persist:
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
        try:
            with open(env_path, 'w') as f:
                f.write(f"GEMINI_API_KEY={key}\n")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Failed to write .env: {e}')
    return { 'gemini_key_loaded': True, 'gemini_key_masked': key[:4] + '...' + key[-4:] }


@app.get("/generated/{file_name}")
async def serve_generated(file_name: str):
    path = os.path.abspath(os.path.join(GENERATED_DIR, file_name))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="audio/wav")
