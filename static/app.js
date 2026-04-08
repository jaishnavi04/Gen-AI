/* ═══════════════════════════════════════════════════════════════════
   NexusAI — Main Application Logic
   ═══════════════════════════════════════════════════════════════════ */

(function () {
    "use strict";

    // ── Config ────────────────────────────────────────────────────
    const BACKEND_URL = "http://localhost:8000";
    const GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent";

    // ── DOM refs ──────────────────────────────────────────────────
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const sidebar = $("#sidebar");
    const sidebarToggle = $("#sidebarToggle");
    const mobileMenuBtn = $("#mobileMenuBtn");
    const newChatBtn = $("#newChatBtn");
    const chatHistory = $("#chatHistory");
    const messagesContainer = $("#messagesContainer");
    const welcomeScreen = $("#welcomeScreen");
    const messagesEl = $("#messages");
    const userInput = $("#userInput");
    const sendBtn = $("#sendBtn");
    const charCount = $("#charCount");
    const modelSelect = $("#modelSelect");
    const chatTitle = $("#chatTitle");
    const statusBadge = $("#statusBadge");
    const clearHistoryBtn = $("#clearHistoryBtn");
    const apiKeyModal = $("#apiKeyModal");
    const apiKeyInput = $("#apiKeyInput");
    const modalClose = $("#modalClose");
    const modalCancel = $("#modalCancel");
    const modalSave = $("#modalSave");

    // ── State ─────────────────────────────────────────────────────
    let chats = JSON.parse(localStorage.getItem("nexus_chats") || "{}");
    let activeChatId = localStorage.getItem("nexus_active_chat") || null;
    let isStreaming = false;
    let geminiApiKey = localStorage.getItem("nexus_gemini_key") || "AIzaSyBibChm6DfV9eFSUPs2MoEJYJ-uMULx3PQ";
    let conversationHistory = []; // For Gemini context

    // ── Init ──────────────────────────────────────────────────────
    function init() {
        bindEvents();
        renderChatHistory();
        if (activeChatId && chats[activeChatId]) {
            loadChat(activeChatId);
        } else {
            showWelcome();
        }
        autoResize();
    }

    // ── Event Bindings ────────────────────────────────────────────
    function bindEvents() {
        sidebarToggle.addEventListener("click", toggleSidebar);
        mobileMenuBtn.addEventListener("click", () => sidebar.classList.toggle("open"));
        newChatBtn.addEventListener("click", startNewChat);
        sendBtn.addEventListener("click", sendMessage);
        clearHistoryBtn.addEventListener("click", clearAllHistory);

        userInput.addEventListener("input", () => {
            autoResize();
            charCount.textContent = userInput.value.length;
            sendBtn.disabled = !userInput.value.trim();
        });

        userInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!sendBtn.disabled && !isStreaming) sendMessage();
            }
        });

        // Suggestion cards
        $$(".suggestion-card").forEach((card) => {
            card.addEventListener("click", () => {
                userInput.value = card.dataset.query;
                userInput.dispatchEvent(new Event("input"));
                sendMessage();
            });
        });

        // Quick actions
        $$(".action-btn[data-action]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const actionMap = {
                    tasks: "Show all my tasks",
                    notes: "Show all my notes",
                    calendar: "Show my upcoming events",
                };
                userInput.value = actionMap[btn.dataset.action] || "";
                userInput.dispatchEvent(new Event("input"));
                sendMessage();
            });
        });

        // Model select — prompt for API key if needed
        modelSelect.addEventListener("change", () => {
            if (modelSelect.value === "gemini" && !geminiApiKey) {
                showApiKeyModal();
            }
        });

        // Modal
        modalClose.addEventListener("click", hideApiKeyModal);
        modalCancel.addEventListener("click", hideApiKeyModal);
        modalSave.addEventListener("click", () => {
            geminiApiKey = apiKeyInput.value.trim();
            if (geminiApiKey) {
                localStorage.setItem("nexus_gemini_key", geminiApiKey);
                hideApiKeyModal();
            }
        });

        // Click outside sidebar on mobile
        document.addEventListener("click", (e) => {
            if (
                window.innerWidth <= 768 &&
                sidebar.classList.contains("open") &&
                !sidebar.contains(e.target) &&
                e.target !== mobileMenuBtn
            ) {
                sidebar.classList.remove("open");
            }
        });
    }

    // ── Sidebar ───────────────────────────────────────────────────
    function toggleSidebar() {
        sidebar.classList.toggle("collapsed");
    }

    // ── Chat Management ───────────────────────────────────────────
    function startNewChat() {
        const id = "chat_" + Date.now();
        chats[id] = { title: "New Chat", messages: [], created: Date.now() };
        activeChatId = id;
        conversationHistory = [];
        saveState();
        renderChatHistory();
        showWelcome();
        messagesEl.innerHTML = "";
        chatTitle.textContent = "NexusAI Assistant";
        userInput.focus();
        sidebar.classList.remove("open");
    }

    function loadChat(id) {
        activeChatId = id;
        localStorage.setItem("nexus_active_chat", id);
        const chat = chats[id];
        if (!chat) return;

        chatTitle.textContent = chat.title;
        welcomeScreen.style.display = "none";
        messagesEl.innerHTML = "";

        // Rebuild conversation history for Gemini context
        conversationHistory = [];
        chat.messages.forEach((msg) => {
            addMessageToDOM(msg.role, msg.content, msg.time, false);
            conversationHistory.push({
                role: msg.role === "user" ? "user" : "model",
                parts: [{ text: msg.content }],
            });
        });

        renderChatHistory();
        scrollToBottom();
        sidebar.classList.remove("open");
    }

    function showWelcome() {
        welcomeScreen.style.display = "flex";
        messagesEl.innerHTML = "";
    }

    function saveState() {
        localStorage.setItem("nexus_chats", JSON.stringify(chats));
        localStorage.setItem("nexus_active_chat", activeChatId);
    }

    function clearAllHistory() {
        if (!confirm("Clear all chat history? This cannot be undone.")) return;
        chats = {};
        activeChatId = null;
        conversationHistory = [];
        saveState();
        renderChatHistory();
        showWelcome();
        chatTitle.textContent = "NexusAI Assistant";
    }

    function renderChatHistory() {
        chatHistory.innerHTML = "";
        const sorted = Object.entries(chats).sort((a, b) => b[1].created - a[1].created);
        sorted.forEach(([id, chat]) => {
            const item = document.createElement("div");
            item.className = `chat-history-item${id === activeChatId ? " active" : ""}`;
            item.innerHTML = `<span class="hist-icon">💬</span><span class="hist-text">${escapeHtml(chat.title)}</span>`;
            item.addEventListener("click", () => loadChat(id));
            chatHistory.appendChild(item);
        });
    }

    // ── Send Message ──────────────────────────────────────────────
    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text || isStreaming) return;

        // Ensure a chat exists
        if (!activeChatId || !chats[activeChatId]) {
            startNewChat();
        }

        // Hide welcome
        welcomeScreen.style.display = "none";

        // Update chat title from first message
        if (chats[activeChatId].messages.length === 0) {
            chats[activeChatId].title = text.length > 40 ? text.slice(0, 40) + "…" : text;
            chatTitle.textContent = chats[activeChatId].title;
            renderChatHistory();
        }

        // Add user message
        const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        addMessageToDOM("user", text, now);
        chats[activeChatId].messages.push({ role: "user", content: text, time: now });
        conversationHistory.push({ role: "user", parts: [{ text }] });
        saveState();

        // Clear input
        userInput.value = "";
        userInput.dispatchEvent(new Event("input"));
        scrollToBottom();

        // Show typing indicator
        const typingEl = showTyping();
        isStreaming = true;
        setStatus("Thinking...", false);

        try {
            let response;
            const model = modelSelect.value;

            if (model === "gemini") {
                response = await callGemini(text);
            } else {
                response = await callBackend(text);
            }

            typingEl.remove();
            const aiTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            addMessageToDOM("assistant", response, aiTime);
            chats[activeChatId].messages.push({ role: "assistant", content: response, time: aiTime });
            conversationHistory.push({ role: "model", parts: [{ text: response }] });
            saveState();
            renderChatHistory();
        } catch (err) {
            typingEl.remove();
            const errMsg = `❌ **Error:** ${err.message || "Something went wrong. Please try again."}`;
            addMessageToDOM("assistant", errMsg, "");
        } finally {
            isStreaming = false;
            setStatus("Online", true);
            scrollToBottom();
        }
    }

    // ── API Calls ─────────────────────────────────────────────────
    async function callGemini(query) {
        if (!geminiApiKey) {
            showApiKeyModal();
            throw new Error("Please set your Gemini API key first (it's free!).");
        }

        const systemInstruction = `You are NexusAI, an extremely intelligent, knowledgeable, and helpful AI assistant. You can answer ANY question on ANY topic — science, math, coding, history, philosophy, creative writing, and more. Always provide thorough, accurate, and well-structured answers. Use markdown formatting for better readability. If you're not sure about something, say so honestly but still give your best analysis.`;

        const body = {
            system_instruction: {
                parts: [{ text: systemInstruction }],
            },
            contents: conversationHistory.length > 0
                ? conversationHistory
                : [{ role: "user", parts: [{ text: query }] }],
            generationConfig: {
                temperature: 0.8,
                topP: 0.95,
                topK: 40,
                maxOutputTokens: 8192,
            },
        };

        const res = await fetch(`${GEMINI_API_URL}?key=${geminiApiKey}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            if (res.status === 400 && errData?.error?.message?.includes("API key")) {
                localStorage.removeItem("nexus_gemini_key");
                geminiApiKey = "";
                throw new Error("Invalid API key. Please set a valid Gemini key.");
            }
            throw new Error(errData?.error?.message || `Gemini API error (${res.status})`);
        }

        const data = await res.json();
        const candidate = data?.candidates?.[0];
        if (!candidate?.content?.parts?.[0]?.text) {
            throw new Error("Empty response from Gemini.");
        }
        return candidate.content.parts[0].text;
    }

    async function callBackend(query) {
        const res = await fetch(`${BACKEND_URL}/query`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: query, session: "web-ui" }),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `Backend error (${res.status})`);
        }

        const data = await res.json();
        return data.response;
    }

    // ── DOM Helpers ───────────────────────────────────────────────
    function addMessageToDOM(role, content, time, animate = true) {
        const div = document.createElement("div");
        div.className = `message ${role}`;
        if (!animate) div.style.animation = "none";

        const avatar = role === "user" ? "👤" : "✨";
        const name = role === "user" ? "You" : "NexusAI";

        div.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-name">${name}</span>
                    <span class="message-time">${time}</span>
                </div>
                <div class="message-body">${renderMarkdown(content)}</div>
            </div>
        `;
        messagesEl.appendChild(div);

        // Add copy buttons to code blocks
        div.querySelectorAll("pre").forEach((pre) => {
            const btn = document.createElement("button");
            btn.className = "copy-btn";
            btn.textContent = "Copy";
            btn.addEventListener("click", () => {
                const code = pre.querySelector("code")?.textContent || pre.textContent;
                navigator.clipboard.writeText(code).then(() => {
                    btn.textContent = "Copied!";
                    setTimeout(() => (btn.textContent = "Copy"), 2000);
                });
            });
            pre.style.position = "relative";
            pre.appendChild(btn);
        });

        if (animate) scrollToBottom();
    }

    function showTyping() {
        const div = document.createElement("div");
        div.className = "message assistant";
        div.id = "typingIndicator";
        div.innerHTML = `
            <div class="message-avatar">✨</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-name">NexusAI</span>
                </div>
                <div class="message-body">
                    <div class="typing-indicator">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>
                </div>
            </div>
        `;
        messagesEl.appendChild(div);
        scrollToBottom();
        return div;
    }

    function setStatus(text, online) {
        statusBadge.innerHTML = `<span class="status-dot" style="background:${online ? "#22c55e" : "#eab308"};box-shadow:0 0 6px ${online ? "rgba(34,197,94,0.5)" : "rgba(234,179,8,0.5)"}"></span>${text}`;
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        });
    }

    function autoResize() {
        userInput.style.height = "auto";
        userInput.style.height = Math.min(userInput.scrollHeight, 160) + "px";
    }

    // ── Markdown Renderer ─────────────────────────────────────────
    function renderMarkdown(text) {
        if (!text) return "";
        let html = escapeHtml(text);

        // Code blocks (```...```)
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
            return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
        });

        // Inline code
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

        // Headers
        html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
        html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
        html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

        // Bold + Italic
        html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

        // Blockquotes
        html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

        // Unordered lists
        html = html.replace(/^[\-\*] (.+)$/gm, "<li>$1</li>");
        html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

        // Ordered lists
        html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

        // Horizontal rule
        html = html.replace(/^---$/gm, "<hr>");

        // Links
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

        // Paragraphs (double newlines)
        html = html.replace(/\n\n/g, "</p><p>");

        // Single newlines
        html = html.replace(/\n/g, "<br>");

        // Wrap in paragraph
        html = "<p>" + html + "</p>";

        // Clean up empty paragraphs
        html = html.replace(/<p><\/p>/g, "");
        html = html.replace(/<p>(<h[1-3]>)/g, "$1");
        html = html.replace(/(<\/h[1-3]>)<\/p>/g, "$1");
        html = html.replace(/<p>(<pre>)/g, "$1");
        html = html.replace(/(<\/pre>)<\/p>/g, "$1");
        html = html.replace(/<p>(<ul>)/g, "$1");
        html = html.replace(/(<\/ul>)<\/p>/g, "$1");
        html = html.replace(/<p>(<blockquote>)/g, "$1");
        html = html.replace(/(<\/blockquote>)<\/p>/g, "$1");
        html = html.replace(/<p>(<hr>)<\/p>/g, "$1");

        return html;
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ── API Key Modal ─────────────────────────────────────────────
    function showApiKeyModal() {
        apiKeyModal.style.display = "flex";
        apiKeyInput.value = geminiApiKey;
        apiKeyInput.focus();
    }

    function hideApiKeyModal() {
        apiKeyModal.style.display = "none";
    }

    // ── Boot ──────────────────────────────────────────────────────
    init();
})();
