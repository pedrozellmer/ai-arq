# -*- coding: utf-8 -*-
"""Cola de comandos: medir e contar no AutoCAD — 1 página A4 (30/08/2026).

🔒 REGRA DE FONTE: cada comando e cada pegadinha desta cola saiu de página da
documentação OFICIAL da Autodesk (help.autodesk.com) ABERTA E LIDA em
29-30/08/2026 pelos agentes de pesquisa — a URL está anotada em comentário ao
lado de cada bloco AQUI NO GERADOR. Um GUID de doc da Autodesk devolve HTTP
200 até quando é inventado, então "o link responde" não é prova de nada:
prova é a página lida. O que a doc NÃO diz ficou FORA (ex.: se a paleta
mostra área de hachura, se CONTAGEM conta bloco explodido — não documentado).

Rodar da raiz: python blog/downloads/gen_cola_autocad.py
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer)

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "cola-medir-contar-autocad.pdf")

INDIGO = colors.HexColor("#4F46E5")
CINZA = colors.HexColor("#6B7280")
LARANJA = colors.HexColor("#B45309")

est_titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=15,
                            textColor=INDIGO, spaceAfter=2)
est_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5,
                         textColor=CINZA, spaceAfter=8, leading=11)
est_cmd = ParagraphStyle("c", fontName="Helvetica-Bold", fontSize=10.5,
                         textColor=colors.white, backColor=INDIGO,
                         borderPadding=(3, 6, 3, 6), spaceBefore=7, spaceAfter=3)
est_item = ParagraphStyle("i", fontName="Helvetica", fontSize=9.2, leading=12.5)
est_ped = ParagraphStyle("p", fontName="Helvetica", fontSize=9.2, leading=12.5,
                         textColor=LARANJA)

# (comando, o que faz, pegadinha ou None)   — URLs das páginas lidas:
# AREA:       help.autodesk.com/cloudhelp/2024/PTB/AutoCAD-LT/files/GUID-0591351F-...
# MEDIRGEOM:  help.autodesk.com/cloudhelp/2022/PTB/AutoCAD-Core/files/GUID-5D5B0EE1-...
# LIMITE:     help.autodesk.com/cloudhelp/2024/PTB/AutoCAD-Core/files/GUID-5072D0D0-...
# área+LISTA: help.autodesk.com/cloudhelp/2017/PTB/AutoCAD-Core/files/GUID-0BCD5F58-...
# Paleta:     help.autodesk.com/cloudhelp/2025/PTB/AutoCAD-DidYouKnow/files/GUID-94C065AB-...
# CONTAGEM:   help.autodesk.com/cloudhelp/2023/PTB/AutoCAD-Core/files/GUID-3A0C3460-...
#   limites:  help.autodesk.com/cloudhelp/2023/ENU/AutoCAD-LT/files/GUID-1A7CD80A-...
#   2022+:    help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-DidYouKnow/files/GUID-D5D02903-...
COMANDOS = [
    ("Paleta PROPRIEDADES",
     "Selecione o objeto e leia área e perímetro direto na paleta — a própria "
     "Autodesk recomenda: dá pra achar a área “sem usar nenhum comando”.",
     None),
    ("AREA",
     "Calcula área e perímetro de objetos (círculo, elipse, spline, polilinha, "
     "polígono, região) ou de uma área definida por pontos clicados.",
     "Polilinha ABERTA não dá erro: o AutoCAD fecha sozinho com uma linha reta "
     "virtual do último ponto ao primeiro e devolve um número — sem avisar. E "
     "o perímetro IGNORA essa linha virtual. Polilinha com espessura: mede pela "
     "linha de centro."),
    ("MEDIRGEOM  (MEASUREGEOM)",
     "Mede distância, raio, ângulo, área e volume — clicando ou dinamicamente "
     "(opção Rápido).",
     "Não mede hachura nem cota (a doc lista as duas como não medidas)."),
    ("LIMITE  (BOUNDARY)",
     "Clica dentro de um contorno e cria uma polilinha/região FECHADA dele, com "
     "detecção de ilhas. A receita oficial pra área composta: LIMITE e depois "
     "Propriedades ou LISTA no objeto criado.",
     None),
    ("LISTA  (LIST)",
     "Despeja os dados do objeto selecionado na janela de texto — inclusive a "
     "área, no caso de polilinha fechada ou região.",
     None),
    ("CONTAGEM  (COUNT) — AutoCAD 2022+",
     "Conta e realça as instâncias do bloco no desenho; a paleta Contagem lista "
     "todos os blocos, e COUNTTABLE insere uma tabela com nomes e contagens.",
     "Só conta o que está VISÍVEL no model space. Fica de fora: bloco dentro de "
     "xref, texto, hachura, sólido 3D, imagem. E a página oficial da Contagem "
     "avisa: bloco dentro de bloco não sai na Seleção rápida."),
]

historia = [
    Paragraph("Medir e contar no AutoCAD — a cola", est_titulo),
    Paragraph("Os comandos de levantamento, com as pegadinhas que a própria "
              "documentação da Autodesk registra (nomes em português conforme "
              "as páginas oficiais; CONTAGEM existe desde o AutoCAD 2022). "
              "Material de apoio do ai.arq.br/blog.", est_sub),
]
for cmd, faz, pegadinha in COMANDOS:
    historia.append(Paragraph(cmd, est_cmd))
    historia.append(Paragraph(faz, est_item))
    if pegadinha:
        # 🪤 Helvetica nao tem ⚠ (renderiza ■) — mesma lição do ☐ do checklist
        historia.append(Paragraph("CUIDADO — " + pegadinha, est_ped))

historia.append(Spacer(1, 4 * mm))
historia.append(Paragraph(
    "Fonte: documentação oficial da Autodesk (help.autodesk.com), páginas de "
    "comando e de recursos consultadas em 30/08/2026 (edições 2017–2025, "
    "conforme a página). Comandos e limitações podem mudar entre versões — "
    "confira a ajuda da SUA versão.", est_sub))

doc = BaseDocTemplate(SAIDA, pagesize=A4,
                      leftMargin=14 * mm, rightMargin=14 * mm,
                      topMargin=14 * mm, bottomMargin=14 * mm,
                      title="Cola — medir e contar no AutoCAD")
doc.addPageTemplates([PageTemplate(id="uma", frames=[
    Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="c1"),
])])
doc.build(historia)
print("gerado:", SAIDA, os.path.getsize(SAIDA), "bytes")
