/**
 * ModificationManager - HTML修正管理システム
 * iframeプレビュー内のHTML要素の修正を管理する
 */

class ModificationManager {
    constructor() {
        this.modifications = [];
        this.sessionId = null;
        this.undoStack = []; // undo用のスタック
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
        console.log('[ModificationManager] 選択クリア');
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
        console.log('[ModificationManager] ========== JSON修正開始 ==========');
        console.log('[ModificationManager] selector:', modification.selector);
        console.log('[ModificationManager] type:', modification.type);
        console.log('[ModificationManager] newValue:', modification.newValue);
        console.log('[ModificationManager] deleteText:', modification.deleteText);

        try {
            // undo処理
            if (modification.type === 'undo') {
                return this.performUndo();
            }

            // iframeの取得
            const iframe = document.getElementById('hp-preview');
            if (!iframe) {
                console.error('[ModificationManager] ❌ iframe要素が見つかりません');
                return { success: false, error: 'iframe not found' };
            }
            console.log('[ModificationManager] ✅ iframe要素取得成功');

            // iframeのdocument取得
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            if (!iframeDoc) {
                console.error('[ModificationManager] ❌ iframe documentが取得できません');
                return { success: false, error: 'iframe document not accessible' };
            }
            console.log('[ModificationManager] ✅ iframe document取得成功');

            // 要素の検索
            console.log('[ModificationManager] セレクタで要素検索:', modification.selector);

            if (!modification.selector || modification.selector.trim() === '') {
                console.error('[ModificationManager] ❌ セレクタが空です');
                return { success: false, error: 'Empty selector' };
            }

            const element = iframeDoc.querySelector(modification.selector);
            if (!element) {
                console.error('[ModificationManager] ❌ 要素が見つかりません:', modification.selector);
                return { success: false, error: 'Element not found' };
            }
            console.log('[ModificationManager] ✅ 要素発見:', element.tagName, element.className);
            console.log('[ModificationManager] 要素の現在のテキスト:', element.textContent.trim());

            // 修正前の状態を保存（undo用）
            const beforeState = {
                selector: modification.selector,
                html: element.outerHTML,
                styles: {},
                parent: element.parentElement,
                nextSibling: element.nextSibling
            };
            console.log('[ModificationManager] 修正前のHTML保存完了');

            // 修正の種類に応じて処理
            let result = { success: false };

            switch (modification.type) {
                case 'fontSize':
                    result = this.applyFontSizeChange(element, modification.newValue, beforeState);
                    break;

                case 'color':
                    result = this.applyColorChange(element, modification.newValue, beforeState);
                    break;

                case 'backgroundColor':
                    result = this.applyBackgroundColorChange(element, modification.newValue, beforeState);
                    break;

                case 'text':
                    result = this.applyTextChange(element, modification.newValue, modification.oldValue, beforeState);
                    break;

                case 'delete':
                    result = this.applyDelete(element, modification.deleteText, beforeState);
                    break;

                case 'insert':
                    result = this.applyInsert(element, modification.newValue, modification.position, beforeState);
                    break;

                case 'style':
                    result = this.applyStyleChange(element, modification.property, modification.newValue, beforeState);
                    break;

                default:
                    console.error('[ModificationManager] ❌ 不明な修正タイプ:', modification.type);
                    return { success: false, error: 'Unknown modification type' };
            }

            if (result.success) {
                // undo stackに保存
                this.undoStack.push(beforeState);

                // 修正履歴に記録
                this.modifications.push({
                    timestamp: new Date().toISOString(),
                    type: modification.type,
                    selector: modification.selector,
                    target: modification.target || {},
                    changes: modification.changes || {},
                    description: modification.description || `${modification.type}を適用`,
                    beforeState: beforeState
                });
                console.log('[ModificationManager] 修正を記録:', this.modifications[this.modifications.length - 1]);
            }

            console.log('[ModificationManager] JSON修正適用完了');
            return result;

        } catch (error) {
            console.error('[ModificationManager] ❌ エラー発生:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * フォントサイズ変更
     */
    applyFontSizeChange(element, newValue, beforeState) {
        const currentSize = window.getComputedStyle(element).fontSize;
        beforeState.styles.fontSize = currentSize;

        console.log('[ModificationManager] フォントサイズ変更 BEFORE:', currentSize);

        element.style.fontSize = newValue;
        console.log('[ModificationManager] フォントサイズ変更 AFTER:', newValue);
        console.log('[ModificationManager] ✅ 変更:', currentSize, '→', newValue);

        return { success: true, before: currentSize, after: newValue };
    }

    /**
     * 色変更
     */
    applyColorChange(element, newValue, beforeState) {
        const currentColor = window.getComputedStyle(element).color;
        beforeState.styles.color = currentColor;

        console.log('[ModificationManager] 色変更 BEFORE:', currentColor);
        element.style.color = newValue;
        console.log('[ModificationManager] 色変更 AFTER:', newValue);
        console.log('[ModificationManager] ✅ 変更:', currentColor, '→', newValue);

        return { success: true, before: currentColor, after: newValue };
    }

    /**
     * 背景色変更
     */
    applyBackgroundColorChange(element, newValue, beforeState) {
        const currentBgColor = window.getComputedStyle(element).backgroundColor;
        beforeState.styles.backgroundColor = currentBgColor;

        console.log('[ModificationManager] 背景色変更 BEFORE:', currentBgColor);
        element.style.backgroundColor = newValue;
        console.log('[ModificationManager] 背景色変更 AFTER:', newValue);
        console.log('[ModificationManager] ✅ 変更:', currentBgColor, '→', newValue);

        return { success: true, before: currentBgColor, after: newValue };
    }

    /**
     * テキスト変更
     */
    applyTextChange(element, newValue, oldValue, beforeState) {
        const currentText = element.textContent;
        console.log('[ModificationManager] テキスト変更 BEFORE:', currentText);

        if (oldValue) {
            // 部分置換
            element.textContent = currentText.replace(oldValue, newValue);
        } else {
            // 全体置換
            element.textContent = newValue;
        }

        console.log('[ModificationManager] テキスト変更 AFTER:', element.textContent);
        console.log('[ModificationManager] ✅ 変更完了');

        return { success: true, before: currentText, after: element.textContent };
    }

    /**
     * テキスト削除
     */
    applyDelete(element, deleteText, beforeState) {
        const currentText = element.textContent;
        console.log('[ModificationManager] テキスト部分削除:', deleteText);

        if (deleteText) {
            // 特定のテキストを削除
            const newText = currentText.replace(deleteText, '');
            element.textContent = newText;
            console.log('[ModificationManager] ✅ 削除完了:', currentText, '→', newText);
            return { success: true, before: currentText, after: newText };
        } else {
            // 要素全体を削除
            element.remove();
            console.log('[ModificationManager] ✅ 要素削除完了');
            return { success: true, deleted: true };
        }
    }

    /**
     * テキスト挿入
     */
    applyInsert(element, newValue, position, beforeState) {
        console.log('[ModificationManager] テキスト挿入:', newValue, 'at', position);

        if (position === 'before') {
            element.insertAdjacentHTML('beforebegin', newValue);
        } else if (position === 'after') {
            element.insertAdjacentHTML('afterend', newValue);
        } else if (position === 'prepend') {
            element.insertAdjacentHTML('afterbegin', newValue);
        } else if (position === 'append') {
            element.insertAdjacentHTML('beforeend', newValue);
        } else {
            // デフォルトはappend
            element.insertAdjacentHTML('beforeend', newValue);
        }

        console.log('[ModificationManager] ✅ 挿入完了');
        return { success: true };
    }

    /**
     * スタイル変更（汎用）
     */
    applyStyleChange(element, property, newValue, beforeState) {
        const currentValue = window.getComputedStyle(element)[property];
        beforeState.styles[property] = currentValue;

        console.log(`[ModificationManager] スタイル変更 ${property} BEFORE:`, currentValue);
        element.style[property] = newValue;
        console.log(`[ModificationManager] スタイル変更 ${property} AFTER:`, newValue);
        console.log('[ModificationManager] ✅ 変更:', currentValue, '→', newValue);

        return { success: true, before: currentValue, after: newValue };
    }

    /**
     * Undo実行
     */
    performUndo() {
        console.log('[ModificationManager] ========== UNDO実行 ==========');

        if (this.undoStack.length === 0) {
            console.warn('[ModificationManager] ⚠️ Undoスタックが空です');
            return { success: false, error: 'Nothing to undo' };
        }

        const lastState = this.undoStack.pop();
        console.log('[ModificationManager] 復元する状態:', lastState);

        try {
            const iframe = document.getElementById('hp-preview');
            if (!iframe) {
                console.error('[ModificationManager] ❌ iframe要素が見つかりません');
                return { success: false, error: 'iframe not found' };
            }

            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            if (!iframeDoc) {
                console.error('[ModificationManager] ❌ iframe documentが取得できません');
                return { success: false, error: 'iframe document not accessible' };
            }

            // 現在の要素を取得
            const currentElement = iframeDoc.querySelector(lastState.selector);

            if (currentElement) {
                // 要素が存在する場合は置き換え
                const tempDiv = iframeDoc.createElement('div');
                tempDiv.innerHTML = lastState.html;
                const restoredElement = tempDiv.firstChild;

                if (restoredElement) {
                    currentElement.parentNode.replaceChild(restoredElement, currentElement);
                    console.log('[ModificationManager] ✅ 要素を復元しました');
                } else {
                    console.error('[ModificationManager] ❌ 復元用の要素を作成できません');
                    return { success: false, error: 'Failed to create restored element' };
                }
            } else {
                // 要素が削除されている場合は再挿入
                if (lastState.parent) {
                    const tempDiv = iframeDoc.createElement('div');
                    tempDiv.innerHTML = lastState.html;
                    const restoredElement = tempDiv.firstChild;

                    if (restoredElement) {
                        if (lastState.nextSibling) {
                            lastState.parent.insertBefore(restoredElement, lastState.nextSibling);
                        } else {
                            lastState.parent.appendChild(restoredElement);
                        }
                        console.log('[ModificationManager] ✅ 削除された要素を復元しました');
                    }
                }
            }

            // 修正履歴から最後のエントリを削除
            if (this.modifications.length > 0) {
                const removed = this.modifications.pop();
                console.log('[ModificationManager] 修正履歴から削除:', removed);
            }

            console.log('[ModificationManager] ========== UNDO完了 ==========');
            return { success: true };

        } catch (error) {
            console.error('[ModificationManager] ❌ Undo中にエラー:', error);
            // エラーが発生した場合はスタックに戻す
            this.undoStack.push(lastState);
            return { success: false, error: error.message };
        }
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
            doc += `- **セレクタ**: ${mod.selector}\n`;

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
