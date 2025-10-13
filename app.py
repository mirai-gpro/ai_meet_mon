# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import time
import markdown
from pathlib import Path
import pyaudio
import threading
import queue
import os
import json
import re

# Google Cloud & Gemini
from google.cloud import speech, texttospeech
from google import genai
from google.genai import types
import google.api_core.exceptions
import google.generativeai as genai_rest

# ==========================================
# 1. 認証情報設定
# ==========================================
GEMINI_API_KEY_OVERRIDE = "AIzaSyDQjSNbVj781K5OhYsFiM86rpSGU-37l8o"
GCP_PROJECT_ID_OVERRIDE = "ai-meet-473716"

if GCP_PROJECT_ID_OVERRIDE:
    os.environ['GOOGLE_CLOUD_PROJECT'] = GCP_PROJECT_ID_OVERRIDE
genai_rest.configure(api_key=GEMINI_API_KEY_OVERRIDE)

# ==========================================
# 2. デバイス設定（UI で選択可能）
# ==========================================
DEVICE_CONFIG_FILE = "device_config.json"

DEFAULT_INPUT_DEVICE_INDEX = 5      # ヘッドセット (PLT V3200 Series Hands-
DEFAULT_OUTPUT_DEVICE_INDEX = 14    # ヘッドセット (PLT V3200 Series Hands-

DEFAULT_INPUT_DEVICE_NAME = "ヘッドセット (PLT V3200 Series Hands-"
DEFAULT_TTS_OUTPUT_DEVICE_NAME = "ヘッドセット (PLT V3200 Series Hands-"

# ==========================================
# 3. オーディオ設定
# ==========================================
RATE = 16000
CHUNK = int(RATE / 10)
CHANNELS = 1
FORMAT = pyaudio.paInt16
LANGUAGE_CODE = 'ja-JP'
SILENCE_FRAMES = int(RATE * 0.05)

# ==========================================
# 4. ファイルパス
# ==========================================
MEETING_SUMMARY_FILE_PATH = "meeting_summary.txt"
TRANSCRIPT_FILE_PATH = "meeting_transcript_log.md"
DRAFT_CACHE_FILE = "meeting_draft_cache.html"
DRAFT_MARKDOWN_FILE = "meeting_draft.md"

# ==========================================
# 5. STT設定（話者分離）
# ==========================================
DIARIZATION_CONFIG = speech.SpeakerDiarizationConfig(
    enable_speaker_diarization=True,
    max_speaker_count=4
)

STREAMING_CONFIG = speech.StreamingRecognitionConfig(
    config=speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code=LANGUAGE_CODE,
        diarization_config=DIARIZATION_CONFIG
    ),
    interim_results=False
)

# ==========================================
# 6. Flask & CORS 初期化
# ==========================================
app = Flask(__name__)
CORS(app)

class AppState:
    def __init__(self):
        self.stt_thread = None
        self.stt_running = False
        self.chat_session = None
        self.tts_client = None
        self.stt_client = None
        self.gemini_client = None
        self.audio_devices = {}
        self.input_device_index = DEFAULT_INPUT_DEVICE_INDEX
        self.output_device_index = DEFAULT_OUTPUT_DEVICE_INDEX
        self.input_device_name = DEFAULT_INPUT_DEVICE_NAME
        self.output_device_name = DEFAULT_TTS_OUTPUT_DEVICE_NAME
        self.response_queue = queue.Queue()

state = AppState()

