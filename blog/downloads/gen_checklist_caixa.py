# -*- coding: utf-8 -*-
"""Checklist do financiamento de construção na Caixa — 1 página A4 (29/08/2026).

🔒 REGRA DE FONTE: cada linha deste checklist saiu de uma página LIDA da
cartilha oficial da Caixa ("Habitação PF — Construção, Conclusão, Reforma e
Ampliação de Unidades Habitacionais Isoladas", Versão 12, DEZEMBRO/2025,
baixada de caixa.gov.br em 29/08/2026; cópia em arq/cartilha_caixa_construcao_
PF_v12_dez25.pdf). A página de origem está anotada em cada item AQUI NO
GERADOR — no PDF final vai só o rodapé com a fonte, pra não poluir a vistoria.

🚫 Nada de exigência "de ouvir dizer": se um item não tem página, ele não entra.

Rodar da raiz: python blog/downloads/gen_checklist_caixa.py
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer)

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "checklist-financiamento-construcao-caixa.pdf")

INDIGO = colors.HexColor("#4F46E5")
CINZA = colors.HexColor("#6B7280")

est_titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=15,
                            textColor=INDIGO, spaceAfter=2)
est_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5,
                         textColor=CINZA, spaceAfter=8, leading=11)
est_grupo = ParagraphStyle("g", fontName="Helvetica-Bold", fontSize=10.5,
                           textColor=colors.white, backColor=INDIGO,
                           borderPadding=(3, 6, 3, 6), spaceBefore=8, spaceAfter=3)
est_item = ParagraphStyle("i", fontName="Helvetica", fontSize=9.2, leading=13)

CX = "[&nbsp;&nbsp;]"

# (grupo, [(item, pagina_da_cartilha)])
GRUPOS = [
    ("FORMULÁRIOS DA CAIXA", [
        ("PCI — Proposta de Construção Individual, preenchida por completo e "
         "assinada pelo cliente E pelo responsável técnico", 6),
        ("PLS — Planilha de Levantamento de Serviços (aba do mesmo arquivo da "
         "PCI), com os percentuais de evolução por etapa informados pelo RT", 27),
    ]),
    ("PROJETO E LICENÇAS", [
        ("Projeto Legal aprovado pela Prefeitura ou órgão competente, em "
         "formato digital (PDF)", 13),
        ("Se a aprovação municipal for simplificada: desenhos técnicos "
         "suficientes — plantas baixas, cortes e fachadas", 13),
        ("Alvará ou Licença de construção — recomendável na análise e "
         "obrigatório pra liberação das parcelas de obra", 14),
    ]),
    ("RESPONSABILIDADE TÉCNICA", [
        ("Responsável técnico com inscrição no CREA, CAU ou CFT/CRT", 4),
        ("ART, RRT ou TRT da elaboração dos projetos E da execução da obra", 13),
        ("Memorial descritivo, orçamento e cronograma — o RT responde por "
         "esse conjunto junto com os desenhos técnicos", 13),
    ]),
    ("CRONOGRAMA — AS REGRAS QUE REPROVAM", [
        ("Prazo contratual de até 24 meses, contado 30 dias após a "
         "contratação", 25),
        ("Última etapa com no mínimo 5% da evolução da obra", 25),
        ("Prazo realista: o formulário alerta prazo fora do usual e exige "
         "justificativa técnica", 26),
        ("Obra já iniciada? Informar o percentual pré-executado (Etapa 0) e "
         "descrever os serviços existentes", 25),
    ]),
    ("DEPOIS DE CONTRATADO", [
        ("Mudou projeto, orçamento ou especificação: apresentar a Proposta de "
         "Alteração ANTES de executar — de preferência antes de 30% da obra", 27),
        ("Trocou o responsável técnico: comunicar a CAIXA com os documentos "
         "comprobatórios", 4),
    ]),
]

historia = [
    Paragraph("Financiamento de construção na Caixa — checklist", est_titulo),
    Paragraph("Baseado na cartilha oficial da CAIXA “Habitação PF — "
              "Construção, Conclusão, Reforma e Ampliação”, Versão 12 "
              "(dezembro/2025), disponível em caixa.gov.br. Material de apoio do "
              "ai.arq.br/blog — confira a versão vigente da cartilha e a lista "
              "completa da sua agência antes de protocolar.", est_sub),
]
for grupo, itens in GRUPOS:
    historia.append(Paragraph(grupo, est_grupo))
    for item, _pg in itens:
        historia.append(Paragraph(CX + " " + item, est_item))

historia.append(Spacer(1, 5 * mm))
historia.append(Paragraph(
    "Obra/proposta: ______________________________  Data: ____/____/______  "
    "RT: ______________________________", est_item))

doc = BaseDocTemplate(SAIDA, pagesize=A4,
                      leftMargin=14 * mm, rightMargin=14 * mm,
                      topMargin=14 * mm, bottomMargin=14 * mm,
                      title="Checklist — financiamento de construção Caixa")
larg = (doc.width - 8 * mm) / 2
doc.addPageTemplates([PageTemplate(id="duas", frames=[
    Frame(doc.leftMargin, doc.bottomMargin, larg, doc.height, id="c1"),
    Frame(doc.leftMargin + larg + 8 * mm, doc.bottomMargin, larg, doc.height, id="c2"),
])])
doc.build(historia)
print("gerado:", SAIDA, os.path.getsize(SAIDA), "bytes")
