# -*- coding: utf-8 -*-
"""Gera as imagens do e-mail de boas-vindas (02/08/2026).

Rode da raiz do repo:  python assets/email/gen_email_assets.py
Saída: assets/email/*.png (deploy do Pages serve em ai.arq.br/assets/email/).
O deploy varre .py do _site — este script pode viver no repo sem ir pro ar.

Identidade: Indigo #4F46E5 · Cyan #22D3EE · Slate #0F172A · Montserrat.
Regra dura nº1 nas artes: linhas BRANCAS = medido, LARANJA = estimativa.
Imagens @2x da largura de exibição (~460px no card → 920-1200px).
"""

from PIL import Image, ImageDraw, ImageFont

FONTS = "backend/assets/fonts"
OUT = "assets/email"

INDIGO = (79, 70, 229)
CYAN = (34, 211, 238)
SLATE = (15, 23, 42)
CINZA_TXT = (71, 85, 105)
CINZA_CLARO = (226, 232, 240)
LARANJA_BG = (255, 214, 153)
LARANJA_TX = (180, 91, 9)
VERDE = (21, 128, 61)
BRANCO = (255, 255, 255)
FUNDO_CLARO = (248, 250, 252)
VERMELHO = (185, 28, 28)
VIOLETA = (124, 58, 237)


def F(nome, tam):
    return ImageFont.truetype(f"{FONTS}/Montserrat-{nome}.ttf", tam)


