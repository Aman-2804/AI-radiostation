import sys
import json
import os
import subprocess
import socket, base64, time

from google import genai
from google.genai import types
from dotenv import load_dotenv

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

load_dotenv()

HOST, PORT = "localhost", 8000
PASS = "hackme"

def fetch_chunk(param, segment_idx, status_file):
    try:
        transcript = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"""Generate a short transcript around 50 words for a podcast based on this description:\n\n
                        {param}\n
                        The hosts names are Dr. Aman and Liam.""").text
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=transcript,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                        speaker_voice_configs=[
                        types.SpeakerVoiceConfig(
                            speaker='Dr. Aman',
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name='Kore',
                                )
                            )
                        ),
                        types.SpeakerVoiceConfig(
                            speaker='Liam',
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name='Puck',
                                )
                            )
                        ),
                        ]
                    )
                )
            )
        )
        print(transcript)
        data = response.candidates[0].content.parts[0].inline_data.data
        initial_status = {
            'status': 'success',
            'message': 'it worked'
        }
        return data
    except Exception as e:
        initial_status = {
            'status': 'failed',
            'message': f'Failed: {str(e)}'
        }
        print(f'Error: {e}')
    finally:
        if segment_idx == 0:
            with open(status_file, 'w') as f:
                json.dump(initial_status, f)

def pcm_to_mp3_bytes(pcm_bytes):
    ffmpeg_cmd = [
        'ffmpeg',
        '-f', 's16le',
        '-ar', str(12000),
        '-ac', str(2),
        '-i', 'pipe:0',
        '-f', 'mp3',
        '-b:a', '96k',
        'pipe:1'
    ]
    proc = subprocess.run(
        ffmpeg_cmd,
        input=pcm_bytes,
        capture_output=True,
        check=True
    )
    return proc.stdout

def stream_chunk(pcm_bytes, sock):
    BITRATE = 96_000
    BYTES_PER_SEC = BITRATE // 8
    CHUNK_SIZE = 4096

    mp3_bytes = pcm_to_mp3_bytes(pcm_bytes)

    i = 0
    while i < len(mp3_bytes):
        sock.sendall(mp3_bytes[i:i+CHUNK_SIZE])
        i += CHUNK_SIZE
        time.sleep(CHUNK_SIZE / BYTES_PER_SEC)

def main():
    if len(sys.argv) > 2:
        frequency = sys.argv[1]
        stationname = sys.argv[2]
        prompt = sys.argv[3]
        launch_id = sys.argv[4]
    else:
        frequency = -1
        stationname = "nothing"
        prompt = "nothing"
        launch_id = -1

    MOUNT = f"/{frequency}.mp3"
    print(MOUNT)

    # to let frontend know if creation was successful
    os.makedirs('status', exist_ok=True)
    status_file = f'status/{launch_id}.json'

    # to keep track of existing stations
    os.makedirs('frequencies', exist_ok=True)
    freq_file = f'frequencies/{frequency}.json'
    if os.path.exists(freq_file):
        initial_status = {
            'status': 'failed',
            'message': f'frequency {frequency} is occupied'
        }
        with open(status_file, 'w') as f:
            json.dump(initial_status, f)
        return 0
    else:
        print("sdfsd")
        record = {
            'name': stationname
        }
        with open(freq_file, 'w') as f:
            json.dump(record, f)
    
    try:
        assert launch_id != -1
        assert frequency != -1
        
        # create connection
        s = socket.create_connection((HOST, PORT))
        auth = base64.b64encode(f"source:{PASS}".encode()).decode()
        hdr = (
            f"SOURCE {MOUNT} ICE/1.0\r\n"
            f"Authorization: Basic {auth}\r\n"
            "Content-Type: audio/mpeg\r\n"
            "\r\n"
        )
        s.sendall(hdr.encode())

        segment_idx = 0
        chunk = fetch_chunk(prompt, segment_idx, status_file)
        while True:
            stream_chunk(chunk, s)
            #s.sendall(fetch_chunk())   # send a chunk, then loop (keep socket open)
            time.sleep(0.5)
            segment_idx += 1
            #break
    finally:
        s.close()

if __name__ == "__main__":
    main()