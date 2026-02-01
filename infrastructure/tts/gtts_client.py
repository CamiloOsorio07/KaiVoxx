import io
import os
import asyncio
import logging
import uuid
from gtts import gTTS
import discord
from config.settings import MAX_TTS_CHARS, TTS_LANGUAGE

log = logging.getLogger('kaivoxx.tts')

# Nombre temporal por guild (se usa uuid por seguridad si se ejecutan varias TTS en paralelo)
def _temp_tts_path(guild_id: int) -> str:
    return f"tts_{guild_id}_{uuid.uuid4().hex}.mp3"

async def speak_text_in_voice(vc: discord.VoiceClient, text: str):
    """
    Genera TTS y lo reproduce en vc.
    Si hay música en la cola, intenta mezclar la música actual con el TTS usando FFmpeg
    (requiere que exista `build_mixed_ffmpeg_source` en infrastructure.audio.ytdl_source).
    """
    if not vc or not vc.is_connected():
        log.warning("speak_text_in_voice: VoiceClient no conectado")
        return False

    if len(text) > MAX_TTS_CHARS:
        log.info("Texto demasiado largo para TTS, no se leerá por voz.")
        return False

    # limpiar caracteres que pueden romper la generación TTS
    clean_text = text.replace("*", "").replace("_", "").replace("`", "")

    def _generate_audio_bytesio():
        buf = io.BytesIO()
        try:
            gTTS(text=clean_text, lang=TTS_LANGUAGE, slow=False).write_to_fp(buf)
            buf.seek(0)
            return buf
        except Exception:
            log.exception('Error generando TTS')
            raise

    try:
        audio_buf = await asyncio.to_thread(_generate_audio_bytesio)
    except Exception:
        return False

    temp_path = _temp_tts_path(vc.guild.id)
    try:
        # Guardar TTS en disco (ffmpeg necesita un fichero para la mezcla)
        with open(temp_path, 'wb') as f:
            f.write(audio_buf.read())

        # Intentar mezclar si hay música en la cola
        try:
            from integration.queue_shim import music_queues
            from infrastructure.audio.ytdl_source import build_mixed_ffmpeg_source
        except Exception:
            # Si los imports fallan, seguimos con TTS simple
            music_queues = None
            build_mixed_ffmpeg_source = None

        mixed_played = False

        if music_queues and build_mixed_ffmpeg_source:
            guild_id = vc.guild.id
            queue = music_queues.get(guild_id)
            # Si hay canción actual y el bot está reproduciendo, usamos mezcla
            if queue and getattr(queue, "current", None) and vc.is_playing():
                try:
                    # build_mixed_ffmpeg_source debe devolver una FFmpegOpusAudio preparada
                    source = await build_mixed_ffmpeg_source(queue.current.url, temp_path)

                    def _after_play(err):
                        if err:
                            log.exception(f"TTS mixed playback error: {err}")
                        # eliminar fichero TTS al terminar
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception:
                            log.exception("No se pudo borrar el archivo TTS tras mezcla")

                    vc.play(source, after=_after_play)
                    mixed_played = True
                except Exception:
                    log.exception("Error intentando reproducir TTS mezclado. Haré fallback a TTS simple.")

        # Si no se reprodujo la mezcla (no hay música o fallo), reproducir TTS solo
        if not mixed_played:
            def _after_play_simple(err):
                if err:
                    log.exception(f"TTS playback error: {err}")
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    log.exception("No se pudo borrar el archivo TTS tras reproducción simple")

            # IMPORTANT: no detenemos la reproducción previa manualmente aquí
            source = discord.FFmpegOpusAudio(temp_path)
            vc.play(source, after=_after_play_simple)

        # esperar a que termine la reproducción de la TTS actual (mezclada o simple)
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
