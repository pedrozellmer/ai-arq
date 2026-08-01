# -*- coding: utf-8 -*-
"""Memorial descritivo (RASCUNHO) — gerado a partir do quantitativo do projeto.

v1 DETERMINÍSTICA (01/08/2026, estudo em docs/ESTUDO_MEMORIAL_DESCRITIVO_2026-08.md):
nenhuma chamada de IA — o texto é template + os PRÓPRIOS itens do projeto.
Zero risco de inventar especificação, marca ou norma (as 4 cercas do estudo):

  1. Medido × estimado ROTULADO no texto (regra dura nº1 aplicada a prosa);
  2. O que o CAD não tem vira [A PREENCHER PELO RESPONSÁVEL TÉCNICO] explícito;
  3. Zero invenção: nenhuma norma/marca citada que não venha dos itens;
  4. Carimbo RASCUNHO em cabeçalho, capa e rodapé — não substitui o memorial
     assinado (RRT/ART). Regra dura nº5: não substitui o profissional.

⚠️ NBR 13531/13532 estão CANCELADAS (dez/2017 → série NBR 16636). Este módulo
não cita norma nenhuma de propósito — só o que estiver escrito nos itens.
"""

from datetime import datetime, timezone, timedelta

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Ordem construtiva das disciplinas (valores REAIS do banco, conferidos 01/08).
# Disciplina fora da lista entra no fim, antes de "Complementares".
ORDEM_DISCIPLINAS = [
    "Demolição e Remoção",
    "Serviços Preliminares",
    "Estrutura",
    "Fechamentos Verticais",
    "Divisórias e Vidros",
    "Portas e Ferragens",
    "Instalações Elétricas e Dados",
    "Iluminação",
    "Instalações Hidráulicas",
    "Instalações de Gás",
    "Ar-Condicionado",
    "Incêndio e Segurança",
    "Revestimentos",
    "Forros",
    "Pisos e Rodapés",
    "Marcenaria",
    "Mobiliário",
    "Persianas e Cortinas",
    "Complementares",
]

# Lacunas específicas por disciplina — o que um memorial de verdade tem e o
# CAD NÃO tem. Sempre em bloco [A PREENCHER] explícito (cerca nº2).
LACUNAS_POR_DISCIPLINA = {
    "Estrutura": ("características do concreto (fck e traço), resultado da sondagem do solo "
                  "e dimensionamento estrutural conforme projeto específico"),
    "Fechamentos Verticais": ("traço da argamassa de assentamento e de revestimento, e "
                              "especificação do bloco/tijolo quando não indicada em projeto"),
    "Revestimentos": "preparo de base, argamassa colante e rejunte",
    "Pisos e Rodapés": "preparo de contrapiso, argamassa colante e rejunte",
    "Instalações Hidráulicas": "pressões de teste, caimentos e detalhes executivos",
    "Instalações Elétricas e Dados": "quadros de cargas, balanceamento e aterramento",
}

LACUNA_PADRAO = "especificações complementares, método executivo e marcas/modelos de referência"

CINZA = RGBColor(0x6B, 0x72, 0x80)
LARANJA = RGBColor(0xB4, 0x5B, 0x09)
VERMELHO = RGBColor(0xB9, 0x1C, 0x1C)


def _agora_brasilia():
    # Horários sempre em Brasília (regra da casa) — UTC-3 sem depender de tz do host.
    return datetime.now(timezone.utc) - timedelta(hours=3)


def _fmt_qty(q):
    """1234.5 → '1.234,5' (pt-BR, até 2 casas, sem zeros à direita)."""
    try:
        q = float(q or 0)
    except (TypeError, ValueError):
        return "0"
    txt = f"{q:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    if "," in txt:
        txt = txt.rstrip("0").rstrip(",")
    return txt or "0"


