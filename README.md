# 🛡️ Suraksha Saathi — AI Anti-Fraud Voice Agent

Built for the **#VoiceForBharat 10 Days of AI Voice Agents Challenge** by Murf AI.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Murf Falcon](https://img.shields.io/badge/TTS-Murf%20Falcon-6366F1)](https://murf.ai/api/docs/text-to-speech/streaming) [![LiveKit](https://img.shields.io/badge/Transport-LiveKit-002cf2)](https://docs.livekit.io) [![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?logo=typescript&logoColor=white)](https://www.typescriptlang.org/) [![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)

## 📖 Project Retrospective & Journey
Read the full technical breakdown, architecture details, and my 10-day sprint retrospective on DEV.to:
👉 **[Read the Full Story on DEV.to](PASTE_YOUR_DEVTO_ARTICLE_LINK_HERE)**

---

## ⚡ Key Features
- **Native Hindi Voice**: Powered by **Murf Falcon** with strict Devanagari script rendering for natural pronunciation.
- **Caller Memory**: SQLite persistence with active caller consent logic.
- **Human Escalation**: Live Discord webhook dispatch for urgent fraud intervention (keeping the caller calm on the line).
- **Real-Time Analytics**: Full-stack Flask dashboard tracking live scam metrics, call duration, and threat scores.
- **Multi-Agent Voice Handoff**: Mid-call live voice engine configuration swap, transitioning from a General Guide (*Anisha*) to a strict Fraud Specialist (*Samar*) without dropping the audio graph.

---

## 🛠️ Tech Stack
- **Voice Synthesis:** Murf Falcon 2 API
- **Real-Time WebRTC Pipeline:** LiveKit Agents
- **Reasoning & Tool Calling:** Google Gemini 3.5 Flash
- **Speech-to-Text:** Deepgram Nova-3
- **Analytics Dashboard:** Flask (Python), SQLite, Chart.js, HTML/CSS

---
---

# 🚀 Local Quickstart Guide
*This project was built on top of the Murf LiveKit Starter template. Below are the instructions to run it locally.*

## Architecture

```mermaid
flowchart LR
    A[🎙️ User speaks] -->|audio| B[Deepgram STT]
    B -->|text| C[LLM (Gemini)]
    C -->|response text| D[Murf Falcon TTS]
    D -->|audio| E[LiveKit]
    E -->|stream| F[🔊 User hears]

    style A fill:#444441,stroke:#888780,color:#fff
    style B fill:#185FA5,stroke:#85B7EB,color:#fff
    style C fill:#534AB7,stroke:#AFA9EC,color:#fff
    style D fill:#0F6E56,stroke:#5DCAA5,color:#fff
    style E fill:#D85A30,stroke:#F0997B,color:#fff
    style F fill:#444441,stroke:#888780,color:#fff
