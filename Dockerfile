# Usa imagen base con Python 3.12 y ffmpeg
FROM python:3.12-slim

# Instala librerías del sistema requeridas para voz de Discord
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libogg0 \
    libsodium23 \
    && rm -rf /var/lib/apt/lists/*

# Crea entorno virtual
RUN python3 -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copia requirements e instala dependencias Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia código de la aplicación
COPY . .

# Ejecuta el bot
CMD ["python", "main.py"]