# ==========================================
# 7. ユーティリティ関数
# ==========================================
def sanitize_for_tts(text: str) -> str:
    """TTS用にテキストをクリーンアップ"""
    text = re.sub(r'[\U0001F300-\U0001F9FF]', '', text)
    text = re.sub(r'[♪♫♬𝄐𝄑⟪⟫\*\[\]\{\}]', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ==========================================
# 8. ファイル操作
# ==========================================
def load_device_config():
    if os.path.exists(DEVICE_CONFIG_FILE):
        try:
            with open(DEVICE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                input_idx = config.get('input_device_index')
                output_idx = config.get('output_device_index')
                if input_idx is not None:
                    state.input_device_index = input_idx
                if output_idx is not None:
                    state.output_device_index = output_idx
                state.input_device_name = config.get('input_device_name', DEFAULT_INPUT_DEVICE_NAME)
                state.output_device_name = config.get('output_device_name', DEFAULT_TTS_OUTPUT_DEVICE_NAME)
                print(f"[INFO] デバイス設定をロード: input_idx={state.input_device_index}, output_idx={state.output_device_index}")
                return True
        except Exception as e:
            print(f"[WARN] デバイス設定ロード失敗: {e}")
    return False

def save_device_config():
    try:
        config = {
            'input_device_index': state.input_device_index,
            'output_device_index': state.output_device_index,
            'input_device_name': state.input_device_name,
            'output_device_name': state.output_device_name
        }
        with open(DEVICE_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"[INFO] デバイス設定を保存しました")
    except Exception as e:
        print(f"[ERROR] デバイス設定保存失敗: {e}")

def log_transcript(log_entry: str, file_path: str):
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_entry = f"{timestamp} {log_entry}\n"
    try:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(formatted_entry)
    except Exception as e:
        print(f"[ERROR] 議事録ファイル書き込みエラー: {e}")

def read_local_summary_file(file_path: str) -> str:
    if not os.path.exists(file_path):
        return "資料が見つかりませんでした。"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return "資料の読み込みに失敗しました。"

def generate_meeting_transcript():
    md_path = Path(TRANSCRIPT_FILE_PATH)
    if not md_path.exists():
        return "# 議事録ファイルが見つかりません。"
    raw_text = md_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return "# 議事ログが空です。"
    
    prompt = f"""
以下は会議の議事ログです。以下の構成で議事録ドラフトを作成してください：

# 会議議事録

## 会議基本情報
- 開催日時：（ログから推測）
- 件名：（重要な議題から推測）
- 参加者：（[話者 X]から推測）

## 議題と決定事項
（重要な決定事項をまとめてください）

## 次回アクション
（誰が何をいつまでにするのかを明確に）

---

【議事ログ】
{raw_text}

上記のログを整理し、Markdown形式で出力してください。
"""
    model = genai_rest.GenerativeModel("gemini-2.5-flash-preview-05-20")
    response = model.generate_content(prompt)
    return response.text if hasattr(response, "text") else "生成に失敗しました。"

def generate_and_cache_draft():
    print("[INFO] 議事録ドラフトを生成中...")
    summary_md = generate_meeting_transcript()
    
    try:
        with open(DRAFT_MARKDOWN_FILE, 'w', encoding='utf-8') as f:
            f.write(summary_md)
    except Exception as e:
        print(f"[ERROR] Markdown 保存失敗: {e}")
    
    html_content = markdown.markdown(summary_md)
    try:
        with open(DRAFT_CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(html_content)
    except Exception as e:
        print(f"[ERROR] キャッシュ保存失敗: {e}")
    
    return html_content

def load_draft_cache():
    if os.path.exists(DRAFT_CACHE_FILE):
        try:
            with open(DRAFT_CACHE_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"[WARN] キャッシュ読み込み失敗: {e}")
    return None

def load_draft_markdown():
    if os.path.exists(DRAFT_MARKDOWN_FILE):
        try:
            with open(DRAFT_MARKDOWN_FILE, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"[WARN] Markdown ドラフト読み込み失敗: {e}")
    return None

def save_draft_markdown(content: str):
    try:
        with open(DRAFT_MARKDOWN_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        html_content = markdown.markdown(content)
        with open(DRAFT_CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"[OK] ドラフトを更新")
        return True
    except Exception as e:
        print(f"[ERROR] ドラフト保存失敗: {e}")
        return False

# ==========================================
# 9. クライアント初期化
# ==========================================
def initialize_clients():
    try:
        state.stt_client = speech.SpeechClient()
        state.tts_client = texttospeech.TextToSpeechClient()
        state.gemini_client = genai.Client(api_key=GEMINI_API_KEY_OVERRIDE)
        print("[INFO] クライアント初期化完了")
        return True
    except Exception as e:
        print(f"[ERROR] クライアント初期化失敗: {e}")
        return False

def scan_audio_devices():
    p = pyaudio.PyAudio()
    devices_list = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        device_info = {
            'index': i,
            'name': info.get('name', ''),
            'input_channels': info.get('maxInputChannels', 0),
            'output_channels': info.get('maxOutputChannels', 0)
        }
        devices_list.append(device_info)
    state.audio_devices = {d['index']: d for d in devices_list}
    p.terminate()

def setup_audio_devices():
    p = pyaudio.PyAudio()
    input_found = False
    output_found = False
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if i == state.input_device_index and info.get('maxInputChannels') > 0:
            print(f"[OK] STT入力: Index {i}")
            input_found = True
        if i == state.output_device_index and info.get('maxOutputChannels') > 0:
            print(f"[OK] TTS出力: Index {i}")
            output_found = True
    p.terminate()
    return input_found and output_found

# ==========================================
# 10. TTS
# ==========================================
def synthesize_and_play(tts_text: str):
    if not tts_text.strip():
        return
    cleaned_text = sanitize_for_tts(tts_text)
    if not cleaned_text:
        print(f"[WARN] クリーンアップ後、テキストが空になりました")
        return
    print(f"[INFO] AI応答生成: {cleaned_text[:50]}...")
    log_transcript(f"[AI] {tts_text}", TRANSCRIPT_FILE_PATH)
    try:
        synthesis_input = texttospeech.SynthesisInput(text=tts_text)
        voice = texttospeech.VoiceSelectionParams(language_code="ja-JP", name="ja-JP-Chirp3-HD-Sulafat")
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=RATE)
        response = state.tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
        silence_buffer = b'\x00\x00' * SILENCE_FRAMES
        audio_to_play = silence_buffer + response.audio_content
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, output_device_index=state.output_device_index)
        stream.write(audio_to_play)
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("[INFO] AI音声再生完了")
    except Exception as e:
        print(f"[ERROR] TTS エラー: {e}")

# ==========================================
# 11. STT
# ==========================================
class MicrophoneStream:
    def __init__(self):
        self._p = pyaudio.PyAudio()
        self.stream = self._p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK, input_device_index=state.input_device_index)
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self._p.terminate()
    
    def generator(self):
        while True:
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                if not data:
                    break
                yield speech.StreamingRecognizeRequest(audio_content=data)
            except Exception as e:
                print(f"[ERROR] MicrophoneStream エラー: {e}")
                break

def stt_worker():
    print("\n" + "="*60)
    print("[INFO] STT ワーカースレッド開始")
    print(f"[DEBUG] 入力デバイス Index: {state.input_device_index}")
    print(f"[DEBUG] 出力デバイス Index: {state.output_device_index}")
    print("="*60 + "\n")
    state.stt_running = True
    
    summary_content = read_local_summary_file(MEETING_SUMMARY_FILE_PATH)
    base_system = """
あなたは、議事録修正モードの**AIアシスタント**です。
ユーザーからの質問や修正リクエストに対してのみ応答してください。
ユーザーからの指示がない限り、発言してはいけません。
"""
    final_system = base_system + f"\n\n【議事録ログ】\n{summary_content}"
    
    state.chat_session = state.gemini_client.chats.create(
        model='gemini-2.5-flash-preview-05-20',
        config=types.GenerateContentConfig(system_instruction=final_system),
    )
    print("[INFO] Gemini チャットセッション開始")
    
    while state.stt_running:
        try:
            with MicrophoneStream() as stream:
                requests = stream.generator()
                print("[INFO] STT 認識開始")
                responses = state.stt_client.streaming_recognize(config=STREAMING_CONFIG, requests=requests)
                
                for response in responses:
                    if not response.results:
                        continue
                    result = response.results[0]
                    if not result.alternatives:
                        continue
                    
                    if result.is_final:
                        transcript = result.alternatives[0].transcript
                        speaker_id = 0
                        if result.alternatives[0].words and result.alternatives[0].words[0].speaker_tag:
                            speaker_id = result.alternatives[0].words[0].speaker_tag
                        
                        tagged_transcript = f"[話者 {speaker_id}] {transcript}"
                        print(f"[STT] {tagged_transcript}")
                        log_transcript(tagged_transcript, TRANSCRIPT_FILE_PATH)
                        
                        gemini_response_obj = state.chat_session.send_message(tagged_transcript)
                        
                        if gemini_response_obj and gemini_response_obj.text:
                            gemini_response = gemini_response_obj.text.strip()
                            if gemini_response:
                                state.response_queue.put({"user": tagged_transcript, "ai": gemini_response})
                                synthesize_and_play(gemini_response)
        
        except google.api_core.exceptions.OutOfRange:
            print("[WARN] STT 305秒制限に達しました。再開します...")
            time.sleep(1)
            continue
        
        except Exception as e:
            print(f"[ERROR] STT エラー: {e}")
            time.sleep(3)
            continue

# ==========================================
# 12. Flask ルート
# ==========================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["GET"])
def generate():
    print("[INFO] 議事録を再生成中...")
    html_content = generate_and_cache_draft()
    return jsonify({"summary": html_content})

@app.route("/get-draft-cache", methods=["GET"])
def get_draft_cache():
    cached = load_draft_cache()
    if cached:
        return jsonify({"summary": cached, "from_cache": True}), 200
    html_content = generate_and_cache_draft()
    return jsonify({"summary": html_content, "from_cache": False}), 200

@app.route("/get-draft-markdown", methods=["GET"])
def get_draft_markdown():
    md_content = load_draft_markdown()
    return jsonify({"markdown": md_content or ""}), 200

@app.route("/update-draft", methods=["POST"])
def update_draft():
    data = request.json
    updated_markdown = data.get("draft_markdown", "").strip()
    if not updated_markdown:
        return jsonify({"status": "error", "message": "ドラフトが空です"}), 400
    if save_draft_markdown(updated_markdown):
        return jsonify({"status": "success", "message": "ドラフトを更新しました"}), 200
    return jsonify({"status": "error", "message": "ドラフト保存に失敗しました"}), 500

@app.route("/start-stt", methods=["POST"])
def start_stt():
    if not state.stt_running:
        state.stt_thread = threading.Thread(target=stt_worker, daemon=True)
        state.stt_thread.start()
        return jsonify({"status": "STT started"}), 200
    return jsonify({"status": "STT already running"}), 200

@app.route("/stop-stt", methods=["POST"])
def stop_stt():
    state.stt_running = False
    return jsonify({"status": "STT stopped"}), 200

@app.route("/chat-message", methods=["POST"])
def chat_message():
    data = request.json
    user_text = data.get("message", "").strip()
    
    if not user_text or not state.chat_session:
        return jsonify({"error": "Invalid message or chat not initialized"}), 400
    
    try:
        log_transcript(f"[ユーザー] {user_text}", TRANSCRIPT_FILE_PATH)
        gemini_response_obj = state.chat_session.send_message(user_text)
        
        if gemini_response_obj and gemini_response_obj.text:
            ai_response = gemini_response_obj.text.strip()
            log_transcript(f"[AI] {ai_response}", TRANSCRIPT_FILE_PATH)
            return jsonify({"ai_response": ai_response}), 200
    except Exception as e:
        print(f"[ERROR] Chat エラー: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/get-devices", methods=["GET"])
def get_devices():
    input_devices = [d for d in state.audio_devices.values() if d['input_channels'] > 0]
    output_devices = [d for d in state.audio_devices.values() if d['output_channels'] > 0]
    return jsonify({
        "input_devices": input_devices,
        "output_devices": output_devices,
        "current_input": state.input_device_index,
        "current_output": state.output_device_index
    }), 200

@app.route("/set-device", methods=["POST"])
def set_device():
    data = request.json
    input_index = data.get("input_device_index")
    output_index = data.get("output_device_index")
    
    if input_index is not None:
        state.input_device_index = input_index
        if input_index in state.audio_devices:
            state.input_device_name = state.audio_devices[input_index]['name']
    
    if output_index is not None:
        state.output_device_index = output_index
        if output_index in state.audio_devices:
            state.output_device_name = state.audio_devices[output_index]['name']
    
    save_device_config()
    
    return jsonify({
        "status": "success",
        "input_device": state.input_device_name,
        "output_device": state.output_device_name,
        "input_index": state.input_device_index,
        "output_index": state.output_device_index
    }), 200

# ==========================================
# 13. メイン
# ==========================================
if __name__ == "__main__":
    print("[INFO] 初期化中...")
    
    load_device_config()
    
    if not initialize_clients():
        print("[FATAL] クライアント初期化失敗")
        exit(1)
    
    scan_audio_devices()
    
    if not setup_audio_devices():
        print("[WARN] デバイス設定に問題があります。UI から設定してください。")
    
    print("[INFO] Flask アプリ起動...")
    app.run(debug=False, host="127.0.0.1", port=5000)
