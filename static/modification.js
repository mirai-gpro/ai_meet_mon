/**
 * 修正機能管理クラス（完全修正版）
 */
class ModificationManager {
    constructor() {
        this.modifications = [];
        this.selectedElement = null;
        this.selectedText = null;
        this.sessionId = null;
        this.iframeElement = null;
        console.log('[ModificationManager] 初期化完了');
    }

    setSessionId(sessionId) {
        this.sessionId = sessionId;
        console.log('[ModificationManager] SessionID設定:', sessionId);
    }

    classifyModification(userInput) {
        const immediatePatterns = [
            /(\d+)%(大きく|小さく)/,
            /もっと(大きく|小さく)/,
            /もう少し(大きく|小さく|長く|短く)/,
            /(大きく|小さく|短く)して/,
            /要約して/,
            /色を(変えて|変更して)/,
            /削除して/,
            /消して/,
            /取り除いて/
        ];

        const isImmediate = immediatePatterns.some(p => p.test(userInput));
        console.log('[ModificationManager] 修正タイプ判定:', isImmediate ? 'immediate' : 'batch', userInput);
        return isImmediate ? 'immediate' : 'batch';
    }

    // ★★★ 新規追加: JSON形式の修正指示を処理 ★★★
    applyModificationFromJSON(modificationObj) {
        console.log('[ModificationManager] ========== JSON修正開始 ==========');
        console.log('[ModificationManager] selector:', modificationObj.selector);
        console.log('[ModificationManager] type:', modificationObj.type);
        console.log('[ModificationManager] newValue:', modificationObj.newValue);
        console.log('[ModificationManager] deleteText:', modificationObj.deleteText);

        const iframe = document.getElementById('hp-preview');
        if (!iframe) {
            console.error('[ModificationManager] ❌ iframeが見つかりません');
            return { success: false, message: 'プレビューが見つかりません' };
        }
        console.log('[ModificationManager] ✅ iframe要素取得成功');

        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
        if (!iframeDoc) {
            console.error('[ModificationManager] ❌ iframe documentにアクセスできません');
            return { success: false, message: 'プレビューにアクセスできません' };
        }
        console.log('[ModificationManager] ✅ iframe document取得成功');

        // undo処理の場合は特別処理
        if (modificationObj.type === 'undo') {
            console.log('[ModificationManager] Undo操作開始');
            return this.undoLastModification();
        }

        // セレクタのバリデーション
        if (!modificationObj.selector || modificationObj.selector.trim() === '') {
            console.error('[ModificationManager] ❌ セレクタが空です');
            return { success: false, message: 'セレクタが空です' };
        }

        console.log('[ModificationManager] セレクタで要素検索:', modificationObj.selector);
        const element = iframeDoc.querySelector(modificationObj.selector);
        if (!element) {
            console.error('[ModificationManager] ❌ 要素が見つかりません:', modificationObj.selector);
            return { success: false, message: '要素が見つかりません: ' + modificationObj.selector };
        }
        console.log('[ModificationManager] ✅ 要素発見:', element.tagName, element.className);
        console.log('[ModificationManager] 要素の現在のテキスト:', element.textContent?.substring(0, 100));

        // 修正前のHTMLを保存
        const originalHtml = element.outerHTML;
        console.log('[ModificationManager] 修正前のHTML保存完了');

        try {
            switch(modificationObj.type) {
                case 'text':
                    console.log('[ModificationManager] テキスト変更 BEFORE:', element.textContent);
                    element.textContent = modificationObj.newValue;
                    console.log('[ModificationManager] テキスト変更 AFTER:', element.textContent);
                    break;

                case 'color':
                    console.log('[ModificationManager] 色変更:', modificationObj.newValue);
                    element.style.color = modificationObj.newValue;
                    console.log('[ModificationManager] ✅ 色変更完了:', element.style.color);
                    break;

                case 'background':
                    console.log('[ModificationManager] 背景色変更:', modificationObj.newValue);
                    element.style.backgroundColor = modificationObj.newValue;
                    console.log('[ModificationManager] ✅ 背景色変更完了');
                    break;

                case 'fontSize':
                    const beforeSize = window.getComputedStyle(element).fontSize;
                    console.log('[ModificationManager] フォントサイズ変更 BEFORE:', beforeSize);
                    element.style.fontSize = modificationObj.newValue;
                    const afterSize = window.getComputedStyle(element).fontSize;
                    console.log('[ModificationManager] フォントサイズ変更 AFTER:', afterSize);
                    console.log('[ModificationManager] ✅ 変更:', beforeSize, '→', afterSize);
                    break;

                case 'style':
                    if (modificationObj.styles) {
                        Object.entries(modificationObj.styles).forEach(([prop, value]) => {
                            element.style[prop] = value;
                        });
                    }
                    break;

                case 'attribute':
                    element.setAttribute(modificationObj.attribute, modificationObj.newValue);
                    break;

                case 'delete':
                    // deleteTextが指定されている場合は、テキストの一部のみ削除
                    if (modificationObj.deleteText) {
                        const currentText = element.textContent;
                        const newText = currentText.replace(modificationObj.deleteText, '');
                        element.textContent = newText.trim();
                        console.log('[ModificationManager] テキスト部分削除:', modificationObj.deleteText);
                    } else {
                        // 要素全体を削除（フェードアウトアニメーション付き）
                        element.style.transition = 'opacity 0.3s';
                        element.style.opacity = '0';
                        setTimeout(() => {
                            if (element.parentNode) {
                                element.parentNode.removeChild(element);
                            }
                        }, 300);
                        console.log('[ModificationManager] 要素全体削除');
                    }
                    break;

                default:
                    console.error('[ModificationManager] 未対応の修正タイプ:', modificationObj.type);
                    return { success: false, message: '未対応の修正タイプです' };
            }

            // 修正を記録（修正前と修正後のHTMLを保存）
            this.recordModification({
                type: 'immediate',
                userInput: modificationObj.description,
                elementSelector: modificationObj.selector,
                selectedText: this.selectedText,
                originalHtml: originalHtml,  // 修正前
                modifiedHtml: element.outerHTML,  // 修正後
                modificationType: modificationObj.type,
                status: 'applied'
            });

            console.log('[ModificationManager] JSON修正適用完了');
            return { success: true, message: '修正を適用しました' };

        } catch (error) {
            console.error('[ModificationManager] JSON修正適用エラー:', error);
            return { success: false, message: `修正の適用に失敗: ${error.message}` };
        }
    }

