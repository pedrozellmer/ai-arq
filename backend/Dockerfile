FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema (ODA File Converter para DWG→DXF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    libfreetype6 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Instalar ODA File Converter (converte DWG→DXF silenciosamente)
RUN wget -q -O /tmp/oda.deb "https://download.opendesign.com/guestfiles/ODAFileConverter/ODAFileConverter_QT6_lnxX64_8.3dll_25.12.deb" \
    && dpkg -i /tmp/oda.deb || apt-get install -f -y \
    && rm /tmp/oda.deb \
    || echo "ODA install failed - DWG support will be unavailable, PDF/DXF still work"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
