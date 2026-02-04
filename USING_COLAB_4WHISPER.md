# Using Google Colab T4 GPU for Whisper Transcription

Local whisper transcription is slow (~30+ min per video on CPU). Google Colab's free T4 GPU can do it in **2-5 minutes**.

## Option 2: Automated via Google Drive

### How it works
```
Local Script                    Google Drive                 Colab Notebook
     |                               |                            |
     |-- upload mp3 --------------->|                            |
     |                               |<-- watch folder -----------|
     |                               |                            |
     |                               |-- process with whisper --->|
     |                               |                            |
     |                               |<-- save txt ---------------|
     |<-- poll & download txt ------|                            |
```

### Setup

**1. Create Google Drive folders:**
```
/MyDrive/whisper_queue/
├── input/      # Script uploads mp3 here
├── output/     # Colab saves txt here
└── processing/ # Currently being processed
```

**2. Colab Notebook (`whisper_worker.ipynb`):**
```python
# Mount Google Drive
from google.colab import drive
drive.mount('/content/drive')

# Install whisper
!pip install -U openai-whisper

import whisper
import os
import shutil
import time

# Paths
INPUT_DIR = '/content/drive/MyDrive/whisper_queue/input'
OUTPUT_DIR = '/content/drive/MyDrive/whisper_queue/output'
PROCESSING_DIR = '/content/drive/MyDrive/whisper_queue/processing'

# Load model (runs on T4 GPU)
model = whisper.load_model("large-v2")

# Watch loop
while True:
    files = [f for f in os.listdir(INPUT_DIR) if f.endswith(('.mp3', '.m4a', '.wav'))]

    if not files:
        print("No files, waiting...")
        time.sleep(10)
        continue

    for filename in files:
        input_path = os.path.join(INPUT_DIR, filename)
        processing_path = os.path.join(PROCESSING_DIR, filename)

        # Move to processing
        shutil.move(input_path, processing_path)
        print(f"Processing: {filename}")

        # Transcribe
        result = model.transcribe(
            processing_path,
            language="Chinese",
            initial_prompt="繁體中文"
        )

        # Save transcript
        txt_filename = os.path.splitext(filename)[0] + '.txt'
        output_path = os.path.join(OUTPUT_DIR, txt_filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result['text'])

        # Cleanup
        os.remove(processing_path)
        print(f"Done: {txt_filename}")
```

**3. Local script changes (`manipulate_bookmarklm_from_yt_playlist.py`):**
```python
def whisper_via_gdrive(mp3_path: str, output_dir: Path) -> tuple[bool, str]:
    """Upload to Google Drive, wait for Colab to process, download result."""
    from pydrive2.auth import GoogleAuth
    from pydrive2.drive import GoogleDrive

    # Auth (first time will open browser)
    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()
    drive = GoogleDrive(gauth)

    # Upload mp3 to input folder
    filename = Path(mp3_path).name
    file = drive.CreateFile({'title': filename, 'parents': [{'id': 'INPUT_FOLDER_ID'}]})
    file.SetContentFile(mp3_path)
    file.Upload()
    print(f"  Uploaded {filename} to Google Drive")

    # Poll for result
    txt_filename = Path(mp3_path).stem + '.txt'
    for _ in range(60):  # Wait up to 10 minutes
        time.sleep(10)
        file_list = drive.ListFile({'q': f"title='{txt_filename}' and 'OUTPUT_FOLDER_ID' in parents"}).GetList()
        if file_list:
            # Download
            result_file = file_list[0]
            local_txt = output_dir / txt_filename
            result_file.GetContentFile(str(local_txt))
            result_file.Delete()  # Cleanup
            print(f"  Downloaded {txt_filename}")
            return True, str(local_txt)

    return False, "Timeout waiting for transcription"
```

**4. Dependencies:**
```bash
pip install pydrive2
```

---

## Option 3: Colab API via ngrok/gradio

