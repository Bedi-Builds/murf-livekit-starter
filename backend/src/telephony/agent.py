import logging
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
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
    function_tool,
    RunContext,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("telephony_agent")

load_dotenv(".env.local")

DB_PATH = Path(__file__).parent.parent.parent / "caller_memory.db"
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


@function_tool
async def alert_human_agent(
    ctx: RunContext,
    reason: str,
) -> str:
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
    """Build a save_caller_info tool with the real participant ID baked in."""

    @function_tool
    async def save_caller_info(
        ctx: RunContext,
        name: str,
        schemes_checked: str = "",
        eligibility_answers: str = "",
    ) -> str:
        """Save the caller's name and what was discussed. Always ask permission first."""
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
        return f"Saved info for {name}. I'll remember this next time you call."

    return save_caller_info


SYSTEM_PROMPT = """
IDENTITY: You are Suraksha Saathi, an independent voice assistant that helps people in India
spot financial scams and fraud. You do not represent any bank, company, or government body —
you are a neutral safety guide.

OBJECTIVES:
1. Help the user determine if a message, call, or offer they received is likely a scam.
2. Explain the reasoning in simple terms so the user understands the red flags themselves.
3. Give a clear, safe next step every time — never leave the user unsure what to do.

HUMAN ESCALATION:
- If the user explicitly asks to speak to a human, person, manager, or supervisor, OR if they are panicked and reporting money actively stolen / account hacked, call `alert_human_agent` immediately.
- Tell them calmly that you have alerted a human specialist who is standing by.

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


class TelephonyAgent(Agent):
    def __init__(self, tools: list, instructions: str | None = None) -> None:
        super().__init__(
            instructions=instructions or SYSTEM_PROMPT,
            tools=tools,
        )


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="telephony-agent")
async def telephony_agent(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    await ctx.connect()
    participant = await ctx.wait_for_participant()
    user_id = participant.identity

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM callers WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()

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

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=google.LLM(model="gemini-3.5-flash-lite"),
        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    save_tool = make_save_caller_tool(user_id)

    await session.start(
        agent=TelephonyAgent(tools=[save_tool, alert_human_agent]),
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


if __name__ == "__main__":
    cli.run_app(server)