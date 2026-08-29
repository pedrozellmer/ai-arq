# -*- coding: utf-8 -*-
"""Card de compartilhamento (og:image) POR POST — 29/08/2026.

🎯 Do estudo de SEO: as 31 páginas do site dividiam UMA imagem de card
(/og-image.png). No WhatsApp — que é o botão de compartilhar que acabamos de
pôr nos posts, e o canal onde conteúdo profissional circula no Brasil — todo
post aparecia com o mesmo cartão genérico. Card com o título do post é o que
faz o link parecer um artigo e não um site.

🔑 Determinístico de propósito: mesmo título → mesmos bytes. O gerador roda a
cada build (`generate.py` chama), e um card que muda de bytes sem mudar de
conteúdo sujaria o git a cada rodada.

Identidade (CLAUDE.md): gradiente indigo #4F46E5 → cyan #22D3EE, Montserrat
(a fonte dos assets gerados), logo "AI.arq" em texto.

Rodar da raiz: python blog/downloads/gen_og_images.py  (ou via generate.py)
"""
import io
import json
import os

from PIL import Image, ImageDraw, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
BLOG = os.path.dirname(AQUI)
RAIZ = os.path.dirname(BLOG)
FONTES = os.path.join(RAIZ, "backend", "assets", "fonts")
SAIDA = os.path.join(BLOG, "og")

L, A = 1200, 630
INDIGO = (79, 70, 229)
CYAN = (34, 211, 238)
BRANCO = (255, 255, 255)


def _fonte(nome, tamanho):
    return ImageFont.truetype(os.path.join(FONTES, nome), tamanho)


def _gradiente():
    img = Image.new("RGB", (L, A))
    px = img.load()
    for x in range(L):
        t = x / (L - 1)
        # diagonal suave: mistura indigo→cyan por x com leve peso de y
        for y in range(A):
            ty = min(1.0, t * 0.85 + (y / (A - 1)) * 0.15)
            px[x, y] = tuple(int(a + (b - a) * ty) for a, b in zip(INDIGO, CYAN))
    return img


def _quebra(draw, texto, fonte, max_larg):
    """Quebra o título em linhas que cabem. Sem hifenização esperta — título de
    post não pode chegar quebrado no meio da palavra num card."""
    palavras = texto.split()
    linhas, atual = [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if draw.textlength(teste, font=fonte) <= max_larg:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def gerar_card(titulo, destino, selo="ai.arq.br/blog"):
    img = _gradiente()
    d = ImageDraw.Draw(img)

    # painel escuro translúcido pra dar contraste ao texto sobre o gradiente
    painel = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    dp = ImageDraw.Draw(painel)
    dp.rounded_rectangle((60, 60, L - 60, A - 60), radius=28,
                         fill=(15, 23, 42, 216))          # dark slate
    img = Image.alpha_composite(img.convert("RGBA"), painel)
    d = ImageDraw.Draw(img)

    # logo textual
    f_logo = _fonte("Montserrat-Bold.ttf", 44)
    d.text((110, 108), "AI.arq", font=f_logo, fill=BRANCO)
    lg = d.textlength("AI.arq", font=f_logo)
    d.rounded_rectangle((110 + lg + 18, 118, 110 + lg + 30, 152),
                        radius=6, fill=CYAN)

    # título — reduz a fonte até caber em no máximo 4 linhas
    max_larg = L - 220
    for tam in (72, 64, 58, 52, 46):
        f_tit = _fonte("Montserrat-Bold.ttf", tam)
        linhas = _quebra(d, titulo, f_tit, max_larg)
        if len(linhas) <= 4:
            break
    alt_linha = int(tam * 1.22)
    y = 230
    for ln in linhas[:4]:
        d.text((110, y), ln, font=f_tit, fill=BRANCO)
        y += alt_linha

    # selo do rodapé
    f_selo = _fonte("Montserrat-Medium.ttf", 30)
    d.text((110, A - 130), selo, font=f_selo, fill=(165, 180, 252))

    os.makedirs(SAIDA, exist_ok=True)
    img.convert("RGB").save(destino, "PNG", optimize=True)


def gerar_todos():
    dados = json.load(io.open(os.path.join(BLOG, "posts.json"), encoding="utf-8"))
    feitos = []
    for p in dados["posts"]:
        destino = os.path.join(SAIDA, p["slug"] + ".png")
        gerar_card(p["title"], destino)
        feitos.append(destino)
    # card do índice do blog
    gerar_card("Blog do AI.arq — quantitativos, obra e projeto",
               os.path.join(SAIDA, "index.png"), selo="ai.arq.br")
    return feitos


if __name__ == "__main__":
    feitos = gerar_todos()
    tam = sum(os.path.getsize(f) for f in feitos)
    print("cards: %d | total %.0f KB | exemplo: %s (%d KB)"
          % (len(feitos), tam / 1024, os.path.basename(feitos[0]),
             os.path.getsize(feitos[0]) / 1024))
