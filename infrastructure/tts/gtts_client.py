import io
import os
import asyncio
import logging
import uuid
import requests
import discord
from config.settings import MAX_TTS_CHARS, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

log = logging.getLogger('kaivoxx.tts')


async def speak_text_in_voice(vc: discord.VoiceClient, text: str):
    if not vc or not vc.is_connected():
        log.warning("speak_text_in_voice: VoiceClient no conectado")
        return False

    if len(text) > MAX_TTS_CHARS:
        log.info("Texto demasiado largo para TTS, no se leerá por voz.")
        return False

    clean_text = text.replace("*", "").replace("_", "").replace("`", "")

    def _generate_audio():
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": ELEVENLABS_API_KEY
            }
            data = {
                "text": clean_text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.5
                }
            }
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()
            return io.BytesIO(response.content)
        except Exception:
            log.exception('Error generando TTS con ElevenLabs')
            raise

    try:
        audio_buf = await asyncio.to_thread(_generate_audio)
    except Exception:
        return False

    # nombre temporal único para evitar colisiones si hay TTS concurrentes
    temp_path = f"tts_{vc.guild.id}_{uuid.uuid4().hex}.mp3"

    try:
        with open(temp_path, 'wb') as f:
            f.write(audio_buf.read())

        # Si hay reproducción activa, detenemos la fuente actual y aguardamos que termine.
        if vc.is_playing():
            try:
                vc.stop()
            except Exception:
                log.exception('No se pudo detener la reproducción previa')
            # esperar un corto tiempo a que el ffmpeg/proceso termine y vc deje de reportar playing
            for _ in range(30):  # hasta ~3 segundos
                if not vc.is_playing():
                    break
                await asyncio.sleep(0.1)
            else:
                log.warning("La reproducción previa no terminó tras stop(); procedo de todos modos")

        # función clara para el callback after
        def _after_play(err):
            if err:
                log.exception(f"TTS playback error: {err}")
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                log.exception("No se pudo borrar el archivo TTS tras reproducción")

        source = discord.FFmpegOpusAudio(temp_path)

        try:
            vc.play(source, after=_after_play)
        except Exception:
            # puede ocurrir Already playing audio si la voz no terminó de limpiarse
            log.exception("Error al iniciar la reproducción del TTS (vc.play)")
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return False

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
