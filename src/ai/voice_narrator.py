import os
import logging
import requests
from typing import Optional
from pathlib import Path
from src.config import ELEVENLABS_API_KEY, AUDIO_OUTPUT_DIR

logger = logging.getLogger("Aegis.Voice")

class VoiceNarrator:
    """
    Synthesizes institutional morning / execution market briefings
    using ElevenLabs TTS API.
    """
    def __init__(self):
        self.api_key = ELEVENLABS_API_KEY
        # High quality institutional voice ID (e.g. 'Adam' or 'George')
        self.voice_id = "pNInz6obpgDQGcFmaJgB" # Adam - professional executive voice
        self.audio_dir = AUDIO_OUTPUT_DIR

    def generate_speech(self, text: str, filename: str = "latest_briefing.mp3") -> Optional[str]:
        """
        Generates MP3 audio from text and saves to static/audio directory.
        Returns the relative URL path or None if failed.
        """
        if not self.api_key:
            logger.warning("No ELEVENLABS_API_KEY found. Skipping voice audio synthesis.")
            return None

        output_path = self.audio_dir / filename
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.55,
                "similarity_boost": 0.80,
                "style": 0.20,
                "use_speaker_boost": True
            }
        }
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=20)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"Generated ElevenLabs audio briefing saved to {output_path}")
                return f"/audio/{filename}"
            else:
                logger.warning(f"ElevenLabs TTS returned error {resp.status_code}: {resp.text}")
                return None
        except Exception as e:
            logger.warning(f"Failed to generate ElevenLabs audio: {e}")
            return None

voice_narrator = VoiceNarrator()
