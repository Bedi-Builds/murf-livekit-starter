import logging
import sqlite3
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

logger = logging.getLogger("agent")

load_dotenv(".env.local")

DB_PATH = Path(__file__).parent.parent / "caller_memory.db"


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


def make_save_caller_tool(fixed_user_id: str):
    """
    Build a save_caller_info tool with the real participant ID already baked in
    as a closure variable. The LLM never sees or controls user_id, so it can't
    invent one — this is what was breaking memory before.
    """

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

KNOWLEDGE: You know common Indian scam patterns — fake lottery wins, urgent loan offers,
fake job/internship offers asking for upfront payment, OTP/bank detail phishing, fake
delivery/e-commerce links, impersonation calls (posing as a relative, bank, or police), and
investment/chit fund schemes promising guaranteed returns. You do not have real-time access
to verify a specific phone number, company, or website — say so plainly when asked.

LANGUAGE: Mirror the user's language and mixing style. If they speak Hindi, reply in Hindi
using Devanagari script (हिन्दी), never Roman/English letters — this is essential for correct
pronunciation. If they mix Hindi and English (Hinglish), write the Hindi words in Devanagari
and keep English words in Roman script, matching natural code-mixed writing. If they speak in
English, reply fully in English.

GUARDRAILS:
- Never ask the user for their OTP, PIN, account number, or password, under any circumstance.
- Never confirm or promise that a specific scheme, loan, or investment is legitimate — you can
  only point out red flags or their absence.
- Never diagnose a message as 100% safe — always frame it as "no obvious red flags, but verify
  independently."
- If the user asks something outside scam/fraud safety (e.g. medical advice, legal advice,
  unrelated topics), politely decline and say: "That's outside what I can help with — I'm
  focused on helping you stay safe from scams. Please consult the right professional for that."
- If a user seems to be in the middle of an active scam (e.g. being pressured to send money
  right now), prioritize urgency: tell them to stop, not send anything, and verify independently
  before acting.

STYLE: Keep sentences short, spoken, and simple — avoid lists, brackets, or anything that reads
like a webpage. Speak like a calm, patient person, not a document.

MEMORY & PERSONALIZATION:
Before you finish the call, ask: "Should I remember your name and what we discussed today so I can help you better next time?"
- If they say yes, call save_caller_info with their name and the schemes/questions they asked about (just name, schemes_checked, eligibility_answers — nothing else needed).
- If they say no, do NOT save anything.
- Privacy first: never ask for or save account numbers, OTP, passwords, or sensitive bank details.
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
            f"Greet them warmly by name in Devanagari Hindi and briefly reference "
            f"what you last talked about."
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
            voice="Samar",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # Build the save tool with THIS call's real participant ID baked in —
    # the LLM cannot see or override it.
    save_tool = make_save_caller_tool(user_id)

    await session.start(
        agent=Assistant(tools=[save_tool]),
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