def check(d, x, y, cor=VERDE, t=4, s_=11):
    # ✓ desenhado na mão — Montserrat não tem o glifo (virava tofu)
    d.line((x, y + s_ // 2, x + s_ // 2, y + s_), fill=cor, width=t)
    d.line((x + s_ // 2, y + s_, x + s_ + s_ // 2, y - 2), fill=cor, width=t)


def warn(d, x, y, r=12):
    # círculo laranja com ! central
    d.ellipse((x, y, x + 2 * r, y + 2 * r), fill=(245, 158, 11))
    d.rectangle((x + r - 2, y + 5, x + r + 2, y + r + 3), fill=BRANCO)
    d.ellipse((x + r - 3, y + r + 7, x + r + 3, y + r + 13), fill=BRANCO)


def gradiente_h(draw, x0, y0, x1, y1, c0, c1):
    w = max(1, x1 - x0)
    for i in range(w):
        t = i / w
        c = tuple(int(c0[k] + (c1[k] - c0[k]) * t) for k in range(3))
        draw.line([(x0 + i, y0), (x0 + i, y1)], fill=c)


def rr(draw, box, r, **kw):
    draw.rounded_rectangle(box, radius=r, **kw)


# ── HERO: planilha medida saindo do CAD ─────────────────────────
def hero():
    W, H = 1200, 660
    img = Image.new("RGB", (W, H), SLATE)
    d = ImageDraw.Draw(img)
    gradiente_h(d, 0, 0, W, 10, INDIGO, CYAN)
    d.text((70, 64), "Seu CAD vira", font=F("Bold", 58), fill=BRANCO)
    d.text((70, 134), "planilha medida", font=F("Bold", 58), fill=(167, 175, 255))
    d.text((70, 224), "Quantitativo por disciplina, em minutos —", font=F("Regular", 30), fill=(203, 213, 225))
    d.text((70, 264), "medido da geometria do seu arquivo.", font=F("Regular", 30), fill=(203, 213, 225))

    # Mock de planilha: 3 linhas medidas (brancas) + 2 estimativas (laranja)
    px, py, pw = 70, 340, W - 140
    rr(d, (px, py, px + pw, py + 252), 18, fill=BRANCO)
    rr(d, (px, py, px + pw, py + 46), 18, fill=(238, 242, 255))
    d.rectangle((px, py + 24, px + pw, py + 46), fill=(238, 242, 255))
    d.text((px + 24, py + 12), "Item", font=F("SemiBold", 22), fill=SLATE)
    d.text((px + pw - 330, py + 12), "Qtd", font=F("SemiBold", 22), fill=SLATE)
    d.text((px + pw - 180, py + 12), "Origem", font=F("SemiBold", 22), fill=SLATE)
    linhas = [
        ("Alvenaria de vedação 14 cm", "128,4 m²", "medido", True),
        ("Piso porcelanato 60×60", "86,2 m²", "medido", True),
        ("Porta de madeira 80×210", "12 un", "medido", True),
        ("Luminária de embutir", "34 un", "estimativa", False),
        ("Pintura látex 2 demãos", "213 m²", "estimativa", False),
    ]
    y = py + 46
    for txt, qtd, origem, medido in linhas:
        alt = 38
        if not medido:
            d.rectangle((px + 1, y, px + pw - 1, y + alt), fill=(255, 247, 237))
        d.text((px + 24, y + 7), txt, font=F("Regular", 21), fill=CINZA_TXT)
        d.text((px + pw - 330, y + 7), qtd, font=F("SemiBold", 21), fill=SLATE)
        if medido:
            check(d, px + pw - 180, y + 12, t=4, s_=10)
            d.text((px + pw - 150, y + 7), origem, font=F("SemiBold", 20), fill=VERDE)
        else:
            warn(d, px + pw - 182, y + 7, r=11)
            d.text((px + pw - 150, y + 7), origem, font=F("SemiBold", 20), fill=LARANJA_TX)
        y += alt
        d.line((px + 16, y, px + pw - 16, y), fill=CINZA_CLARO, width=1)
    img.save(f"{OUT}/welcome-hero.png", optimize=True)


# ── CRONOGRAMA: mini Gantt + curva S ────────────────────────────
def cronograma():
    W, H = 1200, 430
    img = Image.new("RGB", (W, H), FUNDO_CLARO)
    d = ImageDraw.Draw(img)
    rr(d, (24, 24, W - 24, H - 24), 20, fill=BRANCO, outline=CINZA_CLARO, width=2)
    gradiente_h(d, 24, 24, W - 24, 30, (8, 145, 178), CYAN)
    # Barras do Gantt (esquerda)
    cores = [INDIGO, (8, 145, 178), (16, 185, 129), (245, 158, 11), VIOLETA]
    labels = ["Estrutura", "Alvenaria", "Elétrica", "Revestimentos", "Pintura"]
    y = 78
    for i, (c, lb) in enumerate(zip(cores, labels)):
        d.text((64, y + 2), lb, font=F("Medium", 22), fill=CINZA_TXT)
        x0 = 280 + i * 55
        rr(d, (x0, y, x0 + 190 - i * 12, y + 26), 8, fill=c)
        y += 62
    # Curva S (direita)
    cx, cy, cw, ch = 720, 70, 400, 290
    d.line((cx, cy + ch, cx + cw, cy + ch), fill=CINZA_CLARO, width=3)
    d.line((cx, cy, cx, cy + ch), fill=CINZA_CLARO, width=3)
    pts = []
    import math
    for i in range(41):
        t = i / 40
        v = 1 / (1 + math.exp(-8 * (t - 0.5)))
        pts.append((cx + t * cw, cy + ch - v * (ch - 16)))
    d.line(pts, fill=INDIGO, width=6, joint="curve")
    d.text((cx + 130, cy + ch + 10), "curva de avanço", font=F("Medium", 20), fill=CINZA_TXT)
    img.save(f"{OUT}/welcome-cronograma.png", optimize=True)


# ── MEMORIAL: página com carimbo e [A PREENCHER] ────────────────
def memorial():
    W, H = 1200, 430
    img = Image.new("RGB", (W, H), FUNDO_CLARO)
    d = ImageDraw.Draw(img)
    rr(d, (24, 24, W - 24, H - 24), 20, fill=BRANCO, outline=CINZA_CLARO, width=2)
    gradiente_h(d, 24, 24, W - 24, 30, VIOLETA, (139, 92, 246))
    # Página do documento
    px, py, pw, ph = 90, 70, 480, 300
    rr(d, (px, py, px + pw, py + ph), 10, fill=BRANCO, outline=(203, 213, 225), width=2)
    d.text((px + 30, py + 22), "MEMORIAL DESCRITIVO", font=F("Bold", 26), fill=SLATE)
    for i, wl in enumerate([380, 420, 340, 400, 300]):
        d.rectangle((px + 30, py + 78 + i * 30, px + 30 + wl, py + 90 + i * 30), fill=CINZA_CLARO)
    rr(d, (px + 30, py + 236, px + 410, py + 272), 8, fill=(255, 247, 237), outline=(253, 186, 116), width=2)
    d.text((px + 44, py + 242), "[A PREENCHER pelo RT]", font=F("SemiBold", 22), fill=LARANJA_TX)
    # Carimbo RASCUNHO
    stamp = Image.new("RGBA", (330, 90), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stamp)
    rr(sd, (4, 4, 326, 86), 14, outline=VERMELHO + (230,), width=6)
    sd.text((38, 26), "RASCUNHO", font=F("Bold", 38), fill=VERMELHO + (230,))
    stamp = stamp.rotate(9, expand=True, resample=Image.BICUBIC)
    img.paste(stamp, (300, 205), stamp)
    # Texto à direita
    d.text((660, 120), "Escrito a partir dos", font=F("Medium", 30), fill=CINZA_TXT)
    d.text((660, 162), "itens medidos do", font=F("Medium", 30), fill=CINZA_TXT)
    d.text((660, 204), "seu projeto.", font=F("Medium", 30), fill=CINZA_TXT)
    d.text((660, 262), "Editável na tela ·", font=F("SemiBold", 28), fill=VIOLETA)
    d.text((660, 300), "sai em Word ou PDF", font=F("SemiBold", 28), fill=VIOLETA)
    img.save(f"{OUT}/welcome-memorial.png", optimize=True)


# ── COMPARATIVO: cotações lado a lado ───────────────────────────
def comparativo():
    W, H = 1200, 430
    img = Image.new("RGB", (W, H), FUNDO_CLARO)
    d = ImageDraw.Draw(img)
    rr(d, (24, 24, W - 24, H - 24), 20, fill=BRANCO, outline=CINZA_CLARO, width=2)
    gradiente_h(d, 24, 24, W - 24, 30, (5, 150, 105), (52, 211, 153))
    base_y = 330
    forn = [("Fornecedor A", 200, (148, 163, 184)), ("Fornecedor B", 150, (16, 185, 129)),
            ("Fornecedor C", 235, (148, 163, 184))]
    x = 120
    for nome, alt, cor in forn:
        rr(d, (x, base_y - alt, x + 150, base_y), 10, fill=cor)
        d.text((x + 8, base_y + 14), nome, font=F("Medium", 22), fill=CINZA_TXT)
        if cor == (16, 185, 129):
            check(d, x + 58, base_y - alt - 46, t=6, s_=18)
        x += 240
    d.text((830, 130), "Cotações lado a lado,", font=F("Medium", 28), fill=CINZA_TXT)
    d.text((830, 170), "comparação justa", font=F("Medium", 28), fill=CINZA_TXT)
    d.text((830, 210), "(itens pareados) e", font=F("Medium", 28), fill=CINZA_TXT)
    d.text((830, 250), "quem esqueceu o quê.", font=F("Medium", 28), fill=CINZA_TXT)
    img.save(f"{OUT}/welcome-comparativo.png", optimize=True)




# ── PLANILHA PRONTA: check + planilha saindo ────────────────────
def pronta():
    W, H = 1200, 360
    img = Image.new("RGB", (W, H), FUNDO_CLARO)
    d = ImageDraw.Draw(img)
    rr(d, (24, 24, W - 24, H - 24), 20, fill=BRANCO, outline=CINZA_CLARO, width=2)
    gradiente_h(d, 24, 24, W - 24, 30, (5, 150, 105), (52, 211, 153))
    # círculo com check grande
    d.ellipse((80, 110, 220, 250), fill=(220, 252, 231))
    check(d, 118, 168, cor=VERDE, t=12, s_=40)
    d.text((280, 120), "Planilha pronta", font=F("Bold", 44), fill=SLATE)
    d.text((280, 185), "Quantitativo por disciplina, com cada item", font=F("Regular", 26), fill=CINZA_TXT)
    d.text((280, 222), "rotulado: medido ou estimativa.", font=F("Regular", 26), fill=CINZA_TXT)
    img.save(f"{OUT}/pronta-hero.png", optimize=True)


# ── FALHA: arquivo com aviso + caminho DXF ──────────────────────
def falha():
    W, H = 1200, 360
    img = Image.new("RGB", (W, H), FUNDO_CLARO)
    d = ImageDraw.Draw(img)
    rr(d, (24, 24, W - 24, H - 24), 20, fill=BRANCO, outline=CINZA_CLARO, width=2)
    gradiente_h(d, 24, 24, W - 24, 30, (245, 158, 11), (253, 186, 116))
    # arquivo com aviso
    rr(d, (110, 80, 330, 300), 14, fill=FUNDO_CLARO, outline=(203, 213, 225), width=3)
    d.text((140, 108), "DWG", font=F("Bold", 40), fill=(148, 163, 184))
    warn(d, 250, 200, r=34)
    # seta
    d.line((380, 190, 520, 190), fill=CINZA_TXT, width=8)
    d.polygon([(520, 172), (556, 190), (520, 208)], fill=CINZA_TXT)
    # destino DXF
    rr(d, (600, 80, 820, 300), 14, fill=(238, 242, 255), outline=INDIGO, width=3)
    d.text((640, 108), "DXF", font=F("Bold", 40), fill=INDIGO)
    check(d, 680, 210, cor=VERDE, t=9, s_=28)
    d.text((870, 150), "Um ajuste no", font=F("Medium", 30), fill=CINZA_TXT)
    d.text((870, 192), "arquivo resolve —", font=F("Medium", 30), fill=CINZA_TXT)
    d.text((870, 234), "te mostramos como.", font=F("Medium", 30), fill=CINZA_TXT)
    img.save(f"{OUT}/falha-arquivo.png", optimize=True)


# ── CHECK-IN: gantt com avanço parcial ──────────────────────────
def checkin():
    W, H = 1200, 360
    img = Image.new("RGB", (W, H), FUNDO_CLARO)
    d = ImageDraw.Draw(img)
    rr(d, (24, 24, W - 24, H - 24), 20, fill=BRANCO, outline=CINZA_CLARO, width=2)
    gradiente_h(d, 24, 24, W - 24, 30, (8, 145, 178), CYAN)
    dados = [("Estrutura", 1.0, INDIGO), ("Alvenaria", 0.7, (8, 145, 178)),
             ("Elétrica", 0.35, (16, 185, 129)), ("Revestimentos", 0.0, (245, 158, 11))]
    y = 78
    for lb, prog, cor in dados:
        d.text((64, y + 2), lb, font=F("Medium", 22), fill=CINZA_TXT)
        x0, larg = 300, 560
        rr(d, (x0, y, x0 + larg, y + 28), 9, fill=(237, 242, 247))
        if prog > 0:
            rr(d, (x0, y, x0 + int(larg * prog), y + 28), 9, fill=cor)
        pct = f"{int(prog * 100)}%"
        d.text((x0 + larg + 24, y + 2), pct, font=F("SemiBold", 22),
               fill=VERDE if prog == 1 else CINZA_TXT)
        y += 62
    d.text((950, 140), "% executado", font=F("Medium", 24), fill=CINZA_TXT)
    d.text((950, 175), "em 1 minuto", font=F("Medium", 24), fill=CINZA_TXT)
    img.save(f"{OUT}/checkin-gantt.png", optimize=True)


# ── CALIBRAÇÃO: correção laranja → verde ────────────────────────
def calibracao():
    W, H = 1200, 320
    img = Image.new("RGB", (W, H), FUNDO_CLARO)
    d = ImageDraw.Draw(img)
    rr(d, (24, 24, W - 24, H - 24), 20, fill=BRANCO, outline=CINZA_CLARO, width=2)
    gradiente_h(d, 24, 24, W - 24, 30, INDIGO, CYAN)
    # antes (estimativa laranja)
    rr(d, (90, 110, 470, 190), 12, fill=(255, 247, 237), outline=(253, 186, 116), width=2)
    d.text((120, 128), "Luminárias", font=F("Medium", 26), fill=CINZA_TXT)
    d.text((320, 128), "34 un", font=F("SemiBold", 26), fill=LARANJA_TX)
    warn(d, 420, 128, r=14)
    # seta
    d.line((500, 150, 590, 150), fill=CINZA_TXT, width=7)
    d.polygon([(590, 134), (622, 150), (590, 166)], fill=CINZA_TXT)
    # depois (corrigido)
    rr(d, (650, 110, 1030, 190), 12, fill=(240, 253, 244), outline=(134, 239, 172), width=2)
    d.text((680, 128), "Luminárias", font=F("Medium", 26), fill=CINZA_TXT)
    d.text((880, 128), "38 un", font=F("SemiBold", 26), fill=VERDE)
    check(d, 980, 138, cor=VERDE, t=6, s_=20)
    d.text((90, 232), "Sua correção afina o motor — o próximo projeto sai medindo melhor.",
           font=F("Medium", 24), fill=CINZA_TXT)
    img.save(f"{OUT}/calibracao-art.png", optimize=True)


# ── Recortes de foto (cada e-mail com uma foto diferente) ───────
def fotos():
    cortes = [
        ("building.jpg", "nudge-foto.jpg", 0.30),
        ("workspace.jpg", "feedback-foto.jpg", 0.30),
        ("interior.jpg", "retorno-foto.jpg", 0.35),
        ("office_modern.jpg", "proximo-foto.jpg", 0.30),
    ]
    for origem, destino, frac_topo in cortes:
        ph = Image.open(f"backend/assets/photos/{origem}")
        w, h = ph.size
        alvo_w, alvo_h = 1200, 360
        esc = alvo_w / w
        nh = int(h * esc)
        ph = ph.resize((alvo_w, nh), Image.LANCZOS)
        topo = max(0, min(int(nh * frac_topo), nh - alvo_h))
        ph = ph.crop((0, topo, alvo_w, topo + alvo_h))
        ph.save(f"{OUT}/{destino}", quality=80, optimize=True)

if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    hero()
    cronograma()
    memorial()
    comparativo()
    pronta()
    falha()
    checkin()
    calibracao()
    fotos()
    for f in sorted(os.listdir(OUT)):
        if f.endswith(".png"):
            print(f, os.path.getsize(f"{OUT}/{f}") // 1024, "KB")
