# -*- coding: utf-8 -*-
"""Gerador de imagens profissionais para Instagram — AI.arq.

Usa fotos de arquitetura como fundo + overlay escuro + tipografia Montserrat.
"""
import os
import tempfile
import uuid
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

POST_SIZE = (1080, 1080)

# Paleta
WHITE = (255, 255, 255)
WHITE_90 = (235, 237, 242)
WHITE_50 = (140, 148, 168)
CYAN = (56, 220, 240)
CYAN_SOFT = (90, 205, 230)
INDIGO = (100, 90, 255)

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
FONTS_DIR = os.path.join(ASSETS, "fonts")
PHOTOS_DIR = os.path.join(ASSETS, "photos")
OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "aiarq_jobs", "instagram", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── Fontes ──────────────────────────────────────────

def _f(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    """Montserrat font. weight: Light, Regular, Medium, SemiBold, Bold."""
    path = os.path.join(FONTS_DIR, f"Montserrat-{weight}.ttf")
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        pass
    # Fallback para sistema
    fallbacks = {
        "Bold": ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
        "Light": ["C:/Windows/Fonts/segoeuil.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    }
    for fb in fallbacks.get(weight, fallbacks.get("Bold" if "Bold" in weight else "Light", [])):
        try:
            return ImageFont.truetype(fb, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _tw(text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if font.getbbox(t)[2] <= max_w:
            cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines


def _cx(text, font, w):
    return (w - font.getbbox(text)[2]) // 2


# ── Base visual ─────────────────────────────────────

def _load_photo(name: str) -> Image.Image:
    """Carrega foto, redimensiona para 1080x1080 (crop central)."""
    path = os.path.join(PHOTOS_DIR, name)
    if not os.path.exists(path):
        # Fallback: fundo escuro sólido
        return Image.new("RGB", POST_SIZE, (12, 14, 24))

    img = Image.open(path).convert("RGB")
    # Crop quadrado central
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize(POST_SIZE, Image.LANCZOS)
    return img


def _apply_overlay(img: Image.Image, opacity: float = 0.72, gradient: bool = True) -> Image.Image:
    """Overlay escuro sobre a foto para o texto ficar legível.

    opacity: 0.0 (transparente) a 1.0 (preto total)
    gradient: se True, mais escuro embaixo (onde tem mais texto)
    """
    w, h = img.size
    overlay = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(overlay)

    if gradient:
        for y in range(h):
            # Mais escuro no centro e embaixo, mais claro no topo
            t = y / h
            # Curva: começa suave, escurece mais rápido
            alpha = int(255 * (opacity * 0.6 + opacity * 0.4 * t))
            alpha = min(255, alpha)
            draw.line([(0, y), (w, y)], fill=(8, 10, 20, alpha))
    else:
        draw.rectangle([(0, 0), (w, h)], fill=(8, 10, 20, int(255 * opacity)))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _darken_photo(img: Image.Image, factor: float = 0.4) -> Image.Image:
    """Escurece a foto (0.0=preto, 1.0=original)."""
    enhancer = ImageEnhance.Brightness(img)
    return enhancer.enhance(factor)


def _blur_photo(img: Image.Image, radius: int = 3) -> Image.Image:
    """Blur leve para não competir com o texto."""
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def _gradient_line(draw, x, y, length, height=3):
    start = (100, 90, 255)
    end = (56, 220, 240)
    for i in range(length):
        t = i / max(length - 1, 1)
        r = int(start[0] + (end[0] - start[0]) * t)
        g = int(start[1] + (end[1] - start[1]) * t)
        b = int(start[2] + (end[2] - start[2]) * t)
        draw.rectangle([x + i, y, x + i, y + height - 1], fill=(r, g, b))


def _pill_size(text, font):
    """Retorna (largura, altura) de uma pill sem desenhar."""
    bb = font.getbbox(text)
    tw, th = bb[2], bb[3] - bb[1]
    return tw + 40, th + 18


def _pill(draw, x, y, text, font, bg=(100, 90, 255)):
    bb = font.getbbox(text)
    tw, th = bb[2], bb[3] - bb[1]
    px, py = 20, 9
    draw.rounded_rectangle(
        [x, y, x + tw + px * 2, y + th + py * 2],
        radius=th // 2 + py, fill=bg,
    )
    draw.text((x + px, y + py), text, font=font, fill=WHITE)
    return tw + px * 2, th + py * 2


def _logo(draw, w, h):
    f_ai = _f(34, "Bold")
    f_arq = _f(34, "Light")
    ai_w = f_ai.getbbox("AI")[2]
    arq_w = f_arq.getbbox(".arq")[2]
    x = (w - ai_w - arq_w) // 2
    y = h - 70
    draw.text((x, y), "AI", font=f_ai, fill=WHITE)
    draw.text((x + ai_w, y), ".arq", font=f_arq, fill=CYAN)


def _save(img) -> str:
    fp = os.path.join(OUTPUT_DIR, f"ig_{uuid.uuid4().hex[:8]}.jpg")
    img.save(fp, "JPEG", quality=95)
    return fp


# ══════════════════════════════════════════════════════
#  TEMPLATES — Posts sobre a plataforma
# ══════════════════════════════════════════════════════

def generate_how_it_works() -> str:
    """Post 1: 'Como Funciona' — 3 passos sobre foto de workspace."""
    w, h = POST_SIZE
    img = _load_photo("workspace.jpg")
    img = _blur_photo(img, 4)
    img = _apply_overlay(img, 0.78)
    draw = ImageDraw.Draw(img)

    # Tag
    f_tag = _f(18, "SemiBold")
    pw, _ = _pill_size("COMO FUNCIONA", f_tag)
    _pill(draw, (w - pw) // 2, 60, "COMO FUNCIONA", f_tag)

    # Título
    f_t = _f(52, "Bold")
    t = "Orçamento com IA"
    draw.text((_cx(t, f_t, w), 118), t, font=f_t, fill=WHITE)

    f_sub = _f(24, "Light")
    s = "em 3 passos simples"
    draw.text((_cx(s, f_sub, w), 182), s, font=f_sub, fill=WHITE_50)

    _gradient_line(draw, (w - 60) // 2, 222, 60)

    # Cards
    steps = [
        ("01", "Envie os PDFs", "Faça upload das pranchas do seu projeto"),
        ("02", "IA Analisa Tudo", "Identifica 130+ itens automaticamente"),
        ("03", "Baixe a Planilha", "Receba .xlsx pronto com 16 disciplinas"),
    ]

    card_w = w - 120
    card_h = 150
    y = 260

    for num, title, desc in steps:
        cy = y
        y += card_h + 16

        # Card semi-transparente
        card_overlay = Image.new("RGBA", (card_w, card_h), (15, 18, 35, 200))
        # Arredondar cantos do card
        mask = Image.new("L", (card_w, card_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, card_w, card_h], radius=14, fill=255)
        img.paste(
            Image.alpha_composite(
                Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0)),
                card_overlay,
            ).convert("RGB"),
            (60, cy),
            mask=mask,
        )
        draw = ImageDraw.Draw(img)

        # Número grande
        f_num = _f(52, "Bold")
        draw.text((90, cy + 20), num, font=f_num, fill=CYAN)

        # Barra vertical
        _gradient_line(draw, 170, cy + 25, 3, height=80)

        # Textos
        f_title = _f(30, "SemiBold")
        f_desc = _f(22, "Light")
        draw.text((190, cy + 30), title, font=f_title, fill=WHITE)
        draw.text((190, cy + 72), desc, font=f_desc, fill=WHITE_50)

    # CTA
    f_cta = _f(22, "Medium")
    cta = "Primeiro projeto grátis  ·  ai.arq.br"
    draw.text((_cx(cta, f_cta, w), h - 115), cta, font=f_cta, fill=CYAN_SOFT)

    _logo(draw, w, h)
    return _save(img)


def generate_features_post(
    title: str = "O que a AI.arq faz por você",
    features: list[str] = None,
) -> str:
    """Post 2: Features/benefícios sobre foto de interior."""
    if features is None:
        features = [
            "Lê 10+ tipos de pranchas automaticamente",
            "Identifica portas, luminárias, pontos elétricos",
            "Compara layout atual vs novo em reformas",
            "Gera planilha .xlsx com 16 disciplinas",
            "Marca itens duvidosos em laranja para revisão",
            "Pronta para enviar aos fornecedores",
        ]

    w, h = POST_SIZE
    img = _load_photo("interior.jpg")
    img = _blur_photo(img, 5)
    img = _apply_overlay(img, 0.80)
    draw = ImageDraw.Draw(img)

    # Logo
    f_ai = _f(56, "Bold")
    f_arq = _f(56, "Light")
    ai_w = f_ai.getbbox("AI")[2]
    arq_w = f_arq.getbbox(".arq")[2]
    lx = (w - ai_w - arq_w) // 2
    draw.text((lx, 60), "AI", font=f_ai, fill=WHITE)
    draw.text((lx + ai_w, 60), ".arq", font=f_arq, fill=CYAN)

    # Título
    f_t = _f(38, "Bold")
    lines = _tw(title, f_t, w - 160)
    y = 155
    for line in lines:
        draw.text((_cx(line, f_t, w), y), line, font=f_t, fill=WHITE)
        y += 50

    _gradient_line(draw, (w - 80) // 2, y + 8, 80)
    y += 40

    # Features
    f_feat = _f(26, "Regular")
    f_check = _f(22, "Bold")
    pad = 100

    for feat in features[:7]:
        # Círculo check
        draw.ellipse(
            [pad, y + 5, pad + 26, y + 31],
            fill=(100, 90, 255, ), outline=CYAN_SOFT, width=2,
        )
        draw.text((pad + 6, y + 6), "✓", font=_f(14, "Bold"), fill=CYAN)

        # Texto
        fl = _tw(feat, f_feat, w - pad - 80)
        for line in fl:
            draw.text((pad + 44, y + 3), line, font=f_feat, fill=WHITE_90)
            y += 38
        y += 22

    _logo(draw, w, h)
    return _save(img)


def generate_promo_post(
    headline: str = "Planilha de orçamento em minutos, não em dias",
    subtitle: str = "Envie as pranchas do projeto e receba o orçamento pronto. Primeiro projeto grátis!",
    cta: str = "Teste Grátis",
) -> str:
    """Post 3: Promo/institucional sobre foto de prédio."""
    w, h = POST_SIZE
    img = _load_photo("building.jpg")
    img = _blur_photo(img, 3)
    img = _apply_overlay(img, 0.75)
    draw = ImageDraw.Draw(img)

    # Logo grande
    f_ai = _f(90, "Bold")
    f_arq = _f(90, "Light")
    ai_w = f_ai.getbbox("AI")[2]
    arq_w = f_arq.getbbox(".arq")[2]
    lx = (w - ai_w - arq_w) // 2
    draw.text((lx, 160), "AI", font=f_ai, fill=WHITE)
    draw.text((lx + ai_w, 160), ".arq", font=f_arq, fill=CYAN)

    # Headline
    f_h = _f(44, "Bold")
    lines = _tw(headline, f_h, w - 140)
    y = 330
    for line in lines[:3]:
        draw.text((_cx(line, f_h, w), y), line, font=f_h, fill=WHITE)
        y += 58

    _gradient_line(draw, (w - 80) // 2, y + 10, 80)

    # Subtitle
    if subtitle:
        f_s = _f(24, "Light")
        slines = _tw(subtitle, f_s, w - 180)
        sy = y + 40
        for line in slines[:3]:
            draw.text((_cx(line, f_s, w), sy), line, font=f_s, fill=WHITE_50)
            sy += 36

    # Botão CTA
    f_cta = _f(28, "SemiBold")
    cta_text = f"  {cta}  →  "
    bb = f_cta.getbbox(cta_text)
    cw = bb[2] - bb[0]
    ch = bb[3] - bb[1]
    bp = 18
    bx = (w - cw - bp * 2) // 2
    by = h - 190

    # Gradiente do botão
    btn_h = ch + bp * 2
    for i in range(btn_h):
        t = i / max(btn_h - 1, 1)
        r = int(INDIGO[0] + (CYAN[0] - INDIGO[0]) * t)
        g = int(INDIGO[1] + (CYAN[1] - INDIGO[1]) * t)
        b = int(INDIGO[2] + (CYAN[2] - INDIGO[2]) * t)
        draw.line([(bx, by + i), (bx + cw + bp * 2, by + i)], fill=(r, g, b))

    draw.rounded_rectangle(
        [bx, by, bx + cw + bp * 2, by + btn_h],
        radius=btn_h // 2, outline=None,
    )
    draw.text((bx + bp, by + bp), cta_text, font=f_cta, fill=WHITE)

    # URL
    f_url = _f(18, "Light")
    draw.text((_cx("ai.arq.br", f_url, w), h - 60), "ai.arq.br", font=f_url, fill=WHITE_50)

    return _save(img)


def generate_stat_post(
    stat_number: str = "130+",
    stat_label: str = "itens identificados",
    description: str = "",
    photo: str = "office_modern.jpg",
) -> str:
    """Post de estatística sobre foto."""
    w, h = POST_SIZE
    img = _load_photo(photo)
    img = _blur_photo(img, 6)
    img = _apply_overlay(img, 0.80)
    draw = ImageDraw.Draw(img)

    # Número gigante
    f_num = _f(180, "Bold")
    nx = _cx(stat_number, f_num, w)
    draw.text((nx, 250), stat_number, font=f_num, fill=CYAN)

    # Label
    f_lab = _f(44, "SemiBold")
    draw.text((_cx(stat_label, f_lab, w), 475), stat_label, font=f_lab, fill=WHITE)

    _gradient_line(draw, (w - 80) // 2, 540, 80)

    if description:
        f_d = _f(24, "Light")
        lines = _tw(description, f_d, w - 200)
        y = 570
        for line in lines[:3]:
            draw.text((_cx(line, f_d, w), y), line, font=f_d, fill=WHITE_50)
            y += 36

    _logo(draw, w, h)
    return _save(img)


def generate_tip_post(
    title: str,
    body: str,
    category: str = "Dica de Arquitetura",
    photo: str = "blueprint.jpg",
    post_type: str = "feed",
) -> str:
    """Post de dica/conteúdo educativo sobre foto."""
    w, h = POST_SIZE
    img = _load_photo(photo)
    img = _blur_photo(img, 4)
    img = _apply_overlay(img, 0.78)
    draw = ImageDraw.Draw(img)

    pad = 80

    # Tag
    f_tag = _f(17, "SemiBold")
    _pill(draw, pad, 70, category.upper(), f_tag)

    # Título
    f_t = _f(48, "Bold")
    lines = _tw(title, f_t, w - pad * 2)
    y = 135
    for line in lines[:3]:
        draw.text((pad, y), line, font=f_t, fill=WHITE)
        y += 60

    _gradient_line(draw, pad, y + 8, 80)
    y += 35

    # Body
    f_b = _f(26, "Regular")
    body_lines = _tw(body, f_b, w - pad * 2)
    for line in body_lines[:12]:
        draw.text((pad, y), line, font=f_b, fill=WHITE_90)
        y += 38

    _logo(draw, w, h)
    return _save(img)


def generate_pricing_post(photo: str = "building.jpg") -> str:
    """Post com tabela de preços."""
    w, h = POST_SIZE
    img = _load_photo(photo)
    img = _blur_photo(img, 6)
    img = _apply_overlay(img, 0.82)
    draw = ImageDraw.Draw(img)

    # Tag
    f_tag = _f(17, "SemiBold")
    pw, _ = _pill_size("PLANOS", f_tag)
    _pill(draw, (w - pw) // 2, 55, "PLANOS", f_tag)

    f_t = _f(44, "Bold")
    t = "Quanto custa?"
    draw.text((_cx(t, f_t, w), 108), t, font=f_t, fill=WHITE)

    f_sub = _f(22, "Light")
    s = "Pague por projeto. Sem mensalidade."
    draw.text((_cx(s, f_sub, w), 165), s, font=f_sub, fill=WHITE_50)

    _gradient_line(draw, (w - 60) // 2, 205, 60)

    # Cards de preço
    plans = [
        ("Pequeno", "até 5 pranchas", "R$ 49", False),
        ("Médio", "6-10 pranchas", "R$ 99", True),
        ("Grande", "11+ pranchas", "R$ 149", False),
    ]

    card_w = w - 120
    card_h = 125
    y = 240

    for name, desc, price, popular in plans:
        # Card semi-transparente
        card_img = Image.new("RGBA", (card_w, card_h), (18, 22, 40, 210))
        mask = Image.new("L", (card_w, card_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, card_w, card_h], radius=14, fill=255)
        img.paste(
            Image.alpha_composite(
                Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0)),
                card_img,
            ).convert("RGB"),
            (60, y), mask=mask,
        )
        draw = ImageDraw.Draw(img)

        if popular:
            draw.rounded_rectangle(
                [60, y, 60 + card_w, y + card_h],
                radius=14, outline=CYAN_SOFT, width=2,
            )
            f_pop = _f(13, "SemiBold")
            _pill(draw, 60 + card_w - 150, y + 8, "MAIS POPULAR", f_pop, INDIGO)

        f_name = _f(28, "SemiBold")
        draw.text((90, y + 22), name, font=f_name, fill=WHITE)

        f_desc = _f(20, "Light")
        draw.text((90, y + 58), desc, font=f_desc, fill=WHITE_50)

        f_price = _f(36, "Bold")
        px = 60 + card_w - f_price.getbbox(price)[2] - 30
        draw.text((px, y + 38), price, font=f_price, fill=CYAN)

        y += card_h + 14

    # Destaque grátis
    fy = y + 20
    f_free = _f(26, "SemiBold")
    draw.text((_cx("Primeiro projeto grátis!", f_free, w), fy), "Primeiro projeto grátis!", font=f_free, fill=CYAN)

    f_nc = _f(20, "Light")
    draw.text((_cx("Sem cartão de crédito", f_nc, w), fy + 38), "Sem cartão de crédito", font=f_nc, fill=WHITE_50)

    _logo(draw, w, h)
    return _save(img)
