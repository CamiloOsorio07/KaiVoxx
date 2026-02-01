import io
import os
import asyncio
import logging
import uuid
from gtts import gTTS
import discord
from config.settings import MAX_TTS_CHARS, TTS_LANGUAGE

log = logging.getLogger('kaivoxx.tts')


def _temp_tts_path(guild_id: int) -> str:
    return f"tts_{guild_id}_{uuid.uuid4().hex}.mp3"


async def speak_text_in_voice(vc: discord.VoiceClient, text: str) -> bool:
    if not vc or not vc.is_connected():
        log.warning("speak_text_in_voice: VoiceClient no conectado")
        return False

    if len(text) > MAX_TTS_CHARS:
        log.info("Texto demasiado largo para TTS")
        return False

    clean_text = text.replace("*", "").replace("_", "").replace("`", "")

    def _generate_audio():
        buf = io.BytesIO()
        gTTS(text=clean_text, lang=TTS_LANGUAGE, slow=False).write_to_fp(buf)
        buf.seek(0)
        return buf

    try:
        audio_buf = await asyncio.to_thread(_generate_audio)
    except Exception:
        log.exception("Error generando TTS")
        return False

    temp_path = _temp_tts_path(vc.guild.id)
    was_playing_music = vc.is_playing()

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_buf.read())

        # Pausar música si está sonando
        if was_playing_music:
            vc.pause()

        def _after_play(err):
            if err:
                log.exception(f"TTS playback error: {err}")
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                log.exception("No se pudo borrar el archivo TTS")

            # Reanudar música
            if was_playing_music and vc.is_connected():
                try:
                    vc.resume()
                except Exception:
                    log.exception("No se pudo reanudar la música")

        vc.play(discord.FFmpegOpusAudio(temp_path), after=_after_play)

        while vc.is_playing() or vc.is_paused():
            await asyncio.sleep(0.1)

        return True

    except Exception:
        log.exception("Error reproduciendo TTS")
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return False
