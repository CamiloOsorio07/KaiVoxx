# KaiVoxx 🎧🤖

KaiVoxx es un **bot de Discord** enfocado en la reproducción de música, desarrollado en **Python**, que nace como una refactorización completa de mi bot anterior (`BOT-KAIVOXX`).

El objetivo principal de este proyecto fue **ordenar el código, hacerlo más mantenible y escalable**, sin perder ninguna de las funcionalidades que ya tenía el bot original.

Actualmente el bot está estructurado siguiendo una **arquitectura limpia**, separando responsabilidades y facilitando futuras mejoras.

---

## ✨ Características

* Reproducción de música en Discord.
* IA basica.
* Manejo de colas.
* Integración con YouTube (usando `yt-dlp`).
* Soporte para cookies y proxies cuando es necesario.
* Código modular y organizado por capas.
* Preparado para despliegue en Railway / Nixpacks.

---

## 🧱 Estructura del proyecto

El proyecto está organizado de la siguiente forma:

```
KaiVoxx/
├── main.py                # Punto de entrada del bot
├── config/                # Configuración y variables globales
├── domain/                # Lógica de negocio y entidades
├── integration/           # Integraciones externas (YouTube, cookies, proxies, etc.)
├── infrastructure/        # Implementaciones concretas y utilidades
├── tests/
│   └── unit/              # Pruebas unitarias
├── requirements.txt       # Dependencias del proyecto
├── railway.toml           # Configuración para Railway
├── nixpacks.toml          # Configuración para Nixpacks
└── README.md
```

---

## ⚙️ Requisitos

* Python **3.10 o superior**.
* `ffmpeg` instalado y disponible en el PATH.
* Dependencias Python instaladas desde `requirements.txt`.

---

## 🔐 Variables de entorno

Antes de ejecutar el bot, es necesario configurar las variables de entorno.

Las principales son:

```env
DISCORD_TOKEN=tu_token_de_discord
GROQ_API_KEY=tu_api_key (si aplica)
YTDLP_COOKIES=ruta_o_valor_de_cookies
YT_PROXY=http://usuario:contraseña@ip:puerto
```

> Algunas variables son opcionales y dependen de si necesitas cookies o proxy para `yt-dlp`.

---

## 🚀 Instalación y ejecución (local)

1. Clonar el repositorio:

```bash
git clone https://github.com/CamiloOsorio07/KaiVoxx.git
cd KaiVoxx
```

2. Crear y activar entorno virtual:

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.\.venv\Scripts\activate
```

3. Instalar dependencias:

```bash
pip install -r requirements.txt
```

4. Configurar las variables de entorno.

5. Ejecutar el bot:

```bash
python main.py
```

---

## ☁️ Despliegue

El proyecto está listo para ser desplegado en **Railway**, ya que incluye los archivos `railway.toml` y `nixpacks.toml`.

Solo es necesario:

* Configurar las variables de entorno en la plataforma.
* Verificar que `ffmpeg` esté disponible en el entorno de ejecución.

---

## 🧪 Pruebas

Las pruebas unitarias se encuentran en:

```
tests/unit/
```

Para ejecutarlas:

```bash
pytest
```

---

## 🛠️ Problemas comunes

* **ffmpeg no encontrado** → Asegúrate de que esté instalado y en el PATH.
* **Errores 403 con YouTube** → Normalmente se solucionan usando cookies actualizadas o un proxy.

---

## 📌 Notas finales

Este proyecto sigue en evolución. La estructura actual permite agregar nuevas funcionalidades sin romper el código existente.

Cualquier mejora, refactor o idea es bienvenida.

---

## 📄 Licencia

Este proyecto puede ser usado con fines educativos y personales.

---

## 👤 Autor

**Camilo Andrés Osorio Mejía**
Estudiante de Ingeniería en Sistemas / Informática
