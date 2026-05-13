# -*- coding: utf-8 -*-
"""Exportação do cronograma pra PNG / PDF / PPTX.

Funções puras que recebem o JSON do gerar_cronograma() e produzem arquivo.
"""
import os
import tempfile
from typing import Dict, Optional
from datetime import datetime as _dt


# ─── PNGs auxiliares (Gantt + Curva S) ────────────────────────────

def gerar_gantt_png(cronograma: Dict, output_path: str,
                     titulo: str = 'Cronograma da obra') -> str:
    """Gera Gantt visual PNG via matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    fases = cronograma.get('fases', [])
    if not fases:
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.text(0.5, 0.5, 'Cronograma sem fases', ha='center', va='center',
                fontsize=14, color='#94A3B8')
        ax.axis('off')
        plt.savefig(output_path, dpi=120, bbox_inches='tight', facecolor='white')
        plt.close()
        return output_path

    fig, ax = plt.subplots(figsize=(14, max(5, len(fases) * 0.55)))
    for i, f in enumerate(fases):
        ini = _dt.fromisoformat(f['inicio'])
        fim = _dt.fromisoformat(f['fim'])
        cor = f.get('cor', '#4F46E5')
        ax.barh(i, (fim - ini).days, left=mdates.date2num(ini),
                color=cor, alpha=0.88, edgecolor='white', linewidth=1.2)
        meio = ini + (fim - ini) / 2
        ax.text(mdates.date2num(meio), i, f"{f['dur_dias']}d",
                ha='center', va='center', color='white',
                fontsize=9, fontweight='bold')

    ax.set_yticks(list(range(len(fases))))
    ax.set_yticklabels([f['label'] for f in fases], fontsize=10)
    ax.invert_yaxis()
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b/%y'))

    resumo = cronograma.get('resumo', {})
    sub = (f"Início: {resumo.get('data_inicio', '')} · "
           f"Término: {resumo.get('data_fim', '')} · "
           f"Duração: {resumo.get('duracao_dias_reais', '')} dias")
    ax.set_title(f'{titulo}\n{sub}', fontsize=13, fontweight='bold', pad=15)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    fig.text(0.99, 0.01,
              'gerado por AI.arq · validar com engenheiro responsável',
              ha='right', va='bottom', fontsize=8, color='#94A3B8',
              style='italic')

    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches='tight', facecolor='white')
    plt.close()
    return output_path


def gerar_curva_s_png(cronograma: Dict, output_path: str) -> str:
    """Curva S sigmoidal PNG."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    curva = cronograma.get('curva_s', [])
    if not curva:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.text(0.5, 0.5, 'Sem curva S', ha='center', va='center',
                fontsize=14, color='#94A3B8')
        ax.axis('off')
        plt.savefig(output_path, dpi=120, bbox_inches='tight', facecolor='white')
        plt.close()
        return output_path

    fig, ax = plt.subplots(figsize=(12, 6))
    datas = [_dt.fromisoformat(p['data_fim_mes']) for p in curva]
    pcts = [p['pct_acumulado'] for p in curva]
    ax.plot(datas, pcts, color='#4F46E5', linewidth=3, label='Avanço previsto')
    ax.fill_between(datas, pcts, alpha=0.15, color='#4F46E5')

    for pct_alvo in (25, 50, 75, 100):
        for i, p in enumerate(pcts):
            if p >= pct_alvo:
                ax.axhline(pct_alvo, color='#94A3B8', alpha=0.3,
                           linestyle=':', linewidth=1)
                ax.scatter([datas[i]], [pct_alvo], color='#22D3EE',
                           s=70, zorder=5)
                ax.annotate(f'{pct_alvo}%', xy=(datas[i], pct_alvo),
                            xytext=(6, -16), textcoords='offset points',
                            fontsize=9, color='#1E40AF', fontweight='bold')
                break

    ax.set_ylabel('% Avanço acumulado', fontsize=11)
    ax.set_title('Curva S de Avanço Previsto (modelo sigmoidal)',
                 fontsize=13, fontweight='bold', pad=15)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b/%y'))
    ax.grid(alpha=0.3, linestyle='--')
    ax.set_ylim(0, 105)
    ax.set_axisbelow(True)
    fig.text(0.99, 0.01, 'gerado por AI.arq', ha='right', va='bottom',
             fontsize=8, color='#94A3B8', style='italic')

    plt.tight_layout()
    plt.savefig(output_path, dpi=120, bbox_inches='tight', facecolor='white')
    plt.close()
    return output_path


def _format_br(iso_date: Optional[str]) -> str:
    """ISO YYYY-MM-DD → DD/MM/YYYY."""
    if not iso_date or not isinstance(iso_date, str):
        return ''
    parts = iso_date.split('-')
    if len(parts) == 3:
        return f'{parts[2]}/{parts[1]}/{parts[0]}'
    return iso_date