    applyImmediateModification(userInput) {
        console.log('[ModificationManager] 即時修正開始:', userInput);
        console.log('[ModificationManager] iframeElement:', this.iframeElement);
        console.log('[ModificationManager] selectedText:', this.selectedText);

        if (!this.iframeElement) {
            console.error('[ModificationManager] iframe要素が選択されていません');
            return { success: false, message: '要素が選択されていません' };
        }

        try {
            const element = this.iframeElement;
            const originalHtml = element.outerHTML;
            let modifiedHtml = originalHtml;
            let modificationType = '';
            let message = '';

            // パーセンテージでのサイズ変更
            const percentMatch = userInput.match(/(\d+)%(大きく|小さく)/);
            if (percentMatch) {
                const percent = parseInt(percentMatch[1]);
                const direction = percentMatch[2];
                const factor = direction === '大きく' ? (1 + percent / 100) : (1 - percent / 100);

                if (element.tagName === 'IMG') {
                    modifiedHtml = this.adjustImageSize(element, factor);
                } else {
                    modifiedHtml = this.adjustTextSize(element, factor);
                }
                modificationType = 'size';
                message = `文字サイズを${percent}%${direction}しました`;
            }
            // 通常のサイズ変更
            else if (userInput.includes('大きく') || userInput.includes('小さく')) {
                const factor = userInput.includes('大きく') ? 1.2 : 0.8;

                if (element.tagName === 'IMG') {
                    modifiedHtml = this.adjustImageSize(element, factor);
                } else {
                    modifiedHtml = this.adjustTextSize(element, factor);
                }
                modificationType = 'size';
                message = `サイズを変更しました`;
            }
            // 削除処理
            else if (userInput.includes('削除して') || userInput.includes('消して') ||
                     userInput.includes('取り除いて')) {
                this.removeElement(element);
                modificationType = 'delete';
                modifiedHtml = '<!-- 削除されました -->';
                message = `「${this.selectedText.substring(0, 30)}...」を削除しました`;
            }
            // 要約
            else if (userInput.includes('短く') || userInput.includes('要約')) {
                return this.handleSummarization(element, userInput, originalHtml);
            }

            // 修正を記録
            this.recordModification({
                type: 'immediate',
                userInput,
                elementSelector: this.getElementSelector(),
                selectedText: this.selectedText,
                originalHtml,
                modifiedHtml,
                modificationType,
                status: 'applied'
            });

            console.log('[ModificationManager] 即時修正完了:', message);
            return { success: true, message: message || '修正を適用しました' };
        } catch (error) {
            console.error('[ModificationManager] 修正適用エラー:', error);
            return { success: false, message: `修正の適用に失敗: ${error.message}` };
        }
    }

