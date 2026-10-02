# ══════════════════════════════════════════════════════════════════════════
# ESTÁGIO 1 — compilar o LibreDWG (conversor DWG→DXF livre, GPL-3.0-or-later)
# ══════════════════════════════════════════════════════════════════════════
# 🚨 Por que compilar em vez de apt-get: o Debian NÃO empacota o libredwg
# (packages.debian.org devolve vazio). O antigo `apt-get install libredwg-tools
# || echo "install failed"` falhava SEMPRE, em silêncio, e o build seguia limpo —
# então o "fallback" de DWG nunca existiu. Confirmado em 29/07/2026:
# /api/debug/dwg devolvia libredwg_which=null em produção.
#
# GPL não contamina o backend: o dwg2dxf é chamado como PROGRAMA SEPARADO por
# subprocess (dwg_extractor._try_libredwg_convert), não linkado. É GPL, não AGPL,
# então rodar em servidor também não obriga a publicar fonte.
# O tarball de RELEASE já vem com ./configure pronto — não precisa autogen/autotools.
# --disable-bindings tira SWIG/Perl/Python-dev do build.
# Estático (--disable-shared): sai um dwg2dxf que não precisa levar .so junto pra
# imagem final. `test -x` no fim garante que o binário existe mesmo — se não
# existir, o build quebra AQUI, que é onde a gente quer descobrir.
FROM python:3.11-slim AS libredwg-build
ARG LIBREDWG_VERSION=0.14
# 🪤 gperf, libtool, pkg-config e texinfo NÃO vêm no build-essential, e o
# configure.ac procura por eles (AC_CHECK_PROGS). Faltar gperf foi o suspeito
# nº1 da 1ª tentativa, que quebrou o build no Render em 29/07.
# Compila só `src` (a lib) e `programs` (onde mora o dwg2dxf): o `make` puro
# também compila `examples` e `test`, que não usamos e que só somam tempo de
# build e chance de quebrar. -j2 em vez de nproc porque a máquina de build tem
# RAM limitada e paralelismo demais estoura.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gperf libtool pkg-config texinfo perl \
        wget ca-certificates libpcre2-dev \
    && wget -q --tries=3 --timeout=60 -O /tmp/libredwg.tar.gz \
       "https://github.com/LibreDWG/libredwg/releases/download/${LIBREDWG_VERSION}/libredwg-${LIBREDWG_VERSION}.tar.gz" \
    && tar xzf /tmp/libredwg.tar.gz -C /tmp \
    && cd "/tmp/libredwg-${LIBREDWG_VERSION}" \
    && ./configure --disable-bindings --disable-shared --enable-static --disable-docs \
    && make -j2 -C src \
    && make -j2 -C programs \
    && (install -m 755 programs/dwg2dxf /usr/local/bin/dwg2dxf 2>/dev/null \
        || install -m 755 programs/.libs/dwg2dxf /usr/local/bin/dwg2dxf) \
    && test -x /usr/local/bin/dwg2dxf \
    && (strip /usr/local/bin/dwg2dxf || true)


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
    libpcre2-8-0 \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/* \
    || (apt-get update && apt-get install -y --no-install-recommends \
    wget libgl1 libglib2.0-0 xvfb \
    libpango-1.0-0 libpangoft2-1.0-0 fontconfig libpcre2-8-0 \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*)

# LibreDWG: traz só o binário do estágio de compilação acima.
# 🪤 SEM `|| echo`: se o dwg2dxf não vier, o build DEVE quebrar. Foi justamente o
# "falha em silêncio" que escondeu por meses que o fallback não existia. Build que
# falha mantém o deploy anterior no ar — é o modo seguro de errar.
COPY --from=libredwg-build /usr/local/bin/dwg2dxf /usr/local/bin/dwg2dxf
RUN test -x /usr/local/bin/dwg2dxf && (dwg2dxf --version 2>&1 | head -1 || true)

# Baixar e instalar ODA File Converter
# 🩸 02/10/2026: o arquivo "…_8.3dll_27.1.deb" saiu do site (404) e o build do
# d5b1c55 subiu SEM ODA (o RUN é tolerante: "ODA install failed"), com /health
# dizendo dwg=false. O nome atual na página de downloads é "…_11dll.deb"; o
# antigo fica como 2ª tentativa. Sem ODA o DWG vai direto pro LibreDWG.
RUN (wget -q -O /tmp/oda.deb "https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_lnxX64_11dll.deb" \
     || wget -q -O /tmp/oda.deb "https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_lnxX64_8.3dll_27.1.deb") && \
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
# 🩸 27/09/2026 — "tolerante a falha" deixava LIXO: `wget -O arquivo` cria o
# arquivo ANTES de baixar, e as 4 URLs estáticas da IBM Plex Sans passaram a dar
# 404 (a família virou fonte variável no repositório) — 4 .ttf de 0 byte na pasta
# de fontes do sistema desde 14/07. É a data em que o ODA passou a recusar DWG
# (0 falhas em 167 antes; 101 de 105 desde 14/09, sempre "AcDbTextStyleTableRecord"
# — o registro de ESTILO DE TEXTO, que é onde o leitor mexe com fonte). Hipótese
# forte, provada só depois do deploy (o log `libredwg:usado-no-fluxo` tem que cair).
# Agora: a variável no lugar das 4 estáticas, só entra fonte que baixou inteira,
# e nenhum .ttf vazio sobra.
RUN mkdir -p /usr/share/fonts/truetype/aiarq && cd /usr/share/fonts/truetype/aiarq \
    && GH="https://github.com/google/fonts/raw/main/ofl" \
    && for u in \
        "inter/Inter%5Bopsz,wght%5D.ttf|Inter.ttf" \
        "spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf|SpaceGrotesk.ttf" \
        "instrumentserif/InstrumentSerif-Regular.ttf|InstrumentSerif-Regular.ttf" \
        "instrumentserif/InstrumentSerif-Italic.ttf|InstrumentSerif-Italic.ttf" \
        "ibmplexsans/IBMPlexSans%5Bwdth,wght%5D.ttf|IBMPlexSans.ttf" \
        "ibmplexmono/IBMPlexMono-Regular.ttf|IBMPlexMono-Regular.ttf" \
        "ibmplexmono/IBMPlexMono-Medium.ttf|IBMPlexMono-Medium.ttf" \
        "ibmplexmono/IBMPlexMono-SemiBold.ttf|IBMPlexMono-SemiBold.ttf" \
        ; do src="${u%%|*}"; dst="${u##*|}"; \
             if wget -q --tries=2 --timeout=25 "$GH/$src" -O "/tmp/$dst" && [ -s "/tmp/$dst" ]; \
             then mv "/tmp/$dst" "$dst"; else echo "font fail: $src"; fi; rm -f "/tmp/$dst"; done \
    && find /usr/share/fonts -type f -size 0 -print -delete \
    && fc-cache -f || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# --workers 1 É OBRIGATÓRIO (fix OOM 2026-07-22): sem isso, o Render injeta
# WEB_CONCURRENCY=2 e o uvicorn sobe 2 workers. Cada worker carrega o app +
# catálogos SINAPI/TCPO na RAM (dobra a memória base) E cada um tem seu próprio
# _JOB_SEMAPHORE, o que permite 2 jobs simultâneos — furando a proteção de "1 por
# vez" e somando o pico de memória do processamento. Resultado: estouro dos 4GB e
# crash-loop em projetos com várias pranchas DXF. 1 worker = metade da RAM base +
# 1 job por vez garantido. Concorrência de API continua ok (FastAPI é async).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
