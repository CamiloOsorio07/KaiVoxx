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

    # SOLO para listados
    'extract_flat': 'in_playlist',

    'ignoreerrors': True,
    'skip_download': True,
    'nocheckcertificate': True,

    # Evita crashes por formatos raros
    'allow_unplayable_formats': True,
    'ignore_no_formats_error': True,
}

if COOKIE_FILE:
    YTDL_OPTS['cookiefile'] = COOKIE_FILE


def get_ytdl(
    no_format: bool = False,
    no_flat: bool = False
):
    opts = dict(YTDL_OPTS)

    if no_format:
        opts.pop('format', None)

    if no_flat:
        opts.pop('extract_flat', None)

    return yt_dlp.YoutubeDL(opts)


def _normalize_url(value):
    """
    Convierte IDs de YouTube a URLs válidas.
    """

    if not value:
        return None

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    if value.startswith(("http://", "https://")):
        return value

    # ID de YouTube
    if len(value) >= 10:
        return f"https://www.youtube.com/watch?v={value}"

    return None


def _escape_ffmpeg_headers(headers: dict):
    """
    Escapa headers para FFmpeg.
    """

    if not headers:
        return ""

    headers_str = ""

    for k, v in headers.items():
        headers_str += f"{k}: {v}\r\n"

    return (
        headers_str
        .replace("\\", "\\\\")
        .replace('"', '\\"')
    )


def _extract_valid_stream(info: dict):
    """
    Obtiene SOLO streams de audio válidos.
    """

    if not isinstance(info, dict):
        return None

    formats = info.get('formats') or []

    if not formats:
        return None

    valid_audio_formats = []

    for f in formats:

        if not isinstance(f, dict):
            continue

        url = f.get('url')

        if not url:
            continue

        # Ignorar imágenes/storyboards
        if "i.ytimg.com" in url:
            continue

        # Ignorar thumbnails
        if any(
            ext in url.lower()
            for ext in [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp"
            ]
        ):
            continue

        # Debe tener audio
        if f.get('acodec') == 'none':
            continue

        valid_audio_formats.append(f)

    if not valid_audio_formats:
        return None

    # Prioridad
    preferred_exts = [
        'opus',
        'webm',
        'm4a',
        'mp3',
        'ogg'
    ]

    for ext in preferred_exts:
        for f in reversed(valid_audio_formats):

            if (
                f.get('ext') == ext
                and f.get('url')
            ):
                return f['url']

    # Fallback
    for f in reversed(valid_audio_formats):

        if f.get('url'):
            return f['url']

    return None


async def extract_info(search_or_url: str):
    """Extrae info para canción/playlist/radio.

    IMPORTANTE:
    - Para playlists/mixes queremos usar extract_flat='in_playlist'
      (opción ya definida en YTDL_OPTS) para evitar el procesamiento pesado
      de todos los entries.
    """

    # NO fuerces no_flat=True: queremos que extract_flat='in_playlist' se aplique.
    ytdl = get_ytdl(no_flat=False)

    return await asyncio.to_thread(
        lambda: ytdl.extract_info(
            search_or_url,
            download=False
        )
    )


async def build_ffmpeg_source(video_url: str):

    if not video_url:
        raise RuntimeError(
            "video_url está vacío"
        )

    video_url = _normalize_url(video_url)

    if not video_url:
        raise RuntimeError(
            "No se pudo normalizar video_url"
        )

    before_options = (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    )

    def _get_stream():

        # IMPORTANTE:
        # reproducción SIN extract_flat
        ytdl = get_ytdl(
            no_format=True,
            no_flat=True
        )

        try:
            info = ytdl.extract_info(
                video_url,
                download=False
            )

        except Exception as e:
            raise RuntimeError(
                f"No se pudo extraer info con yt-dlp: {e}"
            )

        if not info:
            raise RuntimeError(
                "No se pudo extraer info con yt-dlp"
            )

        # Resolver playlists/radios/mixes
        if (
            isinstance(info, dict)
            and info.get('entries')
        ):

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

                    if (
                        resolved_info
                        and resolved_info.get('formats')
                    ):
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
                "yt-dlp devolvió respuesta inválida"
            )

        stream_url = _extract_valid_stream(info)

        if not stream_url:
            raise RuntimeError(
                f"No se obtuvo stream válido para: {video_url}"
            )

        headers = info.get(
            'http_headers',
            {}
        )

        return stream_url, headers

    stream_url, headers = await asyncio.to_thread(
        _get_stream
    )

    safe_headers = _escape_ffmpeg_headers(
        headers
    )

    ffmpeg_options = "-vn"

    if safe_headers:
        ffmpeg_options += (
            f' -headers "{safe_headers}"'
        )

    return discord.FFmpegOpusAudio(
        stream_url,
        before_options=before_options,
        options=ffmpeg_options
    )


async def build_mixed_ffmpeg_source(
    video_url: str,
    tts_path: str
):

    if not video_url:
        raise RuntimeError(
            "video_url está vacío"
        )

    video_url = _normalize_url(video_url)

    if not video_url:
        raise RuntimeError(
            "No se pudo normalizar video_url"
        )

    before_options = (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    )

    def _get_stream():

        ytdl = get_ytdl(
            no_format=True,
            no_flat=True
        )

        try:
            info = ytdl.extract_info(
                video_url,
                download=False
            )

        except Exception as e:
            raise RuntimeError(
                f"No se pudo extraer info: {e}"
            )

        if not info:
            raise RuntimeError(
                "No se pudo extraer info"
            )

        # Resolver playlist/radio
        if (
            isinstance(info, dict)
            and info.get('entries')
        ):

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

                    if (
                        resolved_info
                        and resolved_info.get('formats')
                    ):
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
                f"No se obtuvo stream válido para: {video_url}"
            )

        headers = info.get(
            "http_headers",
            {}
        )

        return stream_url, headers

    stream_url, headers = await asyncio.to_thread(
        _get_stream
    )

    safe_headers = _escape_ffmpeg_headers(
        headers
    )

    options = "-vn "

    if safe_headers:
        options += (
            f'-headers "{safe_headers}" '
        )

    options += (
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