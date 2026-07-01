# Mini Agent

A browser-based AI assistant with **tool calling**, **session-based memory**, **streaming responses**, and a **ReAct-style agent loop**.

It is built with a Python backend, a vanilla HTML/CSS/JavaScript frontend, and Groq-hosted Llama models.

---

## What it does

Mini Agent lets you:

- chat with an assistant
- ask follow-up questions in the same conversation
- switch between saved conversations
- rename or delete chats
- stream answers token by token
- inspect tool-use traces in a debug panel
- use tools such as calculator, weather, and web search through the agent

The assistant keeps memory per conversation session, not globally across all chats. New conversations start with fresh history, while existing sessions can be restored from storage. 

---

## Features

- **Session-based chat memory** with a sliding window of messages
- **Conversation persistence** through stored session messages
- **Streaming responses** using Server-Sent Events
- **Tool calling** through a ReAct-style agent
- **Two execution modes**
  - graph-based execution for `run()`
  - manual loop for `run_stream()`
- **Fallback model support** if the primary Groq model fails
- **Markdown rendering** and **syntax highlighting** in the UI
- **Debug trace panel** for viewing reasoning, actions, and observations
- **Conversation management**: new chat, switch chat, rename, delete

These behaviors are all visible in the agent, memory, UI, and model-loading code. 

---

## Tech stack

**Backend**
- Python
- Flask
- LangChain message objects
- Groq models via `langchain_groq`

**Frontend**
- HTML
- CSS
- Vanilla JavaScript
- `marked` for Markdown rendering
- `DOMPurify` for sanitizing rendered HTML
- `highlight.js` for code highlighting

**Storage**
- Session storage with persistent message loading/saving

The frontend dependencies and rendering pipeline are visible in `app.js`, and the model configuration is visible in `src/llm.py`. 

---

## How it works

### Request flow

1. The user types a message in the browser.
2. The frontend sends the message to `/api/chat/stream`.
3. The backend loads the session memory.
4. The agent builds a ReAct prompt with conversation history.
5. The agent either answers directly or calls a tool.
6. The response is streamed back to the browser.
7. The UI renders the answer and the trace.

The frontend sends the same `session_id` for all messages in a conversation, loads prior sessions from the server, and supports switching between chats. 

### Agent flow

Mini Agent supports two execution paths:

- `run()` uses a graph-based backend when `use_graph=True`
- `run_stream()` uses a manual loop for token-level streaming

Both paths build the prompt from `build_react_prompt(...)` and append the conversation history from `memory.get_messages()`. 

### LLM flow

The primary model is:

- `llama-3.3-70b-versatile`

The fallback model is:

- `llama-3.1-8b-instant`

Both are Groq-backed models. The fallback is used only if the primary model call fails. :contentReference[oaicite:6]{index=6}

---

## Project structure

```text
mini-agent/
├── server.py
├── src/
│   ├── agent.py
│   ├── llm.py
│   ├── memory.py
│   ├── prompts.py
│   ├── registry.py
│   ├── executor.py
│   ├── retry.py
│   ├── storage.py
│   └── ...
└── ui/
    ├── index.html
    ├── app.js
    └── style.css
```

---

## Conversation model

This app uses **per-session memory**.

That means:

- messages inside the same chat session are remembered
- a new chat starts with fresh memory
- different sessions do not share history automatically

The frontend creates a new `sessionId` for each conversation, and the backend uses that ID to load and save messages for that session. 

---

## Setup

### 1. Install dependencies

Install the Python dependencies listed in your project.

### 2. Configure environment variables

Create a `.env` file and add your Groq API key:

```env
GROQ_API_KEY=your_api_key_here
```

Optional model overrides:

```env
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FALLBACK_MODEL=llama-3.1-8b-instant
```

### 3. Run the backend

```bash
python server.py
```

### 4. Open the app

Visit the local URL printed by Flask in the browser.

---

## Notes

- This project is a **session-based assistant**, not a global-memory assistant.
- It does **not** store long-term user facts across all chats yet.
- It does **not** claim to be a fully autonomous general-purpose agent.
- The streaming path uses a manual loop so tokens can be shown in real time. 

---

## Example tools

The UI mentions:
- weather
- calculator
- web search

The agent trace panel also labels these tool categories in the UI. 

 