# app.py
from flask import Flask, render_template, jsonify
import time
import markdown
from pathlib import Path
import google.generativeai as genai

# ---------------------------------------------
# Gemini設定
# ---------------------------------------------
GEMINI_API_KEY_OVERRIDE = "AIzaSyDQjSNbVj781K5OhYsFiM86rpSGU-37l8o"
GCP_PROJECT_ID_OVERRIDE = "ai-meet-473716"

genai.configure(api_key=GEMINI_API_KEY_OVERRIDE)

# ---------------------------------------------
# Flaskアプリ初期化
# ---------------------------------------------
app = Flask(__name__)

# ---------------------------------------------
# 議事録生成関数（app.py内で完結）
# ---------------------------------------------
def generate_meeting_transcript():
    """
    meeting_transcript_log.md を読み込み、
    Geminiで半分の長さに要約した議事録を返す
    """
    md_path = Path("meeting_transcript_log.md")
    if not md_path.exists():
        return "# 議事録ファイルが見つかりません。"

    # 読み込み
    raw_text = md_path.read_text(encoding="utf-8")

    # Geminiで要約（約50％）
    prompt = f"""
以下は会議の議事録全文です。全体の約50%の長さに要約し、
重要な議題、決定事項、今後のアクションを残してください。
出力はMarkdown形式でお願いします。

---
{raw_text}
---
"""
    model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")
    response = model.generate_content(prompt)

    summarized = response.text if hasattr(response, "text") else "要約に失敗しました。"
    return summarized

# ---------------------------------------------
# ルート：HTML表示
# ---------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# ---------------------------------------------
# API：議事録生成（Flask起動直後に呼ばれる）
# ---------------------------------------------
@app.route("/generate", methods=["GET"])
def generate():
    print("[INFO] Geminiによる議事録生成を開始...")
    time.sleep(1)
    summary_md = generate_meeting_transcript()
    html_content = markdown.markdown(summary_md)
    print("[INFO] Gemini要約完了。HTMLに変換済。")
    return jsonify({"summary": html_content})

# ---------------------------------------------
# メイン
# ---------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