    adjustImageSize(element, factor) {
        const currentWidth = element.width || element.offsetWidth;
        const currentHeight = element.height || element.offsetHeight;

        element.style.width = `${currentWidth * factor}px`;
        element.style.height = `${currentHeight * factor}px`;

        console.log('[ModificationManager] 画像サイズ変更:', { currentWidth, currentHeight, factor });
        return element.outerHTML;
    }

    adjustTextSize(element, factor) {
        const iframe = document.getElementById('hp-preview');
        const iframeDoc = iframe.contentWindow.document;
        const computedStyle = iframe.contentWindow.getComputedStyle(element);
        const currentSize = parseFloat(computedStyle.fontSize);
        const newSize = currentSize * factor;

        element.style.fontSize = `${newSize}px`;

        console.log('[ModificationManager] テキストサイズ変更:', { currentSize, newSize, factor });
        return element.outerHTML;
    }

    removeElement(element) {
        console.log('[ModificationManager] 要素削除:', element.tagName, element.textContent?.substring(0, 50));

        element.style.transition = 'opacity 0.3s';
        element.style.opacity = '0';

        setTimeout(() => {
            const parent = element.parentNode;
            if (parent) {
                parent.removeChild(element);
                console.log('[ModificationManager] 要素削除完了');
            }
        }, 300);
    }

