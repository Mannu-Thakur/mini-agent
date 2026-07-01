// ── State ──────────────────────────────────────────────────────────────────
const state = {
  sessionId: crypto.randomUUID(),
  sessions: [],
  activeIdx: null,
  debugOpen: false,
  sidebarOpen: true,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const messagesEl   = $("messages");
const messagesWrap = $("messagesWrap");
const inputEl      = $("userInput");
const sendBtn      = $("sendBtn");
const chatHistory  = $("chatHistory");
const debugPanel   = $("debugPanel");
const debugBody    = $("debugBody");
const debugToggle  = $("debugToggle");
const topbarTitle  = $("topbarTitle");
const sidebar      = $("sidebar");

// ── Session helpers ────────────────────────────────────────────────────────
function newSession() {
  const id = crypto.randomUUID();
  const session = { id, title: "New Conversation", messages: [] };
  state.sessions.unshift(session);
  state.activeIdx = 0;
  state.sessionId = id;
  renderSidebar();
  clearChat();
  showWelcome();
  topbarTitle.textContent = session.title;
}

function switchSession(idx) {
  state.activeIdx = idx;
  const session = state.sessions[idx];
  state.sessionId = session.id;
  renderSidebar();
  clearChat();
  topbarTitle.textContent = session.title;

  if (session.messages.length > 0) {
    session.messages.forEach(m => appendMessage(m.role, m.html, m.meta, false));
    return;
  }
  // Load from server
  fetch(`/api/sessions/${session.id}/messages`)
    .then(r => r.ok ? r.json() : { messages: [] })
    .then(data => {
      if (data.messages.length === 0) { showWelcome(); return; }
      data.messages.forEach(m => {
        const role = m.role === "human" ? "user" : "ai";
        const html = role === "user"
          ? `<p>${escHtml(m.content)}</p>`
          : markdownToHtml(m.content);
        appendMessage(role, html, null, true);
      });
    })
    .catch(() => {});
}

function saveMessage(role, html, meta) {
  if (state.activeIdx === null) return;
  state.sessions[state.activeIdx].messages.push({ role, html, meta });
}

// ── Sidebar ────────────────────────────────────────────────────────────────
function renderSidebar() {
  chatHistory.innerHTML = "";
  state.sessions.forEach((s, i) => {
    const li = document.createElement("li");
    li.className = "chat-item" + (i === state.activeIdx ? " active" : "");

    const titleSpan = document.createElement("span");
    titleSpan.className = "chat-item-title";
    titleSpan.textContent = s.title;
    titleSpan.ondblclick = (e) => {
      e.stopPropagation();
      const input = document.createElement("input");
      input.className = "rename-input";
      input.value = s.title;
      input.onclick = ev => ev.stopPropagation();
      input.onblur = () => finishRename(i, input.value);
      input.onkeydown = ev => {
        if (ev.key === "Enter") input.blur();
        if (ev.key === "Escape") { input.value = s.title; input.blur(); }
      };
      li.replaceChild(input, titleSpan);
      input.focus();
      input.select();
    };

    const delBtn = document.createElement("button");
    delBtn.className = "chat-item-del";
    delBtn.textContent = "\u00d7";
    delBtn.title = "Delete conversation";
    delBtn.onclick = e => { e.stopPropagation(); deleteSession(i); };

    li.appendChild(titleSpan);
    li.appendChild(delBtn);
    li.onclick = () => switchSession(i);
    chatHistory.appendChild(li);
  });
}

function finishRename(idx, newTitle) {
  newTitle = newTitle.trim() || "Untitled";
  state.sessions[idx].title = newTitle;
  if (idx === state.activeIdx) topbarTitle.textContent = newTitle;
  renderSidebar();
  fetch("/api/sessions/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessions[idx].id, title: newTitle }),
  }).catch(() => {});
}

function deleteSession(idx) {
  const s = state.sessions[idx];
  fetch(`/api/sessions/${s.id}`, { method: "DELETE" }).catch(() => {});
  state.sessions.splice(idx, 1);
  if (state.sessions.length === 0) {
    newSession();
  } else if (idx === state.activeIdx) {
    switchSession(Math.min(idx, state.sessions.length - 1));
  } else {
    if (idx < state.activeIdx) state.activeIdx--;
    renderSidebar();
  }
}

// ── Chat rendering ─────────────────────────────────────────────────────────
function clearChat() { messagesEl.innerHTML = ""; }

function showWelcome() {
  if (messagesEl.querySelector(".welcome")) return;
  messagesEl.innerHTML = `
    <div class="welcome">
      <div class="welcome-icon">\u26a1</div>
      <h1>Mini Agent</h1>
      <p>Ask me anything. I can chat, check weather, do math, and search the web.</p>
      <div class="pill-row">
        <button class="pill" onclick="sendSuggestion('What is the weather in Mumbai?')">\ud83c\udf24 Weather in Mumbai</button>
        <button class="pill" onclick="sendSuggestion('What is 1234 * 5678?')">\ud83e\uddee Calculator</button>
        <button class="pill" onclick="sendSuggestion('Who is Alan Turing?')">\ud83d\udd0d Web Search</button>
        <button class="pill" onclick="sendSuggestion('Tell me a fun fact')">\ud83d\udcac Just chat</button>
      </div>
    </div>`;
}

