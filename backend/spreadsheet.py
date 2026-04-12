# -*- coding: utf-8 -*-
"""Gerador de planilha .xlsx de orçamento."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from models import ProjectData, BudgetItem, Confidence


# Estilos
F_TITLE = Font(name='Arial', bold=True, size=14)
F_SEC = Font(name='Arial', bold=True, size=11, color='FFFFFF')
F_SUB = Font(name='Arial', bold=True, size=10)
F_HDR = Font(name='Arial', bold=True, size=9)
F_N = Font(name='Arial', size=9)
F_BLUE = Font(name='Arial', size=9, color='0000FF')
F_BOLD = Font(name='Arial', bold=True, size=9)
F_TOT = Font(name='Arial', bold=True, size=10)
F_NOTE = Font(name='Arial', size=8, italic=True, color='FF0000')
F_SM = Font(name='Arial', size=8)

P_SEC = PatternFill('solid', fgColor='2F5496')
P_SUB = PatternFill('solid', fgColor='D6E4F0')
P_HDR = PatternFill('solid', fgColor='B4C6E7')
P_YEL = PatternFill('solid', fgColor='FFFF00')
P_TOT = PatternFill('solid', fgColor='D9E2F3')
P_LT = PatternFill('solid', fgColor='F2F2F2')
P_ORANGE = PatternFill('solid', fgColor='FFD699')

AC = Alignment(horizontal='center', vertical='center', wrap_text=True)
AL = Alignment(horizontal='left', vertical='center', wrap_text=True)
ALT = Alignment(horizontal='left', vertical='top', wrap_text=True)
AR = Alignment(horizontal='right', vertical='center')
BD = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))


DISCIPLINE_ORDER = [
    "Serviços Preliminares",
    "Demolição e Remoção",
    "Fechamentos Verticais",
    "Revestimentos",
    "Pisos e Rodapés",
    "Forros",
    "Portas e Ferragens",
    "Divisórias e Vidros",
    "Persianas e Cortinas",
    "Iluminação",
    "Instalações Elétricas e Dados",
    "Ar-Condicionado",
    "Incêndio e Segurança",
    "Marcenaria",
    "Mobiliário",
    "Complementares",
]


def _style_row(ws, row, font, fill=None, align=None, cols=9):
    for c in range(1, cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = font
        if fill: cell.fill = fill
        if align: cell.alignment = align
        cell.border = BD


def generate_spreadsheet(project: ProjectData, items: list[BudgetItem], output_path: str):
    """Gera a planilha .xlsx completa."""
    wb = Workbook()

    # ================================================================
    # SHEET 1: RESUMO
    # ================================================================
    ws1 = wb.active
    ws1.title = 'Resumo Comparativo'
    ws1.sheet_properties.tabColor = '2F5496'
    ws1.column_dimensions['A'].width = 4
    ws1.column_dimensions['B'].width = 90

    r = 1
    def add_title(text):
        nonlocal r
        ws1.merge_cells(f'A{r}:B{r}')
        ws1.cell(row=r, column=1, value=text).font = Font(name='Arial', bold=True, size=12, color='2F5496')
        r += 1

    def add_line(text, bold=False, fill=None):
        nonlocal r
        ws1.merge_cells(f'A{r}:B{r}')
        c = ws1.cell(row=r, column=1, value=text)
        c.font = Font(name='Arial', bold=bold, size=10)
        c.alignment = ALT
        if fill: c.fill = fill
        r += 1

    def add_section(text):
        nonlocal r
        ws1.merge_cells(f'A{r}:B{r}')
        c = ws1.cell(row=r, column=1, value=text)
        c.font = Font(name='Arial', bold=True, size=10, color='FFFFFF')
        c.fill = P_SEC
        c.alignment = AL
        r += 1

    add_title('ANÁLISE COMPARATIVA — REFORMA DE ESCRITÓRIO')
    r += 1
    if project.name:
        add_line(f'Projeto: {project.name}', bold=True)
    if project.address:
        add_line(f'Endereço: {project.address}')
    if project.architect:
        add_line(f'Arquitetura: {project.architect}')
    add_line(f'Fase: {project.phase}')
    if project.total_area:
        add_line(f'Área laje bruta: {project.total_area:,.1f} m² | Área layout: {project.layout_area:,.1f} m² | Sem intervenção: {project.no_intervention_area:,.1f} m²')
    if project.workstations:
        add_line(f'Posições de trabalho: {project.workstations}')
    r += 1

    # Nota de contexto
    add_line('ATENÇÃO: Reforma de andar existente. Quantitativos consideram apenas o que MUDA.', bold=True)
    r += 1

    if project.departments:
        add_title('DEPARTAMENTOS')
        for dept in project.departments:
            name = dept.get('name', '')
            positions = dept.get('positions', 0)
            add_line(f'  {name}: {positions} posições')
        r += 1

    if project.demolition_notes:
        add_title('DEMOLIÇÃO — O QUE SAI')
        add_section('Notas importantes das pranchas de demolição')
        for note in project.demolition_notes:
            add_line(f'  >> {note}', bold=True, fill=PatternFill('solid', fgColor='FFC7CE'))
        r += 1

    if project.new_rooms:
        add_title('LAYOUT NOVO — O QUE ENTRA')
        for room in project.new_rooms:
            if isinstance(room, dict):
                name = room.get('name', 'Ambiente')
                pd = room.get('ceiling_height', 'a definir')
                area = room.get('area', 'a definir')
                if pd and area and str(pd) != '' and str(area) != '':
                    add_line(f'  • {name} — PD={pd}, ~{area} m²', fill=PatternFill('solid', fgColor='C6EFCE'))
                else:
                    add_line(f'  • {name}', fill=PatternFill('solid', fgColor='C6EFCE'))
            else:
                add_line(f'  • {room}', fill=PatternFill('solid', fgColor='C6EFCE'))
        r += 1

    if project.kept_elements:
        add_title('O QUE PERMANECE')
        for elem in project.kept_elements:
            add_line(f'  • {elem}', fill=PatternFill('solid', fgColor='FFE0B2'))

    # ================================================================
    # SHEET 2: ORÇAMENTO
    # ================================================================
    ws = wb.create_sheet('Orçamento')
    ws.sheet_properties.tabColor = '2F5496'

    widths = [7, 62, 5, 8, 13, 13, 15, 35, 12]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Cabeçalho
    ws.merge_cells('A1:I1')
    ws.cell(row=1, column=1, value='PLANILHA DE QUANTITATIVOS PARA CONCORRÊNCIA — AI.arq').font = F_TITLE
    ws.merge_cells('A2:I2')
    info_parts = []
    if project.name: info_parts.append(project.name)
    if project.architect: info_parts.append(project.architect)
    if project.total_area: info_parts.append(f'Laje {project.total_area:,.0f} m²')
    if project.layout_area: info_parts.append(f'Layout {project.layout_area:,.0f} m²')
    if project.workstations: info_parts.append(f'{project.workstations} posições')
    ws.cell(row=2, column=1, value=' | '.join(info_parts) if info_parts else 'Projeto de Arquitetura').font = F_N
    ws.merge_cells('A3:I3')
    ws.cell(row=3, column=1, value='REFORMA: quantitativos = apenas o que MUDA. Itens em LARANJA = qtd estimada. AMARELO = preencher preço.').font = F_NOTE

    ro = 5
    hdrs = ['ITEM', 'DESCRIÇÃO DO SERVIÇO', 'UN', 'QTDE', 'MAT (R$)', 'M.O. (R$)', 'TOTAL (R$)', 'OBSERVAÇÕES', 'REF.']
    for c, h in enumerate(hdrs, 1):
        cl = ws.cell(row=ro, column=c, value=h)
        cl.font = F_HDR; cl.fill = P_HDR; cl.alignment = AC; cl.border = BD

    ro = 6

    # SEÇÃO 0: PREMISSAS
    ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=9)
    ws.cell(row=ro, column=1, value='0. PREMISSAS')
    _style_row(ws, ro, F_SEC, P_SEC, AL, 9)
    ro += 1

    premissas = []
    if project.total_area:
        premissas.append(('0.1', 'Área construída — perímetro externo da laje', 'm²', project.total_area, '', 'Pr.100'))
    if project.no_intervention_area:
        premissas.append(('0.2', 'Área sem intervenção (core)', 'm²', project.no_intervention_area, '', 'Pr.100'))
    if project.layout_area:
        premissas.append(('0.3', 'Área utilizada para layout / intervenção', 'm²', project.layout_area, '', 'Pr.200'))
    if project.workstations:
        premissas.append(('0.4', 'Posições de trabalho', 'un', project.workstations, 'Conforme quadro de departamentos', 'Pr.300'))

    for num, desc, un, qtd, obs, ref in premissas:
        ws.cell(row=ro, column=1, value=num).font = F_N
        ws.cell(row=ro, column=2, value=desc).font = F_N
        ws.cell(row=ro, column=3, value=un).font = F_N
        ws.cell(row=ro, column=4, value=qtd).font = F_N
        ws.cell(row=ro, column=8, value=obs).font = F_N
        ws.cell(row=ro, column=9, value=ref).font = Font(name='Arial', size=7)
        for c in range(1, 10):
            ws.cell(row=ro, column=c).border = BD
            ws.cell(row=ro, column=c).alignment = AC if c in [1, 3, 4, 9] else AL
        ws.cell(row=ro, column=4).alignment = AR
        ro += 1

    ro += 1  # Linha vazia após premissas
    subtotal_rows = []

    # Agrupar itens por disciplina (deduplicar descrições similares)
    items_by_discipline = {}
    seen_descriptions = set()
    for item in items:
        disc = item.discipline or "Complementares"
        # Deduplicar por descrição normalizada
        desc_key = item.description.lower().strip()[:50]
        if desc_key in seen_descriptions:
            continue
        seen_descriptions.add(desc_key)

        if disc not in items_by_discipline:
            items_by_discipline[disc] = []
        items_by_discipline[disc].append(item)

    # Numerar disciplinas na ordem correta
    disc_num = 1
    for disc_name in DISCIPLINE_ORDER:
        disc_items = items_by_discipline.pop(disc_name, None)
        if not disc_items:
            continue

        # Cabeçalho da seção
        ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=9)
        ws.cell(row=ro, column=1, value=f'{disc_num}. {disc_name.upper()}')
        _style_row(ws, ro, F_SEC, P_SEC, AL, 9)
        ro += 1

        section_start = ro
        for idx, item in enumerate(disc_items, 1):
            item_num = f'{disc_num}.{idx}'
            ws.cell(row=ro, column=1, value=item_num).font = F_N
            ws.cell(row=ro, column=2, value=item.description).font = F_N
            ws.cell(row=ro, column=3, value=item.unit).font = F_N
            ws.cell(row=ro, column=4, value=item.quantity).font = F_BLUE
            ws.cell(row=ro, column=5).font = F_BLUE; ws.cell(row=ro, column=5).fill = P_YEL
            ws.cell(row=ro, column=6).font = F_BLUE; ws.cell(row=ro, column=6).fill = P_YEL
            ws.cell(row=ro, column=7, value=f'=D{ro}*(E{ro}+F{ro})').font = F_N
            ws.cell(row=ro, column=8, value=item.observations).font = F_N
            ws.cell(row=ro, column=9, value=item.ref_sheet).font = Font(name='Arial', size=7)

            for c in range(1, 10):
                ws.cell(row=ro, column=c).border = BD
                ws.cell(row=ro, column=c).alignment = AC if c in [1, 3, 4, 9] else AL
            for c in [4, 5, 6, 7]:
                ws.cell(row=ro, column=c).alignment = AR
            for c in [5, 6, 7]:
                ws.cell(row=ro, column=c).number_format = '#,##0.00'

            # Marcar itens estimados em laranja
            if item.confidence in [Confidence.ESTIMADO, Confidence.VERIFICAR]:
                for c in [1, 2, 3, 4]:
                    ws.cell(row=ro, column=c).fill = P_ORANGE

            ro += 1

        # Subtotal
        section_end = ro - 1
        ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=6)
        ws.cell(row=ro, column=1, value=f'SUBTOTAL {disc_num} — {disc_name.upper()}')
        ws.cell(row=ro, column=7, value=f'=SUM(G{section_start}:G{section_end})')
        ws.cell(row=ro, column=7).number_format = '#,##0.00'
        _style_row(ws, ro, F_BOLD, P_LT, AR, 9)
        ws.cell(row=ro, column=1).alignment = AL
        subtotal_rows.append(ro)
        ro += 1

        disc_num += 1

    # Itens de disciplinas não mapeadas
    for disc_name, disc_items in items_by_discipline.items():
        ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=9)
        ws.cell(row=ro, column=1, value=f'{disc_num}. {disc_name.upper()}')
        _style_row(ws, ro, F_SEC, P_SEC, AL, 9)
        ro += 1

        section_start = ro
        for idx, item in enumerate(disc_items, 1):
            item_num = f'{disc_num}.{idx}'
            ws.cell(row=ro, column=1, value=item_num).font = F_N
            ws.cell(row=ro, column=2, value=item.description).font = F_N
            ws.cell(row=ro, column=3, value=item.unit).font = F_N
            ws.cell(row=ro, column=4, value=item.quantity).font = F_BLUE
            ws.cell(row=ro, column=5).font = F_BLUE; ws.cell(row=ro, column=5).fill = P_YEL
            ws.cell(row=ro, column=6).font = F_BLUE; ws.cell(row=ro, column=6).fill = P_YEL
            ws.cell(row=ro, column=7, value=f'=D{ro}*(E{ro}+F{ro})').font = F_N
            ws.cell(row=ro, column=8, value=item.observations).font = F_N
            ws.cell(row=ro, column=9, value=item.ref_sheet).font = Font(name='Arial', size=7)
            for c in range(1, 10):
                ws.cell(row=ro, column=c).border = BD
                ws.cell(row=ro, column=c).alignment = AC if c in [1, 3, 4, 9] else AL
            for c in [4, 5, 6, 7]: ws.cell(row=ro, column=c).alignment = AR
            for c in [5, 6, 7]: ws.cell(row=ro, column=c).number_format = '#,##0.00'
            if item.confidence in [Confidence.ESTIMADO, Confidence.VERIFICAR]:
                for c in [1, 2, 3, 4]: ws.cell(row=ro, column=c).fill = P_ORANGE
            ro += 1

        section_end = ro - 1
        ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=6)
        ws.cell(row=ro, column=1, value=f'SUBTOTAL {disc_num} — {disc_name.upper()}')
        ws.cell(row=ro, column=7, value=f'=SUM(G{section_start}:G{section_end})')
        ws.cell(row=ro, column=7).number_format = '#,##0.00'
        _style_row(ws, ro, F_BOLD, P_LT, AR, 9)
        ws.cell(row=ro, column=1).alignment = AL
        subtotal_rows.append(ro)
        ro += 1
        disc_num += 1

    # Resumo
    ro += 1
    ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=9)
    ws.cell(row=ro, column=1, value='RESUMO GERAL')
    _style_row(ws, ro, F_SEC, P_SEC, AL, 9)
    ro += 1

    resumo_start = ro
    for st_row in subtotal_rows:
        ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=6)
        # Copiar label do subtotal
        label = ws.cell(row=st_row, column=1).value or ""
        ws.cell(row=ro, column=1, value=label)
        ws.cell(row=ro, column=7, value=f'=G{st_row}')
        ws.cell(row=ro, column=7).number_format = '#,##0.00'
        _style_row(ws, ro, F_N, None, None, 9)
        ws.cell(row=ro, column=1).alignment = AL
        ws.cell(row=ro, column=7).alignment = AR
        ro += 1
    resumo_end = ro - 1

    # Total direto
    ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=6)
    ws.cell(row=ro, column=1, value='TOTAL CUSTO DIRETO (sem BDI)')
    ws.cell(row=ro, column=7, value=f'=SUM(G{resumo_start}:G{resumo_end})')
    ws.cell(row=ro, column=7).number_format = '#,##0.00'
    _style_row(ws, ro, F_TOT, P_TOT, AR, 9)
    ws.cell(row=ro, column=1).alignment = AL
    td = ro; ro += 1

    # BDI
    ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=5)
    ws.cell(row=ro, column=1, value='BDI (%)')
    ws.cell(row=ro, column=6, value=0.30)
    ws.cell(row=ro, column=6).font = F_BLUE
    ws.cell(row=ro, column=6).number_format = '0.00%'
    ws.cell(row=ro, column=6).fill = P_YEL
    ws.cell(row=ro, column=7, value=f'=G{td}*F{ro}')
    ws.cell(row=ro, column=7).number_format = '#,##0.00'
    _style_row(ws, ro, F_BOLD, None, None, 9)
    ws.cell(row=ro, column=1).alignment = AL
    ws.cell(row=ro, column=6).alignment = AR
    ws.cell(row=ro, column=7).alignment = AR
    bdi = ro; ro += 1

    # Total com BDI
    ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=6)
    ws.cell(row=ro, column=1, value='TOTAL GERAL COM BDI')
    ws.cell(row=ro, column=7, value=f'=G{td}+G{bdi}')
    ws.cell(row=ro, column=7).number_format = '#,##0.00'
    _style_row(ws, ro, Font(name='Arial', bold=True, size=12, color='FFFFFF'), P_SEC, AR, 9)
    ws.cell(row=ro, column=1).alignment = AL

    # Notas profissionais
    ro += 2
    ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=9)
    ws.cell(row=ro, column=1, value='NOTAS:').font = F_BOLD; ro += 1
    notas = [
        '1. REFORMA: quantitativos consideram apenas o que MUDA. Conferir in loco e em projeto executivo.',
        '2. Colunas MAT e M.O. (amarelo): preencher pelo orçamentista/fornecedor.',
        '3. BDI padrão 30% — ajustar conforme negociação e tipo de contratação.',
        '4. Itens em LARANJA: quantidade estimada visualmente — confirmar com projeto executivo.',
        '5. Itens em BRANCO: quantidade confirmada na legenda da prancha.',
        '6. Quantidades de materiais já incluem perda estimada de 5-10%.',
        '7. Para alvenaria: vãos de portas e janelas foram descontados quando identificados.',
        '8. Planilha gerada automaticamente por AI.arq — validar com engenheiro de custos.',
    ]
    for n in notas:
        ws.merge_cells(start_row=ro, start_column=1, end_row=ro, end_column=9)
        ws.cell(row=ro, column=1, value=n).font = F_SM; ro += 1

    # Configurações
    ws.freeze_panes = 'A6'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1

    wb.save(output_path)
    return output_path
