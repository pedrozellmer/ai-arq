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
    && ldconfig \
    && rm -rf /var/lib/apt/lists/* \
    || (apt-get update && apt-get install -y --no-install-recommends \
    wget libgl1 libglib2.0-0 xvfb \
    libpango-1.0-0 libpangoft2-1.0-0 fontconfig \
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

# Fontes dos templates via Google Fonts (Inter, Space Grotesk, Instrument Serif,
# IBM Plex Sans/Mono). Tudo por wget (não depende de pacote apt) e tolerante a
# falha: se uma fonte não baixar, o build segue e o WeasyPrint cai pra fallback.
RUN mkdir -p /usr/share/fonts/truetype/aiarq && cd /usr/share/fonts/truetype/aiarq \
    && GH="https://github.com/google/fonts/raw/main/ofl" \
    && for u in \
        "inter/Inter%5Bopsz,wght%5D.ttf|Inter.ttf" \
        "spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf|SpaceGrotesk.ttf" \
        "instrumentserif/InstrumentSerif-Regular.ttf|InstrumentSerif-Regular.ttf" \
        "instrumentserif/InstrumentSerif-Italic.ttf|InstrumentSerif-Italic.ttf" \
        "ibmplexsans/IBMPlexSans-Regular.ttf|IBMPlexSans-Regular.ttf" \
        "ibmplexsans/IBMPlexSans-Medium.ttf|IBMPlexSans-Medium.ttf" \
        "ibmplexsans/IBMPlexSans-SemiBold.ttf|IBMPlexSans-SemiBold.ttf" \
        "ibmplexsans/IBMPlexSans-Bold.ttf|IBMPlexSans-Bold.ttf" \
        "ibmplexmono/IBMPlexMono-Regular.ttf|IBMPlexMono-Regular.ttf" \
        "ibmplexmono/IBMPlexMono-Medium.ttf|IBMPlexMono-Medium.ttf" \
        "ibmplexmono/IBMPlexMono-SemiBold.ttf|IBMPlexMono-SemiBold.ttf" \
        ; do src="${u%%|*}"; dst="${u##*|}"; wget -q --tries=2 --timeout=25 "$GH/$src" -O "$dst" || echo "font fail: $src"; done \
    && fc-cache -f || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
