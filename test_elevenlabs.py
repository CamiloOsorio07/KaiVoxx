import io
import requests
import os

# Test script for ElevenLabs TTS API
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "sk_00a12533974b12466dbd8fed0583712ad6b3d8478c66d3a0")  # Using the provided key for testing
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice

def test_elevenlabs_api():
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        data = {
            "text": "Hola, soy Kaivoxx, tu asistente virtual VTuber.",
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()

        # Save test audio
        with open("test_tts.mp3", "wb") as f:
            f.write(response.content)

        print("✅ TTS generado exitosamente. Archivo guardado como test_tts.mp3")
        print(f"📏 Tamaño del archivo: {len(response.content)} bytes")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"❌ Error HTTP: {e.response.status_code} - {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ Error general: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Probando API de ElevenLabs...")
    success = test_elevenlabs_api()
    if success:
        print("🎉 Prueba exitosa: La API de ElevenLabs funciona correctamente.")
    else:
        print("💥 Prueba fallida: Revisar configuración de API.")
