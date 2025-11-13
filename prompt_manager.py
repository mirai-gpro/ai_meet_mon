# -*- coding: utf-8 -*-
"""
PromptManager - プロンプト管理システム
GCS上のプロンプトファイルを読み込み、キャッシュする
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PromptManager:
    """プロンプト管理クラス"""

    def __init__(self, cache_minutes: int = 10):
        """
        初期化

        Args:
            cache_minutes: キャッシュの有効期限（分）
        """
        self.prompts: Dict[str, str] = {}
        self.last_loaded: Optional[datetime] = None
        self.cache_minutes = cache_minutes
        self.bucket_name = os.getenv("PROMPTS_BUCKET_NAME")

        # デフォルトプロンプト
        self.default_prompts = {
            "chat_system": """あなたはHP作成サポートアシスタントです。
ユーザーからの修正依頼に対して、適切な提案と修正を行います。

以下の形式でJSON形式で返答してください:
{
  "action": "immediate" | "batch" | "question",
  "response": "ユーザーへの返答メッセージ",
  "modification": {
    "type": "text" | "style" | "structure",
    "target": {"selector": "...", "text": "..."},
    "changes": {"property": "value", ...},
    "description": "修正内容の説明"
  }
}

- action: "immediate" = 即座に適用, "batch" = バッチ処理, "question" = 確認が必要
- modification: action が "immediate" の場合のみ必須
""",

            "fix_instructions": """以下の会話ログから、修正指示書を生成してください。

## 基本情報
- 生成日時: {timestamp}
- セッションID: {session_id}

## 会話ログ
{conversation_text}

上記の内容を分析し、以下の形式で修正指示書を生成してください:

# 修正指示書

## 概要
[プロジェクトの概要を簡潔に記載]

## 修正項目
[各修正項目を箇条書きで記載]

### 1. [修正項目名]
- 対象: [修正対象の要素]
- 内容: [修正内容の詳細]
- 理由: [修正の理由]

## 備考
[その他の注意事項]
""",

            "selection_analysis": """ユーザーが以下の要素を選択しました:

種類: {selection_type}
内容: {selection_content}

ユーザーコメント: {user_comment}

この選択に対して、どのような修正を希望しているか質問してください。
"""
        }

        logger.info(f"PromptManager initialized (cache: {cache_minutes}min)")

    def _load_from_gcs(self) -> bool:
        """GCSからプロンプトを読み込む"""
        if not self.bucket_name:
            logger.info("No GCS bucket configured, using default prompts")
            return False

        try:
            from google.cloud import storage

            storage_client = storage.Client()
            bucket = storage_client.bucket(self.bucket_name)

            # 読み込むプロンプトファイル一覧
            prompt_files = [
                "chat_system.txt",
                "fix_instructions.txt",
                "selection_analysis.txt"
            ]

            loaded_count = 0
            for filename in prompt_files:
                blob = bucket.blob(f"prompts/{filename}")
                if blob.exists():
                    prompt_name = filename.replace(".txt", "")
                    content = blob.download_as_text(encoding='utf-8')
                    self.prompts[prompt_name] = content
                    loaded_count += 1
                    logger.info(f"Loaded prompt from GCS: {prompt_name}")

            if loaded_count > 0:
                self.last_loaded = datetime.now()
                logger.info(f"Loaded {loaded_count} prompts from GCS")
                return True
            else:
                logger.warning("No prompts found in GCS bucket")
                return False

        except Exception as e:
            logger.error(f"Failed to load prompts from GCS: {e}")
            return False

    def _is_cache_valid(self) -> bool:
        """キャッシュが有効かチェック"""
        if not self.last_loaded:
            return False

        cache_expiry = self.last_loaded + timedelta(minutes=self.cache_minutes)
        return datetime.now() < cache_expiry

    def reload(self) -> Dict[str, any]:
        """プロンプトを強制再読み込み"""
        self.prompts = {}
        self.last_loaded = None

        success = self._load_from_gcs()

        return {
            "loaded_from_gcs": success,
            "prompts_count": len(self.prompts),
            "using_defaults": len(self.prompts) == 0,
            "timestamp": datetime.now().isoformat()
        }

    def get(self, prompt_name: str, **kwargs) -> str:
        """
        プロンプトを取得

        Args:
            prompt_name: プロンプト名
            **kwargs: プロンプト内の変数置換用のパラメータ

        Returns:
            プロンプト文字列
        """
        # キャッシュが無効な場合は再読み込み
        if not self._is_cache_valid():
            self._load_from_gcs()

        # GCSから読み込めなかった場合はデフォルトを使用
        if prompt_name not in self.prompts:
            if prompt_name in self.default_prompts:
                logger.debug(f"Using default prompt: {prompt_name}")
                prompt = self.default_prompts[prompt_name]
            else:
                logger.warning(f"Prompt not found: {prompt_name}")
                return f"[Prompt '{prompt_name}' not found]"
        else:
            prompt = self.prompts[prompt_name]

        # 変数置換
        if kwargs:
            try:
                prompt = prompt.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing variable in prompt '{prompt_name}': {e}")

        return prompt

    def list_prompts(self) -> Dict[str, int]:
        """現在読み込まれているプロンプトの一覧を返す"""
        return {
            name: len(content)
            for name, content in self.prompts.items()
        }
