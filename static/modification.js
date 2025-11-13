/**
 * ModificationManager - HTML修正管理システム
 * iframeプレビュー内のHTML要素の修正を管理する
 */

class ModificationManager {
    constructor() {
        this.modifications = [];
        this.sessionId = null;
        console.log('[ModificationManager] 初期化完了');
    }

    /**
     * セッションIDを設定
     */
    setSessionId(sessionId) {
        this.sessionId = sessionId;
        console.log('[ModificationManager] SessionID設定:', sessionId);
    }

    /**
     * 選択をクリア
     */
    clearSelection() {
        console.log('[ModificationManager] Selection cleared');
    }

    /**
     * 修正履歴を取得
     */
    getModifications() {
        return this.modifications;
    }

    /**
     * JSON形式の修正指示を適用
     */
    applyModificationFromJSON(modification) {
        console.log('[ModificationManager] Applying modification:', modification);

        this.modifications.push({
            timestamp: new Date().toISOString(),
            type: modification.type || 'unknown',
            target: modification.target || {},
            changes: modification.changes || {},
            description: modification.description || ''
        });

        console.log('[ModificationManager] Total modifications:', this.modifications.length);
    }

    /**
     * 修正指示書を生成
     */
    generateInstructionDocument() {
        if (this.modifications.length === 0) {
            return '# 修正指示書\n\n修正履歴がありません。';
        }

        let doc = '# 修正指示書\n\n';
        doc += `## セッション情報\n`;
        doc += `- セッションID: ${this.sessionId || 'N/A'}\n`;
        doc += `- 生成日時: ${new Date().toISOString()}\n`;
        doc += `- 修正件数: ${this.modifications.length}\n\n`;

        doc += `## 修正内容\n\n`;

        this.modifications.forEach((mod, index) => {
            doc += `### ${index + 1}. ${mod.description || '修正項目'}\n\n`;
            doc += `- **日時**: ${mod.timestamp}\n`;
            doc += `- **種類**: ${mod.type}\n`;

            if (mod.target && Object.keys(mod.target).length > 0) {
                doc += `- **対象要素**: ${JSON.stringify(mod.target, null, 2)}\n`;
            }

            if (mod.changes && Object.keys(mod.changes).length > 0) {
                doc += `- **変更内容**: ${JSON.stringify(mod.changes, null, 2)}\n`;
            }

            doc += `\n`;
        });

        return doc;
    }
}

// グローバルインスタンスを作成
window.modificationManager = new ModificationManager();
console.log('[ModificationManager] グローバルインスタンス作成完了');