    async handleSummarization(element, userInput, originalHtml) {
        if (!this.sessionId) {
            return { success: false, message: 'セッションが開始されていません' };
        }

        try {
            const response = await fetch('/api/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: element.textContent,
                    session_id: this.sessionId
                })
            });

            if (!response.ok) {
                throw new Error('要約に失敗しました');
            }

            const data = await response.json();
            const summary = data.summary || element.textContent;

            element.textContent = summary;

            this.recordModification({
                type: 'immediate',
                userInput,
                elementSelector: this.getElementSelector(),
                selectedText: this.selectedText,
                originalHtml,
                modifiedHtml: element.outerHTML,
                modificationType: 'summarize',
                status: 'applied'
            });

            return { success: true, message: '要約を適用しました' };
        } catch (error) {
            console.error('[ModificationManager] 要約エラー:', error);
            return { success: false, message: '要約に失敗しました' };
        }
    }

    recordBatchModification(userInput) {
        this.recordModification({
            type: 'batch',
            userInput: userInput,
            description: userInput,
            selectedText: this.selectedText,
            elementSelector: this.getElementSelector(),
            status: 'pending'
        });
    }

    getElementSelector() {
        const element = this.iframeElement || this.selectedElement;
        if (!element) return 'unknown';

        let selector = element.tagName?.toLowerCase() || 'unknown';

        if (element.id) {
            selector += `#${element.id}`;
        } else if (element.className && typeof element.className === 'string') {
            const classes = element.className.trim().replace(/\s+/g, '.');
            if (classes) {
                selector += `.${classes}`;
            }
        }

        return selector;
    }

    recordModification(modification) {
        modification.id = this.generateId();
        modification.timestamp = new Date();
        modification.pageUrl = window.location.pathname;
        this.modifications.push(modification);

        console.log('[ModificationManager] 修正を記録:', {
            id: modification.id,
            type: modification.type,
            userInput: modification.userInput,
            selectedText: modification.selectedText?.substring(0, 50)
        });
    }

    generateInstructionDocument() {
        console.log('[ModificationManager] 修正指示書生成開始 - 修正件数:', this.modifications.length);

        let doc = '# 修正指示書\n\n';
        doc += `## 対象ページ: ${window.location.pathname}\n`;
        doc += `## 作成日時: ${new Date().toLocaleString('ja-JP')}\n`;
        doc += `## 修正件数: ${this.modifications.length}件\n\n`;
        doc += '---\n\n';

        if (this.modifications.length === 0) {
            doc += '**修正履歴がありません**\n\n';
            console.warn('[ModificationManager] 修正履歴が空です');
            return doc;
        }

        this.modifications.forEach((mod, i) => {
            doc += `## 修正 ${i + 1}: ${this.getModificationTitle(mod)}\n\n`;
            doc += `- **タイプ**: ${mod.type === 'immediate' ? '✓ 即時反映済み' : '⏳ バッチ処理待ち'}\n`;
            doc += `- **指示内容**: ${mod.userInput}\n`;
            doc += `- **実行日時**: ${mod.timestamp.toLocaleString('ja-JP')}\n`;
            doc += `- **状態**: ${mod.status === 'applied' ? '✓ 適用済み' : '⏳ 保留中'}\n`;

            if (mod.elementSelector) {
                doc += `- **対象要素**: \`${mod.elementSelector}\`\n`;
            }

            if (mod.selectedText) {
                const displayText = mod.selectedText.length > 100
                    ? mod.selectedText.substring(0, 100) + '...'
                    : mod.selectedText;
                doc += `- **選択テキスト**: "${displayText}"\n`;
            }

            if (mod.originalHtml && mod.modifiedHtml) {
                doc += `\n### 変更内容\n\n`;
                doc += `**修正前のHTML:**\n\`\`\`html\n${mod.originalHtml}\n\`\`\`\n\n`;
                doc += `**修正後のHTML:**\n\`\`\`html\n${mod.modifiedHtml}\n\`\`\`\n\n`;
            }

            doc += '---\n\n';
        });

        console.log('[ModificationManager] 修正指示書生成完了 - 文字数:', doc.length);
        return doc;
    }

    getModificationTitle(mod) {
        if (mod.type === 'immediate') {
            if (mod.userInput.match(/\d+%(大きく|小さく)/)) {
                const match = mod.userInput.match(/(\d+)%(大きく|小さく)/);
                return `文字サイズを${match[1]}%${match[2]}`;
            }
            if (mod.userInput.includes('大きく')) return 'サイズを大きく';
            if (mod.userInput.includes('小さく')) return 'サイズを小さく';
            if (mod.userInput.includes('短く') || mod.userInput.includes('要約')) return 'テキスト要約';
            if (mod.userInput.includes('色')) return '色変更';
            if (mod.userInput.includes('削除') || mod.userInput.includes('消して') ||
                mod.userInput.includes('取り除いて')) return 'テキスト削除';
            return '軽微な修正';
        }
        return '複雑な修正（バッチ処理）';
    }

    setSelectedElement(element, text) {
        this.iframeElement = element;
        this.selectedElement = {
            tagName: element.tagName,
            className: element.className,
            id: element.id
        };
        this.selectedText = text;

        console.log('[ModificationManager] 要素選択:', {
            tagName: element.tagName,
            textLength: text.length,
            text: text.substring(0, 50)
        });

        const selectionInfo = document.getElementById('selection-info');
        const selectionText = document.getElementById('selection-text');

        if (selectionInfo && selectionText) {
            if (element && text) {
                selectionText.textContent = text.length > 50 ? text.substring(0, 50) + '...' : text;
                selectionInfo.classList.add('active');
            } else {
                selectionText.textContent = '';
                selectionInfo.classList.remove('active');
            }
        }
    }

    clearSelection() {
        console.log('[ModificationManager] 選択クリア');
        this.iframeElement = null;
        this.selectedElement = null;
        this.selectedText = null;

        const selectionInfo = document.getElementById('selection-info');
        const selectionText = document.getElementById('selection-text');

        if (selectionInfo && selectionText) {
            selectionText.textContent = '';
            selectionInfo.classList.remove('active');
        }
    }

    undoLastModification() {
        console.log('[ModificationManager] Undo開始 - 履歴件数:', this.modifications.length);

        if (this.modifications.length === 0) {
            console.warn('[ModificationManager] Undo不可: 履歴なし');
            return { success: false, message: '元に戻す履歴がありません' };
        }

        // 最後の修正を取得
        const lastMod = this.modifications.pop();
        console.log('[ModificationManager] 最後の修正を取得:', lastMod);

        const iframe = document.getElementById('hp-preview');
        if (!iframe) {
            console.error('[ModificationManager] ❌ iframeが見つかりません');
            return { success: false, message: 'プレビューが見つかりません' };
        }

        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
        if (!iframeDoc) {
            console.error('[ModificationManager] ❌ iframe documentにアクセスできません');
            return { success: false, message: 'プレビューにアクセスできません' };
        }

        try {
            const element = iframeDoc.querySelector(lastMod.elementSelector);

            if (!element) {
                console.warn('[ModificationManager] ⚠️ 要素が見つかりませんが、削除された要素の可能性があるため復元を試みます');

                // 削除された要素を復元する場合
                if (lastMod.modificationType === 'delete' && lastMod.originalHtml) {
                    console.log('[ModificationManager] 削除要素を復元:', lastMod.originalHtml.substring(0, 100));

                    // 親要素を見つけて復元
                    const tempDiv = iframeDoc.createElement('div');
                    tempDiv.innerHTML = lastMod.originalHtml;
                    const restoredElement = tempDiv.firstChild;

                    // body に追加（本来は元の位置に戻すべきだが、簡易実装）
                    iframeDoc.body.appendChild(restoredElement);
                    console.log('[ModificationManager] ✅ 削除要素の復元完了');

                    return { success: true, message: '削除を元に戻しました' };
                }

                return { success: false, message: '元に戻す対象の要素が見つかりません' };
            }

            // 元のHTMLに戻す
            if (lastMod.originalHtml) {
                const tempDiv = iframeDoc.createElement('div');
                tempDiv.innerHTML = lastMod.originalHtml;
                const originalElement = tempDiv.firstChild;

                if (originalElement && element.parentNode) {
                    element.parentNode.replaceChild(originalElement, element);
                    console.log('[ModificationManager] ✅ 要素を元のHTMLに復元');
                }
            }

            console.log('[ModificationManager] ✅ Undo完了');
            return { success: true, message: '変更を元に戻しました' };

        } catch (error) {
            console.error('[ModificationManager] Undoエラー:', error);
            return { success: false, message: `元に戻す処理に失敗: ${error.message}` };
        }
    }

    generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2);
    }

    clearHistory() {
        this.modifications = [];
        console.log('[ModificationManager] 履歴クリア');
    }

    getModifications() {
        return this.modifications;
    }
}

// グローバルインスタンスを作成
window.modificationManager = new ModificationManager();
console.log('[ModificationManager] グローバルインスタンス作成完了');
