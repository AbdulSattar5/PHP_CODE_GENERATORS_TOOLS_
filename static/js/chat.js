/**
 * ChatGPT-style chat UI for GenCode AI
 */

class ChatManager {
    constructor() {
        this.chatMessages = document.getElementById('chatMessages');
        this.userInput = document.getElementById('userInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.emptyState = document.getElementById('chatEmptyState');

        this.isTyping = false;
        this.isComposing = false;
        this.snippetStore = new Map();
        this.snippetCounter = 0;
        this.autoScroll = true;

        this.init();
    }

    init() {
        if (this.userInput) {
            this.userInput.addEventListener('compositionstart', () => {
                this.isComposing = true;
            });
            this.userInput.addEventListener('compositionend', () => {
                this.isComposing = false;
            });
            this.userInput.addEventListener('keydown', (e) => {
                const isEnter = e.key === 'Enter' || e.code === 'Enter' || e.code === 'NumpadEnter';
                if (isEnter && !e.shiftKey && !this.isComposing && !e.isComposing) {
                    e.preventDefault();
                    this.handleSend();
                }
            });
            this.userInput.addEventListener('input', () => {
                this.autoResizeTextarea();
                this.syncSendButton();
            });
        }

        if (this.chatMessages) {
            this.chatMessages.addEventListener('scroll', () => {
                const el = this.chatMessages;
                const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
                this.autoScroll = nearBottom;
            });
        }

        this.autoResizeTextarea();
        this.syncSendButton();
    }

    autoResizeTextarea() {
        if (!this.userInput) return;
        const maxHeight = 200;
        const baseMinHeight = 24;
        this.userInput.style.height = '0px';
        const next = Math.max(baseMinHeight, Math.min(this.userInput.scrollHeight, maxHeight));
        this.userInput.style.height = `${next}px`;
        this.userInput.style.overflowY = this.userInput.scrollHeight > maxHeight ? 'auto' : 'hidden';
        this.userInput.dispatchEvent(new CustomEvent('composer:input-state', { bubbles: true }));
    }

    resetComposer() {
        if (!this.userInput) return;
        this.userInput.value = '';
        this.autoResizeTextarea();
        this.syncSendButton();
    }

    syncSendButton() {
        if (!this.sendBtn || !this.userInput) return;
        const hasText = this.userInput.value.trim().length > 0;
        this.sendBtn.classList.toggle('is-ready', hasText);
        if (!this.sendBtn.classList.contains('is-loading')) {
            this.sendBtn.disabled = !hasText;
        }
    }

    hideEmptyState() {
        if (this.emptyState) {
            this.emptyState.classList.add('hidden');
        }
    }

    appendUserMessage(text) {
        return this.addUserMessage(text);
    }

    appendAIMessage(text, options = {}) {
        return this.addAssistantMessage(text, options);
    }

    addUserMessage(text) {
        if (!this.chatMessages) return;
        this.hideEmptyState();

        const row = document.createElement('div');
        row.className = 'chat-message user';
        row.innerHTML = `<div class="user-bubble">${this.escapeHtml(text)}</div>`;
        this.chatMessages.appendChild(row);
        this.scrollToBottom();
    }

    addAssistantMessage(text, options = {}) {
        if (!this.chatMessages) return;
        this.hideEmptyState();

        const row = document.createElement('div');
        row.className = 'chat-message assistant';
        const body = document.createElement('div');
        body.className = 'message-body';
        body.innerHTML = this.formatMessageContent(text);

        if (options.codeSnippets) {
            body.innerHTML += this.renderCodeSnippets(options.codeSnippets);
        }

        row.innerHTML = `
            <div class="ai-avatar" aria-hidden="true"><i class="fas fa-code"></i></div>
        `;
        row.appendChild(body);

        this.addMessageActions(row, body, text);
        this.bindSnippetCopyButtons(row);
        this.highlightMessageCodeBlocks(row);

        if (Array.isArray(options.actions) && options.actions.length) {
            const actions = document.createElement('div');
            actions.className = 'message-actions';
            actions.style.opacity = '1';
            options.actions.forEach((action) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'msg-action-btn';
                btn.innerHTML = `<i class="${this.sanitizeClassName(action?.icon || 'fas fa-bolt')}"></i>`;
                btn.title = action?.text || 'Action';
                btn.addEventListener('click', () => {
                    if (typeof action?.onClick === 'function') action.onClick();
                    else if (typeof action?.onClick === 'string') this.invokeActionString(action.onClick);
                });
                actions.appendChild(btn);
            });
            body.appendChild(actions);
        }

        this.chatMessages.appendChild(row);
        this.scrollToBottom();
        return row;
    }

