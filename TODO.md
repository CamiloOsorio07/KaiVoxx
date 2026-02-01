# TODO: Implementar ElevenLabs TTS para voz VTuber-like en español latino

- [x] Actualizar requirements.txt para agregar la librería elevenlabs
- [x] Actualizar config/settings.py para agregar ELEVENLABS_API_KEY y ELEVENLABS_VOICE_ID
- [x] Reemplazar el cliente TTS en infrastructure/tts/gtts_client.py para usar ElevenLabs API directa (librería elevenlabs falló, usar requests)
- [x] Actualizar imports en ia_commands.py y bot_client.py (revertidos a gtts_client por error en renombrado)
- [x] Intentar renombrar archivo (falló, mantener gtts_client.py con código ElevenLabs)
- [x] Probar la implementación: Bot se conectó, errores corregidos
