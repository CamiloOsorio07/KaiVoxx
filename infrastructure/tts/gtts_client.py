import io, os, asyncio, logging
from gtts import gTTS
import discord
from config.settings import MAX_TTS_CHARS, TTS_LANGUAGE

log = logging.getLogger('kaivoxx.tts')

async def speak_text_in_voice(vc: discord.VoiceClient, text: str):
    if not vc or not vc.is_connected():
        log.warning("speak_text_in_voice: VoiceClient no conectado")
        return False
    if len(text) > MAX_TTS_CHARS:
        log.info("Texto demasiado largo para TTS, no se leerá por voz.")
        return False
    clean_text = text.replace("*","" ).replace("_","" ).replace("`","")

    def _generate_audio():
        buf = io.BytesIO()
        try:
            gTTS(text=clean_text, lang=TTS_LANGUAGE, slow=False).write_to_fp(buf)
            buf.seek(0)
            return buf
        except Exception:
            log.exception('Error generando TTS')
            raise

    try:
        audio_buf = await asyncio.to_thread(_generate_audio)
    except Exception:
        return False

    temp_path = f"tts_{vc.guild.id}.mp3"
    try:
        with open(temp_path, 'wb') as f:
            f.write(audio_buf.read())
        if vc.is_playing():
            try:
                vc.stop()
            except Exception:
                log.exception('No se pudo detener la reproducción previa')
        source = discord.FFmpegOpusAudio(temp_path)
        vc.play(source, after=lambda e: (log.exception(f"TTS playback error: {e}") if e else None, os.remove(temp_path) if os.path.exists(temp_path) else None))
        while vc.is_playing() or vc.is_paused():
            await asyncio.sleep(0.1)
        return True
    except Exception:
        log.exception('Error reproduciendo TTS')
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return False