    addMessageActions(row, body, rawText) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        actions.innerHTML = `
            <button type="button" class="msg-action-btn" title="Copy" data-action="copy"><i class="fas fa-copy"></i></button>
            <button type="button" class="msg-action-btn" title="Good" data-action="up"><i class="fas fa-thumbs-up"></i></button>
            <button type="button" class="msg-action-btn" title="Bad" data-action="down"><i class="fas fa-thumbs-down"></i></button>
            <button type="button" class="msg-action-btn" title="Regenerate" data-action="regen"><i class="fas fa-rotate-right"></i></button>
        `;
        actions.querySelector('[data-action="copy"]').addEventListener('click', async () => {
            await this.copyTextToClipboard(rawText);
        });
        actions.querySelector('[data-action="regen"]').addEventListener('click', () => {
            if (typeof generateCode === 'function') generateCode();
        });
        body.appendChild(actions);
    }

    async streamAssistantMessage(text, delayMs = 15) {
        if (!this.chatMessages) return;
        this.hideEmptyState();
        this.hideTypingIndicator();

        const row = document.createElement('div');
        row.className = 'chat-message assistant';
        row.innerHTML = `<div class="ai-avatar" aria-hidden="true"><i class="fas fa-code"></i></div>`;
        const body = document.createElement('div');
        body.className = 'message-body';
        const span = document.createElement('span');
        const cursor = document.createElement('span');
        cursor.className = 'stream-cursor';
        cursor.textContent = '|';
        body.appendChild(span);
        body.appendChild(cursor);
        row.appendChild(body);
        this.chatMessages.appendChild(row);

        const content = String(text ?? '');
        for (let i = 0; i < content.length; i++) {
            span.textContent += content[i];
            if (i % 3 === 0) this.scrollToBottom();
            await new Promise((r) => setTimeout(r, delayMs));
        }

        cursor.remove();
        body.innerHTML = this.formatMessageContent(content);
        this.addMessageActions(row, body, content);
        this.highlightMessageCodeBlocks(row);
        this.scrollToBottom();
        return row;
    }

    showTypingIndicator() {
        if (this.isTyping || !this.chatMessages) return;
        this.isTyping = true;
        this.hideEmptyState();

        const row = document.createElement('div');
        row.className = 'chat-message assistant typing-indicator';
        row.id = 'typingIndicator';
        row.innerHTML = `
            <div class="ai-avatar" aria-hidden="true"><i class="fas fa-code"></i></div>
            <div class="message-body">
                <div class="typing-dots"><span></span><span></span><span></span></div>
            </div>
        `;
        this.chatMessages.appendChild(row);
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        document.getElementById('typingIndicator')?.remove();
        this.isTyping = false;
    }

    addErrorMessage(errorText) {
        this.addAssistantMessage(`**Error:** ${errorText}`);
    }

    addSuccessMessage(data) {
        const score = Number(data?.validation_score || 0);
        const count = Object.keys(data?.generated_files || {}).length;
        this.addAssistantMessage(
            `Code generated successfully.\n\n- ${count} file(s) created\n- Quality score: **${score.toFixed(1)}%**`,
            {
                actions: [
                    {
                        icon: 'fas fa-clipboard-check',
                        text: 'Quality Report',
                        onClick: () => {
                            if (typeof showValidationPanel === 'function') {
                                showValidationPanel(data.validation_result, score);
                            }
                        },
                    },
                    {
                        icon: 'fas fa-download',
                        text: 'Download',
                        onClick: () => {
                            if (typeof downloadCode === 'function') downloadCode();
                        },
                    },
                ],
            }
        );
    }

    clearMessages() {
        if (!this.chatMessages) return;
        this.chatMessages.innerHTML = '';
        if (this.emptyState) {
            this.emptyState.classList.remove('hidden');
            this.chatMessages.appendChild(this.emptyState);
        } else {
            const empty = document.createElement('div');
            empty.className = 'chat-empty-state';
            empty.id = 'chatEmptyState';
            empty.innerHTML = `
                <h2>What can I help with?</h2>
                <div class="suggestion-chips">
                    <button type="button" class="suggestion-chip" onclick="useExample('Create a student registration form')">Generate Code</button>
                </div>
            `;
            this.chatMessages.appendChild(empty);
            this.emptyState = empty;
        }
    }

    scrollToBottom() {
        if (!this.chatMessages || !this.autoScroll) return;
        requestAnimationFrame(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        });
    }

    handleSend() {
        if (!this.userInput) return;
        const text = this.userInput.value.trim();
        if (!text) return;
        if (typeof generateCode === 'function') generateCode();
    }

    formatMessageContent(text) {
        const safe = this.escapeHtml(String(text ?? '')).replace(/\r\n/g, '\n');
        const fenced = [];
        let idx = 0;
        const withTokens = safe.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
            const token = `@@CODE${idx}@@`;
            fenced.push({ token, lang: lang || 'text', code });
            idx += 1;
            return token;
        });

        const blocks = withTokens.split(/\n{2,}/).filter((p) => p.trim());
        if (!blocks.length) return '<p class="message-text"></p>';

        return blocks
            .map((block) => {
                let html = this.renderMessageBlock(block);
                fenced.forEach(({ token, lang, code }) => {
                    if (block.includes(token)) {
                        html = this.renderCodeBlock(lang, code);
                    }
                });
                return html;
            })
            .join('');
    }

    renderCodeBlock(language, code) {
        const id = `snippet-${++this.snippetCounter}`;
        this.snippetStore.set(id, code);
        const langLabel = this.escapeHtml((language || 'text').toLowerCase());
        const langClass = this.sanitizeLanguageClass(language);
        return `
            <div class="code-block-wrap">
                <div class="code-block-header">
                    <span>${langLabel}</span>
                    <button type="button" class="code-copy-btn" data-snippet-id="${id}">Copy</button>
                </div>
                <pre><code class="${langClass}">${this.escapeHtml(code)}</code></pre>
            </div>
        `;
    }

    renderMessageBlock(block) {
        const lines = block.split('\n').filter((l) => l.trim());
        const isList = lines.length > 1 && lines.every((l) => /^\s*[-*]\s+/.test(l));
        if (isList) {
            const items = lines
                .map((l) => l.replace(/^\s*[-*]\s+/, ''))
                .map((l) => `<li>${this.applyInlineFormatting(l)}</li>`)
                .join('');
            return `<ul class="message-list">${items}</ul>`;
        }
        const paragraph = lines.map((l) => this.applyInlineFormatting(l)).join('<br>');
        return `<p class="message-text">${paragraph}</p>`;
    }

    applyInlineFormatting(text) {
        return text
            .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    }

    renderCodeSnippets(codeSnippets) {
        let html = '';
        Object.entries(codeSnippets).forEach(([language, code]) => {
            html += this.renderCodeBlock(language, String(code ?? ''));
        });
        return html;
    }

    bindSnippetCopyButtons(container) {
        container.querySelectorAll('.code-copy-btn[data-snippet-id]').forEach((btn) => {
            btn.addEventListener('click', async () => {
                const id = btn.getAttribute('data-snippet-id');
                const text = this.snippetStore.get(id);
                if (!text) return;
                const ok = await this.copyTextToClipboard(text);
                btn.textContent = ok ? 'Copied!' : 'Failed';
                setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
            });
        });
    }

    highlightMessageCodeBlocks(container) {
        if (!window.hljs) return;
        container.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
    }

    async copyTextToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch {
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            return ok;
        }
    }

    sanitizeLanguageClass(language) {
        const safe = String(language || 'plaintext').toLowerCase().replace(/[^a-z0-9_+-]/g, '');
        return `language-${safe || 'plaintext'}`;
    }

    sanitizeClassName(className) {
        return String(className || 'fas fa-circle').replace(/[^a-zA-Z0-9_\-\s]/g, ' ').trim() || 'fas fa-circle';
    }

    invokeActionString(actionCall) {
        const raw = String(actionCall || '').trim();
        const match = raw.match(/^([a-zA-Z_$][\w$]*)\(([\s\S]*)\)\s*;?$/);
        if (!match) return;
        const fn = window[match[1]];
        if (typeof fn !== 'function') return;
        const argsRaw = match[2].trim();
        if (!argsRaw) return fn();
        try {
            fn(...JSON.parse(`[${argsRaw}]`));
        } catch {
            fn(argsRaw);
        }
    }

    escapeHtml(text) {
        const d = document.createElement('div');
        d.textContent = String(text ?? '');
        return d.innerHTML;
    }
}

const chatManager = new ChatManager();
window.chatManager = chatManager;

