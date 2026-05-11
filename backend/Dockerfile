FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema incluindo Qt pra ODA
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    libqt6core6 \
    libqt6gui6 \
    libqt6widgets6 \
    qt6-base-dev \
    libgl1 \
    libglib2.0-0 \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/* \
    || (apt-get update && apt-get install -y --no-install-recommends \
    wget libgl1 libglib2.0-0 xvfb \
    && rm -rf /var/lib/apt/lists/*)

# libredwg-tools (fallback open-source pro ODA File Converter) — OPCIONAL.
# Se instalação falhar (ex. pacote indisponível no mirror), build continua;
# código Python (dwg_extractor._try_libredwg_convert) já usa shutil.which
# e pula fallback se binário ausente.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libredwg-tools \
    && rm -rf /var/lib/apt/lists/* \
    || echo "libredwg-tools install failed — fallback DWG converter unavailable"

# Baixar e instalar ODA File Converter
RUN wget -q -O /tmp/oda.deb "https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_lnxX64_8.3dll_27.1.deb" && \
    apt-get update && \
    dpkg -i /tmp/oda.deb || apt-get install -f -y --no-install-recommends && \
    rm -f /tmp/oda.deb && \
    rm -rf /var/lib/apt/lists/* || \
    echo "ODA install failed"

# xvfb-run vai criar o display virtual automaticamente
# NÃO setar QT_QPA_PLATFORM=offscreen — deixar usar xcb com xvfb

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
