import sys
import os
import logging
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

# Force Python to look in the main 'backend' folder
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv

# Import from your EXACT filename: srcanalytics.py
from srcanalytics import log_call, init_analytics_db

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    tokenize,
    room_io,
)
from livekit.agents.llm import function_tool
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

DB_PATH = Path(__file__).parent.parent / "caller_memory.db"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1537029496706699284/P4B9bHhAEF8xqXXvjVDLBn-Bujg-D4NxShBxb5OKAbKFVlinxPwVXP9IjDdomkRbBiDh"

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS callers (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            language_preference TEXT DEFAULT 'hi',
            schemes_checked TEXT,
            eligibility_answers TEXT,
            last_interaction TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_database()

# ---------------------------------------------------------
# TOOLS FOR THE AGENT
# ---------------------------------------------------------
@function_tool
async def alert_human_agent(reason: str) -> str:
    """Alert a human fraud specialist via Discord when the user asks for a human, manager, or reports an urgent active loss/scam."""
    try:
        requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": f"🚨 **URGENT: Human Escalation Needed!**\n**Reason:** {reason}"
            },
            timeout=5,
        )
        return "Human specialist has been alerted on Discord."
    except Exception as e:
        logger.error(f"Failed to post to Discord: {e}")
        return "Failed to dispatch Discord alert, but continue assisting user."

def make_save_caller_tool(fixed_user_id: str):
    @function_tool
    async def save_caller_info(
        name: str,
        schemes_checked: str = "",
        eligibility_answers: str = "",
    ) -> str:
        """Save the caller's name and what was discussed."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT OR REPLACE INTO callers
            (user_id, name, language_preference, schemes_checked, eligibility_answers, last_interaction, created_at)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM callers WHERE user_id = ?), ?))
            """,
            (fixed_user_id, name, "hi", schemes_checked, eligibility_answers, now, fixed_user_id, now),
        )
        conn.commit()
        conn.close()
        return f"Saved info for {name}."
    return save_caller_info

def make_transfer_tool(tts_engine):
    @function_tool
    async def transfer_to_fraud_specialist() -> str:
        """Use this tool IMMEDIATELY when the user says they are scammed, hacked, or need a specialist."""
        
        # PROPER HOT-SWAP: Modify the Murf API configuration dynamically mid-stream
        # This prevents breaking the LiveKit internal event loop
        try:
            if hasattr(tts_engine, '_opts'):
                tts_engine._opts.voice = "Samar"
            elif hasattr(tts_engine, 'voice'):
                tts_engine.voice = "Samar"
        except Exception as e:
            logger.error(f"Failed to swap voice natively: {e}")

        # Inform the LLM to simultaneously swap its logic persona
        return (
            "TRANSFER SUCCESSFUL. "
            "CRITICAL COMMAND: You MUST instantly change your persona to SAMAR, the Bank Fraud Specialist. "
            "Speak in Hindi. Start your very next sentence by saying: 'नमस्ते, मैं फ्रॉड स्पेशलिस्ट समर बोल रहा हूँ।' "
            "Assume full control and ask for the last 4 digits of the account."
        )
    return transfer_to_fraud_specialist

# ---------------------------------------------------------
# MAIN AGENT SYSTEM PROMPT
# ---------------------------------------------------------
SYSTEM_PROMPT = """
IDENTITY: You are Suraksha Saathi, an independent voice assistant that helps people in India
spot financial scams and fraud. You do not represent any bank, company, or government body —
you are a neutral safety guide.

OBJECTIVES:
1. Help the user determine if a message, call, or offer they received is likely a scam.
2. Explain the reasoning in simple terms so the user understands the red flags themselves.
3. Give a clear, safe next step every time — never leave the user unsure what to do.

HUMAN ESCALATION & HANDOFFS:
- If the user explicitly asks to speak to a human, person, manager, or supervisor, call `alert_human_agent` immediately.
- If the user reports money actively stolen, a hacked account, or a severe financial threat, call `transfer_to_fraud_specialist` immediately to hand them over to the specialist agent.

LANGUAGE & SCRIPT:
Always write every language in its own native script.
- Hindi → Devanagari (नमस्ते), never romanized (never "namaste").
- Same rule for all non-English languages.
If they mix Hindi and English (Hinglish), write Hindi words in Devanagari and keep English words in Roman script.

GUARDRAILS:
- Never ask for OTP, PIN, account number, or password.
- Never confirm a scheme is 100% safe — only point out red flags.
- Keep sentences short, spoken, and simple.

MEMORY & PERSONALIZATION:
Before you finish the call, ask: "Should I remember your name and what we discussed today so I can help you better next time?"
- If yes, call save_caller_info with their name and what you discussed.
- If no, do NOT save anything.
"""

class Assistant(Agent):
    def __init__(self, tools: list, instructions: str | None = None) -> None:
        super().__init__(
            instructions=instructions or SYSTEM_PROMPT,
            tools=tools,
        )

server = AgentServer()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    await ctx.connect()
    call_start_time = datetime.now().isoformat()
    call_id = ctx.room.name  
    participant = await ctx.wait_for_participant()
    user_id = participant.identity

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM callers WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    
    caller_name = row['name'] if row else "unknown"

    if row:
        greeting_instructions = (
            f"This is a returning caller named {row['name']}. "
            f"Last time you discussed: {row['schemes_checked'] or 'no specific scheme noted'}. "
            f"Greet them warmly by name in Devanagari Hindi and briefly reference what you last talked about."
        )
    else:
        greeting_instructions = (
            "This is a new caller. Greet them warmly in Devanagari Hindi starting with "
            "'नमस्ते', introduce yourself as Suraksha Saathi, and briefly explain what you help with."
        )

    # Instantiate the Murf TTS Engine cleanly
    active_tts_engine = murf.TTS(
        voice="Anisha",
        style="Conversation",
        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
        text_pacing=True,
    )

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=google.LLM(model="gemini-3.5-flash-lite"),
        tts=active_tts_engine, # Attach the exact engine
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # Initialize all three tools properly
    save_tool = make_save_caller_tool(user_id)
    transfer_tool = make_transfer_tool(active_tts_engine)

    await session.start(
        agent=Assistant(tools=[save_tool, alert_human_agent, transfer_tool]),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    await session.generate_reply(instructions=greeting_instructions)
    call_end_time = datetime.now().isoformat()
    duration = (datetime.fromisoformat(call_end_time) - datetime.fromisoformat(call_start_time)).total_seconds()
    
    log_call(call_id, caller_name, call_start_time, call_end_time, int(duration), "completed")

if __name__ == "__main__":
    cli.run_app(server)