function hideWelcome() {
  const w = messagesEl.querySelector(".welcome");
  if (w) w.remove();
}

// function markdownToHtml(text) {
//   if (typeof marked === "undefined") {
//     console.error("Marked.js is not loaded.");
//     return escHtml(text);
//   }

//   marked.setOptions({
//     breaks: true,
//     gfm: true
//   });

//   return marked.parse(text);
// }

function markdownToHtml(markdown) {

    marked.setOptions({
        gfm: true,
        breaks: true
    });

    const html = marked.parse(markdown);

    return DOMPurify.sanitize(html);
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function appendMessage(role, html, meta = null, save = true) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const avatarEmoji = role === "user" ? "\ud83e\uddd1" : "\u26a1";
  let inner = `<div class="avatar">${avatarEmoji}</div><div class="bubble">`;

  if (role === "ai" && meta?.trace) {
    inner += buildTraceHtml(meta.trace);
  }

  inner += html;
  if (role === "ai") {
    inner += `<br><button class="copy-btn" onclick="copyBubble(this)">\ud83d\udccb Copy</button>`;
  }
  inner += "</div>";
  div.innerHTML = inner;
  messagesEl.appendChild(div);
  scrollBottom();
  if (save) saveMessage(role, html, meta);
}

function buildTraceHtml(trace) {
  if (!trace) return "";
  const toolSteps = trace.filter(s => s.action);
  if (toolSteps.length === 0) return "";
  const traceId = "trace-" + Date.now() + "-" + Math.random().toString(36).slice(2, 6);
  const icons = toolSteps.map(s => {
    const toolName = s.action.split(":")[0];
    const icon = { weather: "\ud83c\udf24", calculator: "\ud83e\uddee", search: "\ud83d\udd0d" }[toolName] || "\ud83d\udd27";
    return `${icon} <strong>${toolName}</strong>`;
  });
  const traceContent = toolSteps.map(s =>
    `Step ${s.step}:\n  THINK: ${s.thought || ""}\n  ACTION: ${s.action}\n  RESULT: ${s.observation || ""}`
  ).join("\n\n");
  return `<div class="tool-badge" onclick="toggleTrace('${traceId}')">${icons.join(" \u00b7 ")} \u25be</div>` +
         `<div class="tool-trace" id="${traceId}">${escHtml(traceContent)}</div>`;
}

function createStreamBubble() {
  const div = document.createElement("div");
  div.className = "msg ai";
  div.innerHTML = `<div class="avatar">\u26a1</div><div class="bubble"><span class="stream-content"></span><span class="streaming-cursor"></span></div>`;
  messagesEl.appendChild(div);
  scrollBottom();
  const contentEl = div.querySelector(".stream-content");
  const cursorEl = div.querySelector(".streaming-cursor");
  const bubbleEl = div.querySelector(".bubble");
  return {
    append(token) { contentEl.textContent += token; scrollBottom(); },
    showAction(tool, input) {
      const badge = document.createElement("div");
      badge.className = "tool-badge stream-badge";
      const icon = { weather: "\ud83c\udf24", calculator: "\ud83e\uddee", search: "\ud83d\udd0d" }[tool] || "\ud83d\udd27";
      badge.innerHTML = `${icon} <strong>${tool}</strong>: ${escHtml(input)}`;
      bubbleEl.insertBefore(badge, contentEl);
    },
    clearStream() { contentEl.textContent = ""; },
    finalize(finalHtml, meta) {
      cursorEl.remove();
      const traceHtml = buildTraceHtml(meta?.trace);
      bubbleEl.innerHTML = traceHtml + finalHtml +
        `<br><button class="copy-btn" onclick="copyBubble(this)">\ud83d\udccb Copy</button>`;
      scrollBottom();
    }
  };
}

function scrollBottom() {
  messagesWrap.scrollTop = messagesWrap.scrollHeight;
}

// ── Tool trace toggle ──────────────────────────────────────────────────────
function toggleTrace(id) {
  const el = $(id);
  if (el) el.classList.toggle("open");
}

// ── Copy ───────────────────────────────────────────────────────────────────
function copyBubble(btn) {
  const bubble = btn.closest(".bubble");
  const clone = bubble.cloneNode(true);
  clone.querySelectorAll(".copy-btn, .tool-badge, .tool-trace").forEach(el => el.remove());
  navigator.clipboard.writeText(clone.textContent.trim()).catch(() => {});
  btn.textContent = "\u2705 Copied";
  setTimeout(() => { btn.textContent = "\ud83d\udccb Copy"; }, 2000);
}

