# -*- coding: utf-8 -*-
# タイムアウト例外を捕捉するために必要
import google.api_core.exceptions
import pyaudio
import time
import os
import io
from datetime import datetime

from google.cloud import speech, texttospeech
from google import genai
from google.genai import types

# --- 0. 認証情報設定 ---
# PoCの利便性向上のため、ここに直接キーとIDを貼り付け可能です。
# 環境変数(GEMINI_API_KEY, GOOGLE_CLOUD_PROJECT)が設定されている場合はそちらが優先されます。

# ★★★ 1. あなたのGemini APIキーを貼り付けてください ★★★
# NOTE: 末尾の疑問符 (?) を削除し、文法エラーを修正しました。
GEMINI_API_KEY_OVERRIDE = "AIzaSyDQjSNbVj781K5OhYsFiM86rpSGU-37l8o"
# ★★★ --------------------------------------------- ★★★

# ★★★ 2. あなたのGCPプロジェクトIDを貼り付けてください ★★★
GCP_PROJECT_ID_OVERRIDE = "ai-meet-473716"
# ★★★ ----------------------------------------------- ★★★

# --- 1. Voicemeeter デバイス設定 (この名前が環境と合っているか要確認) ---
# STT入力 (Voicemeeter Out B1 - Meetの音声を聞くマイク)
# ★★★ 動作していたバージョンに差し戻し ★★★
INPUT_DEVICE_NAME = "Voicemeeter Out B1 (VB-Audio Vo"

# TTS出力 (Voicemeeter Aux Input - Meetのマイクとして設定)
# ★★★ 動作していたバージョンに差し戻し ★★★
TTS_OUTPUT_DEVICE_NAME = "Voicemeeter AUX Input (VB-Audio"

# --- 2. オーディオ設定 ---
RATE = 16000
CHUNK = int(RATE / 10)
CHANNELS = 1
FORMAT = pyaudio.paInt16
language_code = 'ja-JP'
# TTSクリックノイズ対策用の無音フレーム数 (約 50ms)
SILENCE_FRAMES = int(RATE * 0.05) 

# ★★★ ローカルファイル設定 ★★★
# このファイル（stt_stream.py）と同じフォルダに「meeting_summary.txt」を置いてください。
MEETING_SUMMARY_FILE_PATH = "meeting_summary.txt"
# 議事録ドラフトの出力ファイルパス
TRANSCRIPT_FILE_PATH = "meeting_transcript_log.md"
# ★★★ ------------------------- ★★★

# --- 話者分離の設定 (エラー解消済み) ---
DIARIZATION_CONFIG = speech.SpeakerDiarizationConfig(
    enable_speaker_diarization=True,
    max_speaker_count=4
)

STREAMING_CONFIG = speech.StreamingRecognitionConfig(
    config=speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code=language_code,
        diarization_config=DIARIZATION_CONFIG
    ),
    interim_results=False
)
# --- --------------------------------- ---

