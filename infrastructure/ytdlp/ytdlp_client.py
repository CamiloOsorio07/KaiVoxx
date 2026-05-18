import asyncio
import yt_dlp
import discord
from config.settings import COOKIE_FILE

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'extract_flat': 'in_playlist',
    'ignoreerrors': True,
    'skip_download': True,
    'nocheckcertificate': True,
}

if COOKIE_FILE:
    YTDL_OPTS['cookiefile'] = COOKIE_FILE


def get_ytdl(no_format: bool = False):
    opts = dict(YTDL_OPTS)
    if no_format:
        opts.pop('format', None)
    return yt_dlp.YoutubeDL(opts)


def _normalize_url(value):
    if not value:
        return None
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, str):
        return f"https://www.youtube.com/watch?v={value}"
    return None


async def extract_info(search_or_url: str):
    ytdl = get_ytdl()
    return await asyncio.to_thread(lambda: ytdl.extract_info(search_or_url, download=False))


async def build_ffmpeg_source(video_url: str):
    before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

    def _get_stream():
        # Importante: sin 'format' aquí, para que yt-dlp no falle antes de que
        # podamos elegir manualmente un stream válido.
        ytdl = get_ytdl(no_format=True)

        info = ytdl.extract_info(video_url, download=False)
        if not info:
            raise RuntimeError("No se pudo extraer info con yt-dlp")

        # Si viene como playlist/radio, resolver el primer entry válido
        if isinstance(info, dict) and info.get('entries'):
            resolved_url = None

            for entry in info['entries'] or []:
                if not isinstance(entry, dict):
                    continue

                candidate = _normalize_url(
                    entry.get('webpage_url')
                    or entry.get('url')
                    or entry.get('id')
                )

                if not candidate:
                    continue

                try:
                    resolved_info = ytdl.extract_info(candidate, download=False)
                    if resolved_info:
                        info = resolved_info
                        resolved_url = candidate
                        break
                except Exception:
                    continue

            if not resolved_url:
                raise RuntimeError("No se pudo resolver un entry válido (playlist/radio)")

        if not isinstance(info, dict):
            raise RuntimeError("yt-dlp devolvió una respuesta inválida")

        stream_url = None

        if isinstance(info.get('url'), str) and info.get('url'):
            stream_url = info['url']
        else:
            # Primero intenta requested_formats
            requested_formats = info.get('requested_formats') or []
            for f in reversed(requested_formats):
                if f.get('url'):
                    stream_url = f['url']
                    break

            # Luego formatos normales
            if not stream_url:
                formats = info.get('formats') or []
                for f in reversed(formats):
                    if (
                        f.get('acodec') != 'none'
                        and f.get('url')
                        and f.get('ext') in ('m4a', 'webm', 'opus', 'ogg', 'mp3')
                    ):
                        stream_url = f['url']
                        break

            # Último fallback: cualquier formato con URL
            if not stream_url:
                for f in reversed(info.get('formats') or []):
                    if f.get('url'):
                        stream_url = f['url']
                        break

        if not stream_url:
            raise RuntimeError('No se obtuvo URL de stream válida')

        headers = info.get('http_headers', {})
        return stream_url, headers

    stream_url, headers = await asyncio.to_thread(_get_stream)

    headers_str = ''
    for k, v in headers.items():
        headers_str += f"{k}: {v}\r\n"

    return discord.FFmpegOpusAudio(
        stream_url,
        before_options=before_options,
        options=f'-headers "{headers_str}"'
    )


async def build_mixed_ffmpeg_source(video_url: str, tts_path: str):
    """
    Mezcla música actual + voz IA sin cortar la canción
    """
    before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

    def _get_stream():
        ytdl = get_ytdl(no_format=True)
        info = ytdl.extract_info(video_url, download=False)
        if not info:
            raise RuntimeError("No se pudo extraer info")

        if isinstance(info, dict) and info.get('entries'):
            resolved_url = None

            for entry in info['entries'] or []:
                if not isinstance(entry, dict):
                    continue

                candidate = _normalize_url(
                    entry.get('webpage_url')
                    or entry.get('url')
                    or entry.get('id')
                )

                if not candidate:
                    continue

                try:
                    resolved_info = ytdl.extract_info(candidate, download=False)
                    if resolved_info:
                        info = resolved_info
                        resolved_url = candidate
                        break
                except Exception:
                    continue

            if not resolved_url:
                raise RuntimeError("No se pudo resolver un entry válido (playlist/radio)")

        stream_url = None
        if isinstance(info.get("url"), str) and info.get("url"):
            stream_url = info["url"]
        else:
            for f in reversed(info.get("requested_formats") or []):
                if f.get("url"):
                    stream_url = f["url"]
                    break

            if not stream_url:
                for f in reversed(info.get("formats", [])):
                    if f.get("acodec") != "none" and f.get("url"):
                        stream_url = f["url"]
                        break

            if not stream_url:
                for f in reversed(info.get("formats") or []):
                    if f.get("url"):
                        stream_url = f["url"]
                        break

        if not stream_url:
            raise RuntimeError("No se obtuvo stream válido")

        headers = info.get("http_headers", {})
        return stream_url, headers

    stream_url, headers = await asyncio.to_thread(_get_stream)

    headers_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())

    options = (
        f'-headers "{headers_str}" '
        f'-filter_complex '
        f'"[0:a]volume=1.0[a0];'
        f'[1:a]volume=1.4[a1];'
        f'[a0][a1]amix=inputs=2:duration=first:dropout_transition=2"'
        f' -i "{tts_path}"'
    )

    return discord.FFmpegOpusAudio(
        stream_url,
        before_options=before_options,
        options=options
    )