import asyncio
import os
from livekit import api
from dotenv import load_dotenv

load_dotenv(".env.local")

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

async def make_outbound_call(sip_address: str):
    room_name = "fraud-detection-call"
    
    lkapi = api.LiveKitAPI(
        LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET
    )
    
    clean_address = sip_address.replace("sip:", "")
    if "@" in clean_address:
        sip_user, domain = clean_address.split("@")
    else:
        sip_user = clean_address
        domain = "sip.linphone.org"
    
    print(f"Dispatching Agent and Initiating SIP call to '{sip_user}' on domain '{domain}'...")
    
    try:
        # 1. EXPLICITLY DISPATCH THE AGENT TO THE ROOM
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="telephony-agent", # Matches the name in telephony/agent.py
                room=room_name,
            )
        )
        print("Agent dispatched successfully.")

        # 2. CREATE THE SIP OUTBOUND CALL TO LINPHONE
        trunk_config = api.SIPOutboundConfig(
            hostname=domain,
        )
        
        request = api.CreateSIPParticipantRequest(
            trunk=trunk_config,
            sip_number="1000",
            sip_call_to=sip_user,
            room_name=room_name,
            participant_identity="caller",
            participant_name="Linphone User"
        )
        
        participant = await lkapi.sip.create_sip_participant(request)
        print("SIP call dialing! Answer it in Linphone.", participant)
    except Exception as e:
        print(f"Error creating SIP call: {e}")
    finally:
        await lkapi.aclose()

if __name__ == "__main__":
    sip_address = input("Enter SIP address (e.g. sip:japleen@sip.linphone.org): ").strip()
    if sip_address:
        asyncio.run(make_outbound_call(sip_address))