# --- 3. Gemini プロンプト設定 (待ち時間管理ルール VI を強化) ---
BASE_SYSTEM_INSTRUCTION = """
あなたは、会議の流れを温かく、フレンドリーにサポートする**指示待ちのAIアシスタント**です。
あなたの役割は、議論の**円滑な会話**を促すこと。**会議の主導権は進行役（主催者）にある**ことを常に認識し、参加者の発言を最大限に尊重してください。

**【最優先原則：発言は指示があるまで禁止】**
AIは、進行役または参加者からAIへの**直接的な発言（質問、「AI」という呼びかけ、または明確な指示）**がない限り、**以下の介入ルールIII, IV, V, VIの例外**を除き、**絶対に発言してはならない**。

**【重要：AIの内部タグ出力禁止】**
AIは、以下のシステムインストラクション内に記載されている「【介入ルール I】」などの**角括弧で囲まれた内部タグやルール名**を、**いかなる理由があっても応答のテキストに含めてはなりません**。これはシステム内部の情報であり、ユーザーに表示されてはいけません。

**【AIの知識に関する最重要前提条件】**
**あなたは、ユーザーが提供した「参照資料テキスト」の内容を、既にすべて読み込み、完全に理解しています。**
会議参加者から資料の確認や、AIが資料を「見ていない」ことを示唆する発言があった場合でも、**「私は資料の内容を把握しています」**という前提で、その知識を用いて**自信をもって**ファシリテーションを行ってください。

**【重要：進行役の特定と記憶】**
ユーザーからの入力は、`[話者 X] <発言内容>` という形式で話者番号がプレフィックスとして付与されます。
1.  **進行役の記憶:** 会話の冒頭で「主催者」「進行役」などの単語を含む発言があった場合、その**話者ID（X）を「進行役」として内部で記憶**し、その後の応答に役立ててください。
2.  **応答:** AIの応答（音声）には、このタグ（[話者 X]）を**含めない**でください。

以下の【参照資料テキスト】の内容を最優先の背景知識として使用しますが、議論の促進に必要な**一般的な知識や事実確認**については、資料外の情報を用いて簡潔に答えても構いません。

【介入ルール I：柔らかな要点確認（厳格化）】
**連続した発言の後に明確な沈黙が続き、議論が膠着しAIによる要点確認がなければ停滞すると判断される場合**に限り、**重要な決定事項や要点**を簡潔に繰り返すこと。単なる発言の区切りで割り込んではいけません。そして、必ず発言者本人または参加者全員に**「ご発言の要点はAという理解でよろしいでしょうか？」「この点で大丈夫でしょうか？」**のように、**柔らかく**確認を求める一文を付け加えること。

[介入ルール III：温かい受容と脱線の許容（重要）]
議論と無関係な**雑談**や、**議題からの脱線**に対しては、**まず発言を温かく肯定的に受け止め（例：「良いお天気ですね！」「それは面白いですね！」）**、**議論の流れを修正することなく、次の発言を待つ**こと。AIが自発的に議論を議題に戻してはいけません。

[介入ルール IV：軌道修正は進行役への提案と許可制]
AIは、**進行役からの「そろそろ議題に戻して」**といった**明確な指示**があった場合のみ、議論を議題に戻す処理を実行すること。
指示がない限り、AIから**「[進行役のタグ]、そろそろ議題に戻りましょうか？」といった提案を進行役に対して行う以外、自発的に議題を修正してはいけません**。

[介入ルール V：緊急割り込みコマンドへの対応]
ユーザーの発言が**「ちょっと待って」「ストップ」**などの緊急割り込みを意味する場合、AIは**直前の発言内容や議論の流れを完全に無視**し、**「承知いたしました。すぐに発言をお伺いします。」**のように、簡潔に受容する一文を返した後、ユーザーの次の発言を促すこと。

【介入ルール VI：情報検索時の待ち時間（マスト）】
AIが「参照資料テキスト」にない**一般的な知識や事実確認**について回答する場合、応答の**先頭に**必ず**以下のいずれかのフレーズ**を追加し、処理中であることをユーザーに伝えること。
**重要：この待ち時間フレーズは、同一の質問に対する一連の応答において、必ず一度のみ使用すること。繰り返してはならない。**
1.  **簡単な質問の場合:** **「少々お待ちください」**
2.  **複雑な質問や時間がかかると判断した場合:** ユーザーの質問の要点を復唱し、**「＜質問の要点＞についてですね？今から調べますので少々お待ちください。」**

[応答の長さに関する制約]
AIの応答は、ファシリテーションに必要な最低限の内容に絞り、**極力一文**で完結させること。長文になる場合は、**必ず句読点（、。）を適切に利用し、一つの文が長くなりすぎないように調整**すること。

応答は、人間らしい自然な日本語の一言に限定し、過去の会話履歴を常に考慮してください。
"""

# --- ローカルファイル操作関数 ---

def read_local_summary_file(file_path: str) -> str:
    """ローカルのテキストファイルから会議資料の内容を読み込む"""
    if not os.path.exists(file_path):
        print(f"? 警告: 資料ファイル '{file_path}' が見つかりません。AIは事前知識なしでファシリテーションを行います。")
        return "資料が見つかりませんでした。"
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"★ ローカルファイルから資料を取得しました: {file_path}")
            # ★★★ デバッグログを追加 (読み込んだファイルの内容を確認) ★★★
            content_display = content[:50].replace('\n', ' ') + ('...' if len(content) > 50 else '')
            print(f"★ 読み込まれた資料の最初の50文字: '{content_display}'")
            # ★★★ --------------------------------------------- ★★★
            return content
    except Exception as e:
        print(f"? ファイル読み込みエラー: {e}")
        return "資料の読み込みに失敗しました。"