### How it works
```
Local Script                         Colab (with ngrok)
     |                                      |
     |-- POST /transcribe (audio URL) ---->|
     |                                      |-- download audio
     |                                      |-- whisper transcribe
     |<-- return transcript text -----------|
```

### Setup

**1. Colab Notebook (`whisper_api.ipynb`):**
```python
# Install dependencies
!pip install -U openai-whisper gradio

import whisper
import gradio as gr
import requests
import tempfile
import os

# Load model on T4 GPU
model = whisper.load_model("large-v2")

def transcribe_url(audio_url: str) -> str:
    """Download audio from URL and transcribe."""
    # Download audio
    response = requests.get(audio_url)
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
        f.write(response.content)
        temp_path = f.name

    try:
        # Transcribe
        result = model.transcribe(
            temp_path,
            language="Chinese",
            initial_prompt="繁體中文"
        )
        return result['text']
    finally:
        os.unlink(temp_path)

def transcribe_file(audio_file) -> str:
    """Transcribe uploaded audio file."""
    # audio_file is already a filepath string when using type="filepath"
    result = model.transcribe(
        audio_file,
        language="Chinese",
        initial_prompt="繁體中文"
    )
    return result['text']

# Create Gradio interface
demo = gr.Interface(
    fn=transcribe_file,
    inputs=gr.Audio(type="filepath"),
    outputs=gr.Textbox(label="Transcript"),
    title="Whisper Transcription API"
)

# Launch with public URL
demo.launch(share=True, show_error=True)
# This prints a URL like: https://xxxxx.gradio.live
```

**2. Local script integration:**
```python
import requests

COLAB_API_URL = "https://xxxxx.gradio.live/api/predict"  # From Colab output

def whisper_via_colab_api(mp3_path: str) -> tuple[bool, str]:
    """Send audio to Colab API, receive transcript."""
    with open(mp3_path, 'rb') as f:
        # Gradio API format
        response = requests.post(
            COLAB_API_URL,
            files={'files': f}
        )

    if response.ok:
        result = response.json()
        transcript = result['data'][0]
        return True, transcript

    return False, f"API error: {response.text}"
```

**Alternative: Simple Flask API with ngrok:**
```python
# In Colab
!pip install flask pyngrok openai-whisper

from flask import Flask, request, jsonify
from pyngrok import ngrok
import whisper

app = Flask(__name__)
model = whisper.load_model("large-v2")

@app.route('/transcribe', methods=['POST'])
def transcribe():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400

    file = request.files['file']
    temp_path = f'/tmp/{file.filename}'
    file.save(temp_path)

    result = model.transcribe(
        temp_path,
        language="Chinese",
        initial_prompt="繁體中文"
    )

    return jsonify({'transcript': result['text']})

# Start ngrok tunnel
public_url = ngrok.connect(5000)
print(f"API URL: {public_url}")

app.run(port=5000)
```

---

## Comparison

| Aspect | Option 2 (Google Drive) | Option 3 (API) |
|--------|------------------------|----------------|
| Setup complexity | Medium | Medium |
| Requires Colab running | Yes (watch loop) | Yes (API server) |
| Latency | Higher (polling) | Lower (direct) |
| Reliability | Good (Drive is stable) | Depends on ngrok |
| Free tier limits | Drive: 15GB | ngrok: 1 tunnel |
| Best for | Batch processing | Real-time |

## Recommendations

1. **For batch processing**: Option 2 (Google Drive)
   - Start Colab, let it run
   - Script uploads all mp3s
   - Come back later for results

2. **For real-time**: Option 3 (API)
   - Start Colab with API
   - Script calls API for each file
   - Faster turnaround per file

## Notes

- Colab free tier disconnects after ~90 min idle or ~12 hours max
- Keep Colab tab active or use Colab Pro
- T4 GPU processes ~10-30x faster than CPU
- `large-v2` model: best quality, ~2-5 min per 30-min audio on T4
