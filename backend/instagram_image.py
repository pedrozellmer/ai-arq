# -*- coding: utf-8 -*-
"""Gerador de imagens com a identidade visual AI.arq para posts do Instagram."""
import os
import math
import tempfile
import uuid
from PIL import Image, ImageDraw, ImageFont
from typing import Optional

# Dimensoes Instagram
POST_SIZE = (1080, 1080)
STORY_SIZE = (1080, 1920)

# Cores da marca AI.arq
BRAND_INDIGO = (79, 70, 229)      # #4f46e5
BRAND_CYAN = (6, 182, 212)        # #06b6d4
BRAND_DARK = (17, 24, 39)         # #111827
BRAND_WHITE = (255, 255, 255)
BRAND_LIGHT_BLUE = (125, 211, 252) # #7dd3fc
BRAND_GRAY = (156, 163, 175)      # #9ca3af

OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "aiarq_jobs", "instagram", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _create_gradient(size: tuple, color_top: tuple, color_bottom: tuple) -> Image.Image:
    """Cria um gradiente vertical."""
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    w, h = size

    for y in range(h):
        ratio = y / h
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    return img


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Tenta carregar uma fonte boa, senao usa a default."""
    font_names = [
        # Linux/Docker
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # Windows
        "C:/Windows/Fonts/segoeui.ttf" if not bold
        else "C:/Windows/Fonts/segoeuib.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for font_path in font_names:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            continue

    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Quebra texto em linhas que cabem na largura maxima."""
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    return lines