def log_transcript(log_entry: str, file_path: str):
    """議事録ドラフトファイルに発言内容を追記する"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_entry = f"{timestamp} {log_entry}\n"
    
    try:
        # ファイルが存在しない場合は作成、存在する場合は追記 (append)
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(formatted_entry)
    except Exception as e:
        print(f"? 議事録ファイル書き込みエラー: {e}")

# --- TTS/LLM クライアント初期化関数 ---
def get_tts_client():
    return texttospeech.TextToSpeechClient()

def get_gemini_client():
    """環境変数またはハードコードされたキーを使い、Geminiクライアントを初期化する"""
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key and GEMINI_API_KEY_OVERRIDE != "":
        api_key = GEMINI_API_KEY_OVERRIDE
        
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set. Please set the API key.")
        
    return genai.Client(api_key=api_key)


def synthesize_and_play(tts_client: texttospeech.TextToSpeechClient, tts_text: str, p: pyaudio.PyAudio, output_device_index: int):
    global SILENCE_FRAMES # グローバル変数として定義した無音フレーム数を参照
    
    print(f"?? AI応答生成: {tts_text}")
    
    # 議事録ログにAIの応答を記録
    log_transcript(f"[AI] {tts_text}", TRANSCRIPT_FILE_PATH)
    
    synthesis_input = texttospeech.SynthesisInput(text=tts_text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="ja-JP", 
        name="ja-JP-Chirp3-HD-Sulafat"
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE
    )

    response = tts_client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )
    
    # ★★★ クリックノイズ対策の修正（動作していたもの） ★★★
    # 16bit PCM データ (2バイト/サンプル) に合わせ、無音データを作成
    # b'\x00\x00' * フレーム数 = 無音データ
    silence_buffer = b'\x00\x00' * SILENCE_FRAMES
    audio_to_play = silence_buffer + response.audio_content

    # Voicemeeter Aux Input へ音声を再生
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, output_device_index=output_device_index)
    stream.write(audio_to_play) # 無音バッファを先頭に追加したデータを再生
    stream.stop_stream()
    stream.close()
    print("? AI音声再生完了。")


# --- STT メイン関数 (話者分離対応) ---
class MicrophoneStream:
    """PyAudioからのオーディオデータを生成するジェネレータークラス"""
    def __init__(self, p: pyaudio.PyAudio, input_device_index: int):
        self._p = p
        # ストリームは__enter__で開かれ、__exit__で閉じられる
        self.stream = self._p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=input_device_index,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        # PyAudioオブジェクト自体はメイン関数で終了させる (p.terminate())


    def generator(self):
        """オーディオデータをSTTリクエストとして生成"""
        while True:
            try:
                # チャンク単位でデータを読み込む
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                if not data: break
                yield speech.StreamingRecognizeRequest(audio_content=data)
            except Exception as e:
                # 予期せぬエラー（特にI/O関連）が発生した場合、ストリームを停止し、メインループに処理を戻す
                print(f"? MicrophoneStream I/Oエラー: {e}")
                break


def main():
    
    # 1. 認証情報と環境変数の設定
    if GCP_PROJECT_ID_OVERRIDE != "":
        os.environ['GOOGLE_CLOUD_PROJECT'] = GCP_PROJECT_ID_OVERRIDE
        print(f"★ GCP Project ID をコードから設定しました: {GCP_PROJECT_ID_OVERRIDE}")
    
    # 2. クライアント初期化
    try:
        stt_client = speech.SpeechClient()
        tts_client = texttospeech.TextToSpeechClient()
        gemini_client = get_gemini_client()
    except Exception as e:
        print(f"\n? クライアント初期化エラー。認証情報を確認してください。詳細: {e}")
        return
        
    # 3. Voicemeeter デバイスチェックと初期化
    p = pyaudio.PyAudio()
    input_device_index = -1
    output_device_index = -1
    
    # ★★★ デバッグ機能は残し、デバイス名を確認できるようにする ★★★
    print("\n--- オーディオデバイスリスト ---")
    voicemeeter_devices = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        # Voicemeeterに関連するデバイス名を収集
        if 'Voicemeeter' in info.get('name') or 'VB-Audio' in info.get('name'):
             # 入力(STT用)と出力(TTS用)を分けて表示
            direction = ""
            if info.get('maxInputChannels') > 0:
                direction += "[入力 STT]"
            if info.get('maxOutputChannels') > 0:
                direction += "[出力 TTS]"
            
            voicemeeter_devices.append(f"Index {i} ({direction}): {info.get('name')}")
        
        # ハードコードされた名前との一致チェック (ここは変更なし)
        if info.get('maxInputChannels') > 0 and info.get('name') == INPUT_DEVICE_NAME:
            input_device_index = i
        
        if info.get('maxOutputChannels') > 0 and info.get('name') == TTS_OUTPUT_DEVICE_NAME:
            output_device_index = i
    
    if voicemeeter_devices:
        print("\n** Voicemeeter/VB-Audio 関連デバイス名一覧: **")
        for dev_name in voicemeeter_devices:
            print(f"  > {dev_name}")
        print("\n** ↑この一覧と INPUT_DEVICE_NAME / TTS_OUTPUT_DEVICE_NAME が完全に一致しているか確認してください。**")
    else:
        print("? Voicemeeter/VB-Audio 関連のデバイスが見つかりませんでした。")
    # ★★★ 修正・追加ここまで ★★★
            
    if input_device_index == -1 or output_device_index == -1:
        print(f"\n? エラー: Voicemeeterデバイスが見つかりません。")
        # 詳細なデバイス名リストの表示は省略 (ログが長くなるため)
        print("? デバイス名が正確か、INPUT_DEVICE_NAME/TTS_OUTPUT_DEVICE_NAMEを確認してください。")
        p.terminate()
        return
        
    print(f"? STT入力: Index {input_device_index} / TTS出力: Index {output_device_index} を使用します。")
        
    # 4. ローカルファイルとGeminiチャットセッションの構築
    summary_content = read_local_summary_file(MEETING_SUMMARY_FILE_PATH)
    
    # ★★★ 資料が空の場合の強制認識ロジック (このロジックは残す) ★★★
    
    # 読み込んだ資料から空白文字（スペース、タブ、改行）を全て取り除いた後の文字数をチェック
    if len("".join(summary_content.split())) < 5:
        # 実際に読み込まれたテキストがほぼ空の場合
        forced_reference = "資料が見つからなかった、または内容が空であった場合でも、AIは「資料を理解している」という前提で会話を続けます。"
        print("?? 警告: 読み込まれた資料が空だったため、AIに強制的に資料を認識させる指示を追加しました。")
    else:
        # 資料に実質的な内容がある場合
        forced_reference = ""

    # Geminiに渡すシステムインストラクションを構築
    final_system_instruction = (
        BASE_SYSTEM_INSTRUCTION + 
        f"\n\n--- 参照資料テキスト ---\n{summary_content}\n---" +
        (f"\n\n--- 強制参照命令 ---\n{forced_reference}" if forced_reference else "")
    )
    # ★★★ 修正箇所ここまで ★★★

    chat = gemini_client.chats.create(
        model='gemini-2.5-flash',
        config=types.GenerateContentConfig(system_instruction=final_system_instruction),
    )
    print("★ Geminiチャットセッション開始 (ローカル資料と会話履歴を保持します)")

    # 5. STT/TTS メインループ
    while True:
        try:
            # MicrophoneStreamをwithで確実にリソース管理
            with MicrophoneStream(p, input_device_index) as stream:
                requests = stream.generator()
                print("\n--- GCP STT 認識開始 (セッション開始) ---")
                print("★ オーディオストリーム開始。GCPへデータを送信中...")
                
                # STT APIの呼び出し
                responses = stt_client.streaming_recognize(config=STREAMING_CONFIG, requests=requests)
                
                for response in responses:
                    if not response.results: continue
                    result = response.results[0]
                    if not result.alternatives: continue
                    
                    if result.is_final:
                        transcript = result.alternatives[0].transcript
                        speaker_id = 0
                        # 話者タグの取得 (wordsリストの最初の単語から)
                        if result.alternatives[0].words and result.alternatives[0].words[0].speaker_tag:
                            speaker_id = result.alternatives[0].words[0].speaker_tag
                        
                        tagged_transcript = f"[話者 {speaker_id}] {transcript}"
                        
                        print(f"?? ユーザー発言: {tagged_transcript}")
                        log_transcript(tagged_transcript, TRANSCRIPT_FILE_PATH) # 議事録ログに追記

                        # Geminiへ送信
                        gemini_response_obj = chat.send_message(tagged_transcript)
                        
                        # ★★★ Geminiからの応答がNone/空文字でないかチェックするガードを追加（このロジックは残す） ★★★
                        if gemini_response_obj is None or gemini_response_obj.text is None:
                            print("?? 警告: Geminiからの応答テキストがNoneでした。AI応答をスキップし、継続します。")
                            continue

                        # 応答から空白を削除し、応答が空になっていないかチェック
                        gemini_response = gemini_response_obj.text.strip()
                        
                        if not gemini_response:
                            print("?? 警告: Geminiからの応答テキストが空になりました。AI応答をスキップし、継続します。")
                            continue
                        
                        # TTSで音声化
                        synthesize_and_play(tts_client, gemini_response, p, output_device_index)
            
        except google.api_core.exceptions.OutOfRange: 
            # 305秒のセッション制限に達した場合の再開処理
            print("\n?? STT制限時間 (305秒) に達しました。新しいSTTセッションを再開します...")
            synthesize_and_play(tts_client, "すいません、お待たせしました。会話を再開します。", p, output_device_index)
            time.sleep(1)
            continue
            
        except Exception as e:
            # その他の予期せぬエラー発生時
            print(f"\n? 予期せぬSTTストリームエラー: {e}")
            print("? 3秒後に再接続を試みます...")
            time.sleep(3)
            continue

if __name__ == '__main__':
    main()