def _p_preencher(doc, detalhe):
    """Parágrafo [A PREENCHER PELO RESPONSÁVEL TÉCNICO: ...] em itálico laranja."""
    p = doc.add_paragraph()
    run = p.add_run(f"[A PREENCHER PELO RESPONSÁVEL TÉCNICO: {detalhe}.]")
    run.italic = True
    run.font.color.rgb = LARANJA
    run.font.size = Pt(10)
    return p


def gerar_memorial_docx(caminho, projeto: dict, items: list):
    """Gera o .docx do memorial em `caminho`.

    projeto: dict com project_name, typology, total_area, user_total_area (opcionais).
    items: lista de dicts (description, quantity, unit, confidence, discipline,
           observations) — o mesmo shape do /api/items.
    """
    doc = Document()

    # Fonte base 11pt (padrão de documento técnico, sem firula)
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ── Cabeçalho e rodapé em TODAS as páginas (cerca nº4) ──
    sec = doc.sections[0]
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
    sec.left_margin, sec.right_margin = Cm(2.5), Cm(2.5)
    h = sec.header.paragraphs[0]
    h.text = "RASCUNHO — para revisão do responsável técnico. Não substitui o memorial assinado (RRT/ART)."
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in h.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = VERMELHO
        run.bold = True
    f = sec.footer.paragraphs[0]
    f.text = (f"Rascunho gerado pelo AI.arq a partir do arquivo CAD do projeto em "
              f"{_agora_brasilia().strftime('%d/%m/%Y')} · quantidades estimadas devem ser confirmadas")
    f.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in f.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = CINZA

    # ── Capa compacta ──
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rt = t.add_run("MEMORIAL DESCRITIVO")
    rt.bold = True
    rt.font.size = Pt(22)
    nome_obra = (projeto.get("project_name") or "").strip() or "[A PREENCHER: nome da obra]"
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rs = sub.add_run(nome_obra)
    rs.font.size = Pt(14)
    carimbo = doc.add_paragraph()
    carimbo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rc = carimbo.add_run("RASCUNHO PARA REVISÃO DO RESPONSÁVEL TÉCNICO")
    rc.bold = True
    rc.font.size = Pt(12)
    rc.font.color.rgb = VERMELHO

    # ── Contagem honesta pro texto de apresentação ──
    total = len(items)
    medidos = sum(1 for i in items if (i.get("confidence") or "") == "confirmado")
    estimados = total - medidos

    doc.add_heading("1. Apresentação", level=1)
    doc.add_paragraph(
        "Este memorial descritivo relaciona os serviços e materiais identificados no projeto, "
        "a partir da leitura do arquivo CAD (plantas e pranchas) enviado ao AI.arq. "
        "Ele foi organizado na sequência usual das etapas construtivas e serve como BASE para o "
        "memorial definitivo, a ser complementado, corrigido e assinado pelo responsável técnico."
    )
    doc.add_paragraph(
        f"O levantamento contém {total} itens: {medidos} com quantidade medida diretamente da "
        f"geometria do CAD e {estimados} com quantidade estimada ou a confirmar. No texto, cada "
        "item indica sua origem entre parênteses — “medido do CAD” ou “estimativa — a confirmar”. "
        "Nenhuma especificação, marca ou norma foi acrescentada além do que consta no próprio projeto; "
        "onde o memorial exige informação que não está no CAD, há um campo destacado "
        "[A PREENCHER PELO RESPONSÁVEL TÉCNICO]."
    )

    # ── Dados da obra ──
    doc.add_heading("2. Dados da obra", level=1)
    area_txt = None
    if projeto.get("total_area"):
        area_txt = f"{_fmt_qty(projeto['total_area'])} m² (medida no projeto)"
    elif projeto.get("user_total_area"):
        area_txt = f"{_fmt_qty(projeto['user_total_area'])} m² (informada pelo cliente — não medida)"
    dados = [
        ("Obra / projeto", nome_obra),
        ("Tipologia", (projeto.get("typology") or "").strip() or "[A PREENCHER]"),
        ("Área total", area_txt or "[A PREENCHER]"),
        ("Endereço", "[A PREENCHER]"),
        ("Proprietário / contratante", "[A PREENCHER]"),
    ]
    tab = doc.add_table(rows=0, cols=2)
    tab.style = "Table Grid"
    for rotulo, valor in dados:
        cells = tab.add_row().cells
        cells[0].paragraphs[0].add_run(rotulo).bold = True
        cells[1].text = valor
        cells[0].width, cells[1].width = Cm(5.5), Cm(10.5)

    doc.add_heading("3. Responsabilidade técnica", level=1)
    _p_preencher(doc, "nome do responsável técnico, título profissional, registro CAU/CREA e número da RRT/ART")

    # ── Seções técnicas por disciplina, em ordem construtiva ──
    grupos = {}
    for it in items:
        d = (it.get("discipline") or "").strip() or "Outros itens levantados"
        grupos.setdefault(d, []).append(it)
    conhecidas = [d for d in ORDEM_DISCIPLINAS if d in grupos]
    extras = sorted(d for d in grupos if d not in ORDEM_DISCIPLINAS)
    # extras entram antes de "Complementares" quando ela existe (é o "saco de resto")
    if "Complementares" in conhecidas:
        idx = conhecidas.index("Complementares")
        ordem = conhecidas[:idx] + extras + conhecidas[idx:]
    else:
        ordem = conhecidas + extras

    num = 4
    for disc in ordem:
        its = grupos[disc]
        doc.add_heading(f"{num}. {disc}", level=1)
        num += 1
        doc.add_paragraph(
            f"Os serviços de {disc.lower()} compreendem os itens identificados no projeto, "
            "conforme relação abaixo:"
        )
        for it in sorted(its, key=lambda x: (x.get("sort_order") or 0, x.get("item_num") or "")):
            qty = float(it.get("quantity") or 0)
            unit = (it.get("unit") or "").strip()
            medido = (it.get("confidence") or "") == "confirmado"
            if qty > 0:
                origem = "medido do CAD" if medido else "estimativa — a confirmar"
                sufixo = f" — {_fmt_qty(qty)} {unit} ({origem})"
            else:
                sufixo = " — quantidade a confirmar"
            p = doc.add_paragraph(style="List Bullet")
            p.add_run((it.get("description") or "").strip())
            run_q = p.add_run(sufixo)
            run_q.bold = qty > 0
            if not medido:
                run_q.font.color.rgb = LARANJA
            obs = (it.get("observations") or "").strip()
            if obs:
                ro = p.add_run(f" Obs.: {obs[:220]}")
                ro.italic = True
                ro.font.size = Pt(9)
                ro.font.color.rgb = CINZA
        _p_preencher(doc, LACUNAS_POR_DISCIPLINA.get(disc, LACUNA_PADRAO))

    # ── Fechamento ──
    doc.add_heading(f"{num}. Considerações finais", level=1)
    doc.add_paragraph(
        "Havendo divergência entre este memorial e os desenhos do projeto, prevalecem os desenhos. "
        "As quantidades assinaladas como estimativa devem ser conferidas pelo responsável técnico "
        "antes de qualquer uso contratual, bancário ou de aprovação. Este documento é um rascunho "
        "gerado automaticamente a partir do arquivo CAD e não possui validade como memorial "
        "descritivo até ser revisado, complementado e assinado pelo responsável técnico."
    )
    doc.add_heading(f"{num + 1}. Encerramento e assinaturas", level=1)
    doc.add_paragraph("Local e data: ____________________________, ____/____/______")
    doc.add_paragraph()
    doc.add_paragraph("_________________________________________\nProprietário / contratante")
    doc.add_paragraph()
    doc.add_paragraph("_________________________________________\nResponsável técnico — registro e RRT/ART nº [A PREENCHER]")

    doc.save(caminho)
    return {"total": total, "medidos": medidos, "estimados": estimados, "secoes": len(ordem)}
