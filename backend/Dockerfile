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
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    fontconfig \
    fonts-ibm-plex \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/* \
    || (apt-get update && apt-get install -y --no-install-recommends \
    wget libgl1 libglib2.0-0 xvfb \
    libpango-1.0-0 libpangoft2-1.0-0 fontconfig fonts-ibm-plex \
    && ldconfig \
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

# WeasyPrint: as libs de sistema (Pango/PangoFT2/fontconfig/fonts-ibm-plex) são
# instaladas no PRIMEIRO bloco apt lá em cima — no estado LIMPO do apt, antes da
# instalação do ODA (que deixa o dpkg inconsistente e fazia esta camada separada
# falhar no build). ldconfig lá popula o cache do linker pro find_library achar o pango.

# Fontes dos templates (Inter, Space Grotesk, Instrument Serif) via Google Fonts.
# IBM Plex Sans/Mono já vêm de fonts-ibm-plex acima. Falha não quebra o build
# (WeasyPrint cai pra fonte padrão; ajustamos depois se faltar).
RUN mkdir -p /usr/share/fonts/truetype/aiarq && cd /usr/share/fonts/truetype/aiarq \
    && GH="https://github.com/google/fonts/raw/main/ofl" \
    && (wget -q --tries=2 --timeout=25 "$GH/inter/Inter%5Bopsz,wght%5D.ttf" -O Inter.ttf || echo "inter fail") \
    && (wget -q --tries=2 --timeout=25 "$GH/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf" -O SpaceGrotesk.ttf || echo "spacegrotesk fail") \
    && (wget -q --tries=2 --timeout=25 "$GH/instrumentserif/InstrumentSerif-Regular.ttf" -O InstrumentSerif-Regular.ttf || echo "instrumentserif fail") \
    && (wget -q --tries=2 --timeout=25 "$GH/instrumentserif/InstrumentSerif-Italic.ttf" -O InstrumentSerif-Italic.ttf || echo "instrumentserif-italic fail") \
    && fc-cache -f || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