def generate_tip_post(
    title: str,
    body: str,
    category: str = "Dica de Arquitetura",
    post_type: str = "feed",
) -> str:
    """Gera imagem de post tipo 'dica'.

    Retorna o caminho do arquivo gerado.
    """
    size = STORY_SIZE if post_type == "story" else POST_SIZE
    w, h = size

    # Fundo gradiente
    img = _create_gradient(size, BRAND_INDIGO, BRAND_DARK)
    draw = ImageDraw.Draw(img)

    padding = 80
    content_w = w - (padding * 2)

    # Circulo decorativo semi-transparente (canto superior direito)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.ellipse(
        [w - 300, -150, w + 150, 300],
        fill=(*BRAND_CYAN, 30),
    )
    ov_draw.ellipse(
        [-200, h - 400, 200, h + 50],
        fill=(*BRAND_INDIGO, 25),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    y_cursor = padding + 40

    # Categoria (tag no topo)
    font_cat = _get_font(28, bold=False)
    cat_text = category.upper()
    cat_bbox = font_cat.getbbox(cat_text)
    cat_w = cat_bbox[2] - cat_bbox[0]
    cat_h = cat_bbox[3] - cat_bbox[1]

    # Fundo da tag
    tag_padding = 16
    draw.rounded_rectangle(
        [padding, y_cursor, padding + cat_w + tag_padding * 2, y_cursor + cat_h + tag_padding * 2],
        radius=8,
        fill=(*BRAND_CYAN, ),
    )
    draw.text(
        (padding + tag_padding, y_cursor + tag_padding),
        cat_text,
        font=font_cat,
        fill=BRAND_WHITE,
    )
    y_cursor += cat_h + tag_padding * 2 + 50

    # Titulo
    font_title = _get_font(56, bold=True)
    title_lines = _wrap_text(title, font_title, content_w)
    for line in title_lines:
        draw.text((padding, y_cursor), line, font=font_title, fill=BRAND_WHITE)
        bbox = font_title.getbbox(line)
        y_cursor += (bbox[3] - bbox[1]) + 16
    y_cursor += 30

    # Linha separadora
    draw.line(
        [(padding, y_cursor), (padding + 120, y_cursor)],
        fill=BRAND_CYAN,
        width=4,
    )
    y_cursor += 40

    # Corpo do texto
    font_body = _get_font(36, bold=False)
    body_lines = _wrap_text(body, font_body, content_w)
    for line in body_lines[:12]:  # limitar pra nao estourar
        draw.text((padding, y_cursor), line, font=font_body, fill=BRAND_LIGHT_BLUE)
        bbox = font_body.getbbox(line)
        y_cursor += (bbox[3] - bbox[1]) + 14

    # Rodape com logo
    footer_y = h - padding - 50
    font_logo = _get_font(44, bold=True)
    font_logo_arq = _get_font(44, bold=False)
    font_tagline = _get_font(22, bold=False)

    draw.text((padding, footer_y), "AI", font=font_logo, fill=BRAND_WHITE)
    ai_bbox = font_logo.getbbox("AI")
    ai_w = ai_bbox[2] - ai_bbox[0]
    draw.text((padding + ai_w, footer_y), ".arq", font=font_logo_arq, fill=BRAND_CYAN)

    draw.text(
        (padding, footer_y + 52),
        "ai.arq.br",
        font=font_tagline,
        fill=BRAND_GRAY,
    )

    # Salvar
    filename = f"post_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "JPEG", quality=95)

    return filepath


def generate_promo_post(
    headline: str,
    subtitle: str,
    cta: str = "Acesse ai.arq.br",
) -> str:
    """Gera imagem promocional (sobre o servico)."""
    w, h = POST_SIZE

    # Fundo dark
    img = _create_gradient(POST_SIZE, BRAND_DARK, (10, 15, 30))
    draw = ImageDraw.Draw(img)

    padding = 80
    content_w = w - (padding * 2)

    # Decoracao — arco gradiente
    overlay = Image.new("RGBA", POST_SIZE, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    for i in range(200):
        alpha = max(0, 40 - i // 5)
        r = int(BRAND_INDIGO[0] + (BRAND_CYAN[0] - BRAND_INDIGO[0]) * (i / 200))
        g = int(BRAND_INDIGO[1] + (BRAND_CYAN[1] - BRAND_INDIGO[1]) * (i / 200))
        b = int(BRAND_INDIGO[2] + (BRAND_CYAN[2] - BRAND_INDIGO[2]) * (i / 200))
        ov_draw.line([(0, h - i), (w, h - i)], fill=(r, g, b, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Logo grande centralizado no topo
    y_cursor = 180
    font_ai = _get_font(120, bold=True)
    font_arq = _get_font(120, bold=False)

    ai_bbox = font_ai.getbbox("AI")
    arq_bbox = font_arq.getbbox(".arq")
    total_w = (ai_bbox[2] - ai_bbox[0]) + (arq_bbox[2] - arq_bbox[0])
    start_x = (w - total_w) // 2

    draw.text((start_x, y_cursor), "AI", font=font_ai, fill=BRAND_WHITE)
    draw.text((start_x + ai_bbox[2] - ai_bbox[0], y_cursor), ".arq", font=font_arq, fill=BRAND_CYAN)

    y_cursor += 180

    # Headline
    font_headline = _get_font(52, bold=True)
    headline_lines = _wrap_text(headline, font_headline, content_w)
    for line in headline_lines:
        bbox = font_headline.getbbox(line)
        line_w = bbox[2] - bbox[0]
        x = (w - line_w) // 2  # centralizado
        draw.text((x, y_cursor), line, font=font_headline, fill=BRAND_WHITE)
        y_cursor += (bbox[3] - bbox[1]) + 16
    y_cursor += 20

    # Subtitle
    font_sub = _get_font(34, bold=False)
    sub_lines = _wrap_text(subtitle, font_sub, content_w)
    for line in sub_lines[:4]:
        bbox = font_sub.getbbox(line)
        line_w = bbox[2] - bbox[0]
        x = (w - line_w) // 2
        draw.text((x, y_cursor), line, font=font_sub, fill=BRAND_GRAY)
        y_cursor += (bbox[3] - bbox[1]) + 12
    y_cursor += 40

    # CTA button
    font_cta = _get_font(36, bold=True)
    cta_bbox = font_cta.getbbox(cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    btn_padding = 24
    btn_x = (w - cta_w - btn_padding * 2) // 2
    btn_y = min(y_cursor, h - 200)

    draw.rounded_rectangle(
        [btn_x, btn_y, btn_x + cta_w + btn_padding * 2, btn_y + cta_h + btn_padding * 2],
        radius=12,
        fill=BRAND_CYAN,
    )
    draw.text(
        (btn_x + btn_padding, btn_y + btn_padding),
        cta,
        font=font_cta,
        fill=BRAND_WHITE,
    )

    # Salvar
    filename = f"promo_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "JPEG", quality=95)

    return filepath


def generate_stat_post(
    stat_number: str,
    stat_label: str,
    description: str,
) -> str:
    """Gera imagem com estatistica/numero destaque."""
    w, h = POST_SIZE

    img = _create_gradient(POST_SIZE, (20, 10, 60), BRAND_DARK)
    draw = ImageDraw.Draw(img)

    # Numero grande centralizado
    font_num = _get_font(160, bold=True)
    num_bbox = font_num.getbbox(stat_number)
    num_w = num_bbox[2] - num_bbox[0]
    draw.text(
        ((w - num_w) // 2, 250),
        stat_number,
        font=font_num,
        fill=BRAND_CYAN,
    )

    # Label
    font_label = _get_font(48, bold=True)
    label_bbox = font_label.getbbox(stat_label)
    label_w = label_bbox[2] - label_bbox[0]
    draw.text(
        ((w - label_w) // 2, 450),
        stat_label,
        font=font_label,
        fill=BRAND_WHITE,
    )

    # Descricao
    padding = 80
    font_desc = _get_font(32, bold=False)
    desc_lines = _wrap_text(description, font_desc, w - padding * 2)
    y = 560
    for line in desc_lines[:4]:
        bbox = font_desc.getbbox(line)
        line_w = bbox[2] - bbox[0]
        draw.text(((w - line_w) // 2, y), line, font=font_desc, fill=BRAND_GRAY)
        y += (bbox[3] - bbox[1]) + 12

    # Logo rodape
    font_logo = _get_font(36, bold=True)
    logo_bbox = font_logo.getbbox("AI.arq")
    logo_w = logo_bbox[2] - logo_bbox[0]
    draw.text(((w - logo_w) // 2, h - 120), "AI.arq", font=font_logo, fill=BRAND_LIGHT_BLUE)

    font_url = _get_font(22, bold=False)
    url_bbox = font_url.getbbox("ai.arq.br")
    url_w = url_bbox[2] - url_bbox[0]
    draw.text(((w - url_w) // 2, h - 75), "ai.arq.br", font=font_url, fill=BRAND_GRAY)

    filename = f"stat_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "JPEG", quality=95)

    return filepath