# ─── PDF ──────────────────────────────────────────────────────────

def exportar_pdf(cronograma: Dict, output_path: str, titulo: str,
                  job_id: str = '') -> str:
    """Gera PDF executivo com capa + Gantt + Curva S + caminho crítico + marcos."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Image, PageBreak, Table, TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    tmp_dir = tempfile.mkdtemp()
    gantt_png = os.path.join(tmp_dir, 'gantt.png')
    curva_png = os.path.join(tmp_dir, 'curva.png')
    gerar_gantt_png(cronograma, gantt_png, titulo=titulo)
    gerar_curva_s_png(cronograma, curva_png)

    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4),
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleAIarq', parent=styles['Title'],
                                  fontSize=20,
                                  textColor=colors.HexColor('#0F172A'),
                                  spaceAfter=12, alignment=0)
    h2_style = ParagraphStyle('H2AIarq', parent=styles['Heading2'],
                               fontSize=13,
                               textColor=colors.HexColor('#4F46E5'),
                               spaceAfter=8, spaceBefore=12)
    body_style = ParagraphStyle('BodyAIarq', parent=styles['BodyText'],
                                 fontSize=10,
                                 textColor=colors.HexColor('#334155'),
                                 leading=14)
    small_style = ParagraphStyle('SmallAIarq', parent=styles['BodyText'],
                                  fontSize=8,
                                  textColor=colors.HexColor('#94A3B8'),
                                  leading=11)

    story = []
    resumo = cronograma.get('resumo', {})

    story.append(Paragraph('Cronograma da obra', title_style))
    story.append(Paragraph(titulo, h2_style))
    story.append(Paragraph(
        f"<b>Início:</b> {_format_br(resumo.get('data_inicio'))} &nbsp;·&nbsp; "
        f"<b>Término previsto:</b> {_format_br(resumo.get('data_fim'))} &nbsp;·&nbsp; "
        f"<b>Duração:</b> {resumo.get('duracao_dias_reais', '?')} dias &nbsp;·&nbsp; "
        f"<b>Fases:</b> {resumo.get('n_fases', 0)}",
        body_style))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph('Gantt', h2_style))
    story.append(Image(gantt_png, width=25*cm, height=12*cm, kind='proportional'))
    story.append(PageBreak())
    story.append(Paragraph('Curva S de Avanço Previsto', h2_style))
    story.append(Image(curva_png, width=25*cm, height=12*cm, kind='proportional'))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        'Modelo sigmoidal (logístico, k=10). Distribuição real de obra: '
        'arranque suave, pico no meio, finalização gradual.',
        small_style))
    story.append(PageBreak())

    cc = resumo.get('caminho_critico', [])
    if cc:
        story.append(Paragraph('Caminho crítico — Top 5 fases mais longas', h2_style))
        rows = [['Posição', 'Fase', 'Duração (dias)']]
        for i, item in enumerate(cc, 1):
            rows.append([str(i), item.get('label', ''),
                         str(item.get('dur_dias', ''))])
        t = Table(rows, colWidths=[2.5*cm, 18*cm, 4*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.HexColor('#F8FAFC'), colors.white]),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5*cm))

    marcos = cronograma.get('marcos_legais', [])
    if marcos:
        story.append(Paragraph('Marcos normativos considerados', h2_style))
        for m in marcos:
            story.append(Paragraph(f'▸ {m}', body_style))
        story.append(Spacer(1, 0.5*cm))

    ressalva = cronograma.get('ressalva', '')
    if ressalva:
        story.append(Paragraph('Ressalvas', h2_style))
        story.append(Paragraph(ressalva, body_style))

    story.append(Spacer(1, 0.8*cm))
    story.append(Paragraph(
        f'Gerado por AI.arq · ai.arq.br · job {job_id}', small_style))

    doc.build(story)

    try:
        os.remove(gantt_png); os.remove(curva_png); os.rmdir(tmp_dir)
    except Exception:
        pass
    return output_path


# ─── PPTX ─────────────────────────────────────────────────────────

def exportar_pptx(cronograma: Dict, output_path: str, titulo: str,
                   job_id: str = '') -> str:
    """PPT executivo com 5 slides."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN

    tmp_dir = tempfile.mkdtemp()
    gantt_png = os.path.join(tmp_dir, 'gantt.png')
    curva_png = os.path.join(tmp_dir, 'curva.png')
    gerar_gantt_png(cronograma, gantt_png, titulo=titulo)
    gerar_curva_s_png(cronograma, curva_png)

    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    INDIGO = RGBColor(0x4F, 0x46, 0xE5)
    DARK = RGBColor(0x0F, 0x17, 0x2A)
    GRAY = RGBColor(0x64, 0x74, 0x8B)

    def add_text(slide, text, left, top, width, height, size=14, bold=False,
                  color=DARK, align='left'):
        tb = slide.shapes.add_textbox(left, top, width, height)
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = {'left': PP_ALIGN.LEFT, 'center': PP_ALIGN.CENTER,
                       'right': PP_ALIGN.RIGHT}[align]
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = 'Calibri'
        return tb

    resumo = cronograma.get('resumo', {})

    # SLIDE 1 — Capa
    s1 = prs.slides.add_slide(blank)
    bg = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0,
                              prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = INDIGO
    bg.line.fill.background()
    add_text(s1, 'CRONOGRAMA DA OBRA', Inches(0.6), Inches(2.5),
              Inches(12), Inches(1.2), size=44, bold=True,
              color=RGBColor(255, 255, 255))
    add_text(s1, titulo, Inches(0.6), Inches(3.8),
              Inches(12), Inches(1), size=22, color=RGBColor(220, 230, 255))
    add_text(s1,
              f"Início {_format_br(resumo.get('data_inicio'))}  ·  "
              f"Término {_format_br(resumo.get('data_fim'))}  ·  "
              f"{resumo.get('n_fases', 0)} fases",
              Inches(0.6), Inches(5.5), Inches(12), Inches(0.6), size=16,
              color=RGBColor(190, 210, 250))
    add_text(s1, 'Gerado por AI.arq · ai.arq.br',
              Inches(0.6), Inches(6.9), Inches(12), Inches(0.4), size=10,
              color=RGBColor(160, 180, 230))

    # SLIDE 2 — Gantt
    s2 = prs.slides.add_slide(blank)
    add_text(s2, 'Gantt', Inches(0.5), Inches(0.3),
              Inches(12), Inches(0.6), size=24, bold=True, color=INDIGO)
    s2.shapes.add_picture(gantt_png, Inches(0.5), Inches(1.0),
                           width=Inches(12.3))

    # SLIDE 3 — Curva S
    s3 = prs.slides.add_slide(blank)
    add_text(s3, 'Curva S de Avanço Previsto', Inches(0.5), Inches(0.3),
              Inches(12), Inches(0.6), size=24, bold=True, color=INDIGO)
    s3.shapes.add_picture(curva_png, Inches(0.5), Inches(1.0),
                           width=Inches(12.3))

    # SLIDE 4 — Caminho crítico
    s4 = prs.slides.add_slide(blank)
    add_text(s4, 'Caminho crítico', Inches(0.5), Inches(0.3),
              Inches(12), Inches(0.6), size=24, bold=True, color=INDIGO)
    add_text(s4, 'Top 5 fases mais longas — atraso aqui atrasa a obra inteira',
              Inches(0.5), Inches(1.0), Inches(12), Inches(0.4), size=12,
              color=GRAY)
    cc = resumo.get('caminho_critico', [])
    y = Inches(1.8)
    for i, item in enumerate(cc, 1):
        add_text(s4, f'{i}.', Inches(0.7), y, Inches(0.5), Inches(0.5),
                  size=18, bold=True, color=INDIGO)
        add_text(s4, item.get('label', ''), Inches(1.3), y, Inches(8.5),
                  Inches(0.5), size=16, bold=True, color=DARK)
        add_text(s4, f"{item.get('dur_dias', '?')} dias",
                  Inches(10), y, Inches(2.5), Inches(0.5), size=14, color=GRAY)
        y += Inches(0.75)

    # SLIDE 5 — Marcos + Ressalva
    s5 = prs.slides.add_slide(blank)
    add_text(s5, 'Marcos normativos & ressalvas', Inches(0.5), Inches(0.3),
              Inches(12), Inches(0.6), size=24, bold=True, color=INDIGO)
    y = Inches(1.2)
    add_text(s5, 'Marcos normativos considerados:',
              Inches(0.5), y, Inches(12), Inches(0.5), size=14, bold=True,
              color=DARK)
    y += Inches(0.5)
    for m in cronograma.get('marcos_legais', []):
        add_text(s5, f'▸ {m}', Inches(0.7), y, Inches(12), Inches(0.4),
                  size=11, color=DARK)
        y += Inches(0.35)
    y += Inches(0.3)
    add_text(s5, 'Ressalvas:',
              Inches(0.5), y, Inches(12), Inches(0.4), size=14, bold=True,
              color=DARK)
    y += Inches(0.5)
    add_text(s5, cronograma.get('ressalva', ''),
              Inches(0.5), y, Inches(12.3), Inches(2), size=11, color=GRAY)

    prs.save(output_path)
    try:
        os.remove(gantt_png); os.remove(curva_png); os.rmdir(tmp_dir)
    except Exception:
        pass
    return output_path
