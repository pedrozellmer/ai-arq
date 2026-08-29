# -*- coding: utf-8 -*-
"""Checklist imprimível da NBR 9050 — o arquivo que o post PROMETIA e não tinha.

🚨 29/08/2026, achado do estudo do blog: o post nbr-9050-checklist (que sobe em
06/09) promete "tabela imprimível pra vistoria" NA DESCRIPTION e tem a seção
"Tabela-resumo das medidas-chave (imprimível)" — com downloads=None. Promessa
no título sem arquivo é o mesmo defeito do post de cotação ("Template" no
título, zero anexo).

🔒 REGRA DE FONTE: este PDF NÃO afirma nada novo. Todo o conteúdo é CÓPIA da
tabela que já está no posts.json — que passou pela auditoria de 14/08 dos 9
posts futuros (16 citações conferidas, zero erro). Se a tabela do post mudar,
rode este gerador de novo; ele lê DIRETO do posts.json justamente pra não haver
duas versões divergindo.

Rodar da raiz: python blog/downloads/gen_checklist_9050.py
"""
import io
import json
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "checklist-nbr-9050-vistoria.pdf")
POSTS = os.path.join(os.path.dirname(AQUI), "posts.json")

INDIGO = colors.HexColor("#4F46E5")
CINZA = colors.HexColor("#6B7280")

# ── a fonte da verdade é o POST, não este script ────────────────────────────
data = json.load(io.open(POSTS, encoding="utf-8"))
post = next(p for p in data["posts"] if "9050" in p["slug"])
secao = next(s for s in post["sections"] if "imprim" in s.get("h2", "").lower())
linhas = secao["body"].split("\n")

est_titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16,
                            textColor=INDIGO, spaceAfter=2)
est_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5,
                         textColor=CINZA, spaceAfter=8)
est_grupo = ParagraphStyle("g", fontName="Helvetica-Bold", fontSize=10.5,
                           textColor=colors.white, backColor=INDIGO,
                           borderPadding=(3, 6, 3, 6), spaceBefore=8, spaceAfter=3)
est_item = ParagraphStyle("i", fontName="Helvetica", fontSize=9.2, leading=13)

historia = [
    Paragraph("Checklist de vistoria — NBR 9050", est_titulo),
    Paragraph("Medidas-chave da ABNT NBR 9050:2020 e NBR 16537:2024 · "
              "material de apoio do ai.arq.br/blog — confira sempre o texto "
              "vigente da norma antes de aprovar", est_sub),
]

# 🪤 Helvetica não tem o glifo ☐ — o reportlab trocava por ■, e checklist
# com caixa JÁ PREENCHIDA convida a vistoria preguiçosa. "[  ]" imprime igual
# em qualquer impressora.
CAIXA = "[&nbsp;&nbsp;]"
intro_ja_foi = False
for linha in linhas:
    t = linha.strip()
    if not t:
        continue
    if t.startswith("- "):
        historia.append(Paragraph(CAIXA + " " + t[2:], est_item))
        continue
    # 🪤 Grupo é a linha cujo trecho ANTES do parêntese é todo maiúsculo.
    # A 1ª versão exigia a linha INTEIRA maiúscula, e "RAMPA (desnível máximo
    # POR SEGMENTO, conforme a inclinação)" caiu no ramo de introdução — o
    # título sumiu e os itens de rampa apareceram DENTRO de ESTACIONAMENTO.
    cabeca = t.split("(")[0].strip()
    if cabeca and cabeca == cabeca.upper() and any(c.isalpha() for c in cabeca):
        historia.append(Paragraph(t, est_grupo))
    elif not intro_ja_foi:
        historia.insert(2, Paragraph(t, est_sub))
        intro_ja_foi = True
    else:
        historia.append(Paragraph(t, est_item))

historia.append(Spacer(1, 6 * mm))
historia.append(Paragraph(
    "Obra/projeto: ______________________________   Data: ____/____/______   "
    "Responsável: ______________________________", est_item))

doc = BaseDocTemplate(SAIDA, pagesize=A4,
                      leftMargin=14 * mm, rightMargin=14 * mm,
                      topMargin=14 * mm, bottomMargin=14 * mm,
                      title="Checklist NBR 9050 — vistoria")
# duas colunas: o checklist inteiro cabe numa folha, que é o ponto de "imprimível"
larg = (doc.width - 8 * mm) / 2
doc.addPageTemplates([PageTemplate(id="duas", frames=[
    Frame(doc.leftMargin, doc.bottomMargin, larg, doc.height, id="c1"),
    Frame(doc.leftMargin + larg + 8 * mm, doc.bottomMargin, larg, doc.height, id="c2"),
])])
doc.build(historia)
print("gerado:", SAIDA, os.path.getsize(SAIDA), "bytes")