// ── Debug panel ────────────────────────────────────────────────────────────
function pushDebug(meta, userMsg) {
  const empty = debugBody.querySelector(".debug-empty");
  if (empty) empty.remove();
  const card = document.createElement("div");
  card.className = "debug-card";
  const trace = meta.trace || [];
  const stepsHtml = trace.map(s => {
    let out = `<strong>Step ${s.step}:</strong>\n`;
    if (s.thought)      out += `  THINK: ${escHtml(s.thought)}\n`;
    if (s.action)       out += `  ACTION: ${escHtml(s.action)}\n`;
    if (s.observation)  out += `  OBSERVATION: ${escHtml(s.observation.slice(0, 300))}\n`;
    if (s.final_answer) out += `  FINAL_ANSWER: (see response)\n`;
    if (s.clarify)      out += `  CLARIFY: ${escHtml(s.clarify)}\n`;
    if (s.error)        out += `  ERROR: ${escHtml(s.error)}\n`;
    return out;
  }).join("\n");
  card.innerHTML = `
    <div class="debug-card-title">Turn</div>
    <pre><strong>Query:</strong> ${escHtml(userMsg)}
<strong>Steps:</strong> ${trace.length}
${stepsHtml}</pre>`;
  debugBody.insertBefore(card, debugBody.firstChild);
}

// ── Send (SSE streaming) ──────────────────────────────────────────────────
async function sendMessage(text) {
  text = text.trim();
  if (!text) return;

  if (state.activeIdx === null) {
    const id = crypto.randomUUID();
    state.sessions.unshift({ id, title: text.slice(0, 36) || "New Conversation", messages: [] });
    state.activeIdx = 0;
    state.sessionId = id;
    topbarTitle.textContent = state.sessions[0].title;
    renderSidebar();
  }

  hideWelcome();
  appendMessage("user", `<p>${escHtml(text)}</p>`);
  inputEl.value = "";
  inputEl.style.height = "auto";
  sendBtn.disabled = true;

  const streamBubble = createStreamBubble();
  let finalText = "", finalTrace = [];

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, message: text }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();

      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        let event;
        try { event = JSON.parse(part.slice(6)); } catch { continue; }

        if (event.type === "token") {
          streamBubble.append(event.content);
        } else if (event.type === "action") {
          streamBubble.clearStream();
          streamBubble.showAction(event.tool, event.input);
        } else if (event.type === "observation") {
          streamBubble.clearStream();
        } else if (event.type === "done") {
          finalText = event.text || "";
          finalTrace = event.trace || [];
        }
      }
    }

const html = `
<div class="markdown-body">
${markdownToHtml(finalText)}
</div>
`;

const meta = { trace: finalTrace };

streamBubble.finalize(html, meta);
saveMessage("ai", html, meta);

// Highlight syntax after rendering
requestAnimationFrame(() => {
    document.querySelectorAll(".markdown-body pre code").forEach(block => {
        hljs.highlightElement(block);
    });
});
    pushDebug(meta, text);

    if (state.sessions[state.activeIdx].messages.length <= 2) {
      const title = text.slice(0, 36) + (text.length > 36 ? "\u2026" : "");
      state.sessions[state.activeIdx].title = title;
      topbarTitle.textContent = title;
      renderSidebar();
    }
  } catch (err) {
    streamBubble.finalize(`<p style="color:#f87171">Error: ${escHtml(err.message)}</p>`, null);
  }

  sendBtn.disabled = false;
  inputEl.focus();
}

function sendSuggestion(text) {
  inputEl.value = text;
  sendMessage(text);
}

// ── Events ─────────────────────────────────────────────────────────────────
sendBtn.onclick = () => sendMessage(inputEl.value);

inputEl.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(inputEl.value); }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + "px";
});

$("sidebarToggle").onclick = () => {
  state.sidebarOpen = !state.sidebarOpen;
  sidebar.classList.toggle("collapsed", !state.sidebarOpen);
};

$("newChatBtn").onclick = () => newSession();

debugToggle.onclick = () => {
  state.debugOpen = !state.debugOpen;
  debugPanel.classList.toggle("open", state.debugOpen);
  debugToggle.classList.toggle("active", state.debugOpen);
};

$("debugClose").onclick = () => {
  state.debugOpen = false;
  debugPanel.classList.remove("open");
  debugToggle.classList.remove("active");
};

// ── Init: load sessions from server ────────────────────────────────────────
(async function init() {
  try {
    const res = await fetch("/api/sessions");
    const data = await res.json();
    if (data.sessions && data.sessions.length > 0) {
      state.sessions = data.sessions.map(s => ({ id: s.id, title: s.title, messages: [] }));
      state.activeIdx = 0;
      state.sessionId = state.sessions[0].id;
      topbarTitle.textContent = state.sessions[0].title;
      renderSidebar();
      switchSession(0);
      return;
    }
  } catch {}
  const id = state.sessionId;
  state.sessions.push({ id, title: "New Conversation", messages: [] });
  state.activeIdx = 0;
  renderSidebar();
  showWelcome();
})();
