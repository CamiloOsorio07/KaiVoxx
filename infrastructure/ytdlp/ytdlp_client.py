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
    'allow_unplayable_formats': True,
    'ignore_no_formats_error': True,
}

if COOKIE_FILE:
    YTDL_OPTS['cookiefile'] = COOKIE_FILE


def get_ytdl(no_format: bool = False, no_flat: bool = False):
    opts = dict(YTDL_OPTS)

    if no_format:
        opts.pop('format', None)

    if no_flat:
        opts.pop('extract_flat', None)

    return yt_dlp.YoutubeDL(opts)


def _normalize_url(value):
    if not value:
        return None

    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value

    if isinstance(value, str):
        return f"https://www.youtube.com/watch?v={value}"

    return None


def _extract_valid_stream(info: dict):
    """
    Obtiene SOLO streams de audio válidos.
    Ignora:
    - storyboards
    - thumbnails
    - imágenes
    - formatos sin audio
    """

    formats = info.get('formats') or []

    audio_formats = []

    for f in formats:
        url = f.get('url')

        if not url:
            continue

        # Ignorar imágenes/storyboards
        if "i.ytimg.com" in url:
            continue

        # Ignorar thumbnails jpg/webp/png
        if any(ext in url for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            continue

        # Ignorar formatos sin audio
        if f.get('acodec') == 'none':
            continue

        audio_formats.append(f)

    # Prioridad de formatos
    preferred_exts = ['opus', 'webm', 'm4a', 'mp3', 'ogg']

    for ext in preferred_exts:
        for f in reversed(audio_formats):
            if f.get('ext') == ext and f.get('url'):
                return f['url']

    # Fallback
    for f in reversed(audio_formats):
        if f.get('url'):
            return f['url']

    return None


async def extract_info(search_or_url: str):
    ytdl = get_ytdl()

    return await asyncio.to_thread(
        lambda: ytdl.extract_info(search_or_url, download=False)
    )


async def build_ffmpeg_source(video_url: str):
    before_options = (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    )

    def _get_stream():
        ytdl = get_ytdl(no_format=True, no_flat=True)

        try:
            info = ytdl.extract_info(video_url, download=False)

        except Exception as e:
            raise RuntimeError(
                f"No se pudo extraer info con yt-dlp: {e}"
            )

        if not info:
            raise RuntimeError(
                "No se pudo extraer info con yt-dlp"
            )

        # Resolver playlists/radios
        if isinstance(info, dict) and info.get('entries'):

            resolved = False

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
                    resolved_info = ytdl.extract_info(
                        candidate,
                        download=False
                    )

                    if resolved_info:
                        info = resolved_info
                        resolved = True
                        break

                except Exception:
                    continue

            if not resolved:
                raise RuntimeError(
                    "No se pudo resolver playlist/radio"
                )

        if not isinstance(info, dict):
            raise RuntimeError(
                "yt-dlp devolvió una respuesta inválida"
            )

        stream_url = _extract_valid_stream(info)

        if not stream_url:
            raise RuntimeError(
                "No se obtuvo URL de stream válida"
            )

        headers = info.get('http_headers', {})

        return stream_url, headers

    stream_url, headers = await asyncio.to_thread(_get_stream)

    headers_str = ""

    for k, v in headers.items():
        headers_str += f"{k}: {v}\r\n"

    return discord.FFmpegOpusAudio(
        stream_url,
        before_options=before_options,
        options=f'-vn -headers "{headers_str}"'
    )


async def build_mixed_ffmpeg_source(
    video_url: str,
    tts_path: str
):
    before_options = (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    )

    def _get_stream():
        ytdl = get_ytdl(no_format=True, no_flat=True)

        try:
            info = ytdl.extract_info(video_url, download=False)

        except Exception as e:
            raise RuntimeError(
                f"No se pudo extraer info: {e}"
            )

        if not info:
            raise RuntimeError(
                "No se pudo extraer info"
            )

        # Resolver playlists/radios
        if isinstance(info, dict) and info.get('entries'):

            resolved = False

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
                    resolved_info = ytdl.extract_info(
                        candidate,
                        download=False
                    )

                    if resolved_info:
                        info = resolved_info
                        resolved = True
                        break

                except Exception:
                    continue

            if not resolved:
                raise RuntimeError(
                    "No se pudo resolver playlist/radio"
                )

        stream_url = _extract_valid_stream(info)

        if not stream_url:
            raise RuntimeError(
                "No se obtuvo stream válido"
            )

        headers = info.get("http_headers", {})

        return stream_url, headers

    stream_url, headers = await asyncio.to_thread(_get_stream)

    headers_str = "".join(
        f"{k}: {v}\r\n"
        for k, v in headers.items()
    )

    options = (
        f'-vn '
        f'-headers "{headers_str}" '
        f'-filter_complex '
        f'"[0:a]volume=1.0[a0];'
        f'[1:a]volume=1.4[a1];'
        f'[a0][a1]amix=inputs=2:duration=first:dropout_transition=2" '
        f'-i "{tts_path}"'
    )

    return discord.FFmpegOpusAudio(
        stream_url,
        before_options=before_options,
        options=options
    )