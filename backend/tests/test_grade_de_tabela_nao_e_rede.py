# -*- coding: utf-8 -*-
"""Metro que é a grade de uma tabela desenhada não sai medido (E14).

🩸 04/10/2026 — conferência da lista de dano, E14. Um projeto de incêndio
entregou "tubulação 1.285,22 ml ✓" (o mesmo número em dois jobs): o layer da
rede era, em 94–99 % do metro, a grade da tabela de SIMBOLOGIA. O H79 não pega
(tabela não é moldura).

Regras:
- caixa de ≥ 5 horizontais de mesmo vão, espaçadas ≥ 2 % do vão, fechada pelas
  bordas das duas pontas, com texto por linha e um cabeçalho → as linhas dela
  são grade; ≥ 20 m e ≥ 20 % do layer → ressalva do layer: fora da chave do selo
  e do resgate, ⚠ no prompt, e a linha ✓ em metro que cita o layer cai;
- duas leituras (trecho a trecho e em corridas emendadas), a caixa parte onde
  as bordas param; layer de parede NÃO fica de fora (quadro de áreas);
- SÓ REBAIXA: nenhuma soma muda.
Todos os desenhos e nomes são sintéticos.
"""
import os
import re
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402


def _tabela(m, layer, x0=0.0, y0=0.0, vao=97.5, linhas=11, passo=4.93, colunas=(0.15, 0.6),
            modo="linha", cab="SIMBOLOGIA", textos=True, bordas=(True, True), txt="TEXTO"):
    """Tabela desenhada: `linhas` horizontais de `vao`, as bordas das pontas e as
    colunas internas; um texto por faixa e o cabeçalho logo acima.
    modo: 'linha' (LINE inteira), 'quebrada' (LINE por célula), 'celula'
    (LWPOLYLINE fechada por célula), 'poli2d' (POLYLINE pesada)."""
    ys = [y0 + i * passo for i in range(linhas)]
    xs = [x0 + f * vao for f in colunas]
    pontas = [x for x, tem in zip((x0, x0 + vao), bordas) if tem]
    at = {"layer": layer}
    if modo == "linha":
        for y in ys:
            m.add_line((x0, y), (x0 + vao, y), dxfattribs=at)
        for x in pontas + xs:
            m.add_line((x, ys[0]), (x, ys[-1]), dxfattribs=at)
    elif modo == "quebrada":
        cols = sorted({x0, x0 + vao} | set(xs))
        for y in ys:
            for a, b in zip(cols, cols[1:]):
                m.add_line((a, y), (b, y), dxfattribs=at)
        for x in pontas + xs:
            for a, b in zip(ys, ys[1:]):
                m.add_line((x, a), (x, b), dxfattribs=at)
    elif modo == "celula":
        cols = sorted({x0, x0 + vao} | set(xs))
        for ya, yb in zip(ys, ys[1:]):
            for xa, xb in zip(cols, cols[1:]):
                m.add_lwpolyline([(xa, ya), (xb, ya), (xb, yb), (xa, yb)], close=True, dxfattribs=at)
    elif modo == "poli2d":
        for y in ys:
            m.add_polyline2d([(x0, y), (x0 + vao, y)], dxfattribs=at)
        for x in pontas + xs:
            m.add_polyline2d([(x, ys[0]), (x, ys[-1])], dxfattribs=at)
    if textos:
        for ya, yb in zip(ys, ys[1:]):
            m.add_text("Ø 25 mm", dxfattribs={"layer": txt, "height": 0.3 * passo,
                                              "insert": (x0 + 0.02 * vao, (ya + yb) / 2.0)})
    if cab:
        m.add_text(cab, dxfattribs={"layer": txt, "height": 0.4 * passo,
                                    "insert": (x0 + 0.3 * vao, ys[-1] + 0.3 * passo)})
    return ys


def _rede(m, layer, n=10, comp=120.0, x0=200.0, y0=20.0, subida=3.0):
    """Ramais soltos, inclinados (não fazem tabela)."""
    for i in range(n):
        m.add_line((x0, y0 + i * 9.0), (x0 + comp, y0 + i * 9.0 + subida), dxfattribs={"layer": layer})


def _lados(e):
    if e.dxftype() == "LINE":
        return [((e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1]))]
    if e.dxftype() == "LWPOLYLINE":
        p = [(q[0], q[1]) for q in e.get_points("xy")]
        if e.closed:
            p.append(p[0])
    else:
        p = [(v.dxf.location[0], v.dxf.location[1]) for v in e.vertices]
    return list(zip(p, p[1:]))


def _grade(desenha, uf=1.0):
    """Roda o detector sobre o desenho (walls = a soma crua de cada layer)."""
    doc = ezdxf.new("R2018")
    m = doc.modelspace()
    desenha(m)
    tot = {}
    for e in m.query("LINE LWPOLYLINE POLYLINE"):
        for a, b in _lados(e):
            tot[e.dxf.layer] = tot.get(e.dxf.layer, 0.0) + ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 * uf
    walls = [dx.WallSegment(layer=ly, length=v) for ly, v in tot.items()]
    texts = [dx.TextAnnotation(layer=t.dxf.layer, text=t.dxf.text, position=(t.dxf.insert[0], t.dxf.insert[1]),
                               height=t.dxf.height)
             for t in m.query("TEXT")]
    return dx.layers_grade_de_tabela(m, walls, texts, uf)


def _ler(tmp_path, desenha):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    desenha(doc.modelspace())
    p = str(tmp_path / "prancha.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


# ══════════════════════════════════════════════════════════════════════════
#  1. O caso e as formas de desenhar a tabela
# ══════════════════════════════════════════════════════════════════════════
def _o_caso(m):
    """A tabela de simbologia (97,5 × 49,3, 11 linhas) é quase todo o layer da
    rede; sobra a amostra de linha da legenda. A rede de verdade está noutro
    layer, numa planta de ~2 km (a tabela é < 10 % do desenho: não é moldura)."""
    _tabela(m, "TUBO-INC")
    m.add_line((10.0, -8.0), (23.85, -8.0), dxfattribs={"layer": "TUBO-INC"})
    _rede(m, "REDE-OUTRA", n=12, comp=2000.0, subida=60.0)


def test_o_caso_a_tabela_de_simbologia_no_layer_da_rede(tmp_path):
    ex = _ler(tmp_path, _o_caso)
    tab = ex.metadata.get("layers_grade_de_tabela") or {}
    assert "TUBO-INC" in tab and tab["TUBO-INC"]["fracao"] >= 0.9, tab
    assert "simbologia" in tab["TUBO-INC"]["cabecalho"]
    assert "REDE-OUTRA" not in tab
    assert "TUBO-INC" in er.layers_que_nao_provam(ex.metadata)
    assert "REDE-OUTRA" not in er.layers_que_nao_provam(ex.metadata)
    prompt = ex.to_structured_prompt()
    linha = next(l for l in prompt.splitlines() if l.strip().startswith("TUBO-INC:"))
    assert "⚠ GRADE DE TABELA" in linha and "simbologia" in linha
    # o aviso não pode ter "layer <palavra>" (a régua da observação leria a palavra)
    assert not re.search(r"(?i)\blayers?\s+\w", linha.split("⚠", 1)[1])
    # registro de máquina não vai cru pro prompt
    assert "layers_grade_de_tabela" not in prompt


def test_so_marca_nao_muda_a_soma(tmp_path):
    def sem(m):
        _tabela(m, "TUBO-INC", cab=None)          # sem cabeçalho: não marca
        m.add_line((10.0, -8.0), (23.85, -8.0), dxfattribs={"layer": "TUBO-INC"})
        _rede(m, "REDE-OUTRA", n=12, comp=2000.0, subida=60.0)
    a, b = _ler(tmp_path, _o_caso), _ler(tmp_path, sem)
    assert "TUBO-INC" in (a.metadata.get("layers_grade_de_tabela") or {})
    assert "TUBO-INC" not in (b.metadata.get("layers_grade_de_tabela") or {})
    assert a.get_walls_by_layer() == b.get_walls_by_layer()


# 'celula': o walls soma os DOIS lados comuns de células vizinhas (a polilinha
# fechada não passa pela cópia exata), e a grade conta cada lado 1× — ~57 %
@pytest.mark.parametrize("modo,piso", [("linha", 0.9), ("quebrada", 0.9), ("celula", 0.5), ("poli2d", 0.9)])
def test_as_formas_de_desenhar_a_tabela(modo, piso):
    tab = _grade(lambda m: (_tabela(m, "TAB-X", modo=modo), _rede(m, "REDE", n=3)))
    assert "TAB-X" in tab and tab["TAB-X"]["fracao"] >= piso, (modo, tab)
    assert type(tab["TAB-X"]["fracao"]) is float and type(tab["TAB-X"]["m"]) is float


def test_a_celula_em_polilinha_so_aparece_nas_corridas():
    """Trecho a trecho, cada coluna é uma caixa sem cabeçalho: só a leitura em
    corridas emendadas vê a tabela inteira."""
    tab = _grade(lambda m: _tabela(m, "TAB-X", modo="celula"))
    assert tab.get("TAB-X", {}).get("caixas") == 1, tab


def test_a_tabela_de_horizontais_sobrepostas_so_aparece_trecho_a_trecho():
    """2 das 6 linhas têm um 2º trecho sobreposto que passa da borda: emendadas,
    elas mudam de vão e sobram 4 — só a leitura trecho a trecho vê a tabela."""
    def d(m):
        ys = _tabela(m, "TAB-X", linhas=6)
        for y in ys[1:3]:
            m.add_line((50.0, y), (120.0, y), dxfattribs={"layer": "TAB-X"})
    tab = _grade(d)
    assert "TAB-X" in tab, tab


def test_tabelas_empilhadas_do_mesmo_vao_sao_caixas_separadas():
    """Duas tabelas de mesma largura, uma em cima da outra, cada uma com as suas
    bordas: a caixa parte onde as bordas param."""
    def d(m):
        _tabela(m, "TAB-X", linhas=6, cab="LEGENDA")
        _tabela(m, "TAB-X", y0=6 * 4.93 + 12.0, linhas=6, cab="QUADRO")
    tab = _grade(d)
    assert tab.get("TAB-X", {}).get("caixas") == 2 and tab["TAB-X"]["fracao"] >= 0.9, tab


def test_a_faixa_sem_borda_entre_o_titulo_e_a_tabela_parte_a_caixa():
    """Anatomia medida no acervo (sintética aqui): o quadro do título embaixo,
    uma faixa de 0,17 SEM borda, e a tabela de 0,5 por linha. Numa prancha de
    1 km, emendar a borda pela corrida (vão ≤ 1/1000 do desenho) fechava a
    faixa: a caixa não partia e os 0,17 (< 2 % do vão) derrubavam tudo."""
    def d(m):
        _tabela(m, "TAB-X", vao=8.6, linhas=25, passo=0.5, cab="LEGENDA", colunas=(0.3,))
        for y in (-3.301, -3.471, -5.68):
            m.add_line((0.0, y), (8.6, y), dxfattribs={"layer": "TAB-X"})
        for x in (0.0, 8.6):
            m.add_line((x, -3.301), (x, 0.0), dxfattribs={"layer": "TAB-X"})
            m.add_line((x, -5.68), (x, -3.471), dxfattribs={"layer": "TAB-X"})
        _rede(m, "REDE", n=3, comp=1000.0, subida=60.0)
    tab = _grade(d)
    assert "TAB-X" in tab and tab["TAB-X"]["fracao"] >= 0.8, tab


def test_a_borda_comum_de_duas_tabelas_conta_uma_vez():
    """Duas tabelas encostadas (linhas desencontradas) dividem a MESMA vertical do
    meio: ela está nas duas caixas e conta uma vez só."""
    def d(m):
        _tabela(m, "TAB-X", x0=0.0, y0=0.0, vao=50.0, linhas=6, passo=10.0, bordas=(True, False), cab="LEGENDA")
        _tabela(m, "TAB-X", x0=50.0, y0=2.5, vao=50.0, linhas=11, passo=5.0, bordas=(False, True), cab="QUADRO")
        m.add_line((50.0, 0.0), (50.0, 52.5), dxfattribs={"layer": "TAB-X"})
        _rede(m, "TAB-X", n=2, comp=601.2, x0=300.0)
    tab = _grade(d)
    grade = (6 * 50 + 3 * 50) + (11 * 50 + 3 * 50) + 52.5        # horizontais + verticais + a borda comum
    total = grade + 2 * (601.2 ** 2 + 3.0 ** 2) ** 0.5
    assert tab.get("TAB-X", {}).get("caixas") == 2, tab
    assert abs(tab["TAB-X"]["fracao"] - round(grade / total, 2)) < 0.006, (tab, grade / total)


@pytest.mark.parametrize("cab", ["SIMBOLOGIA", "LEGENDA", "QUADRO DE ÁREAS", "TABELA", "NOTAS",
                                 "DESCRIÇÃO", "ITEM", "QUANT.", "ESPECIFICAÇÃO"])
def test_os_cabecalhos(cab):
    assert "TAB-X" in _grade(lambda m: _tabela(m, "TAB-X", cab=cab))


def test_o_texto_conta_de_qualquer_layer():
    tab = _grade(lambda m: _tabela(m, "TAB-X", txt="OUTRO-TEXTO-QUALQUER"))
    assert "TAB-X" in tab


# 🪤 Diferente do H79, o layer de PAREDE não fica de fora: o quadro de áreas
# desenhado no layer de parede era 74 % do metro dele (medido no acervo).
def test_layer_de_parede_com_o_quadro_de_areas_marca():
    def d(m):
        _tabela(m, "PAREDE", vao=86.5, linhas=20, passo=3.0, cab="QUADRO DE ÁREAS")
        for i in range(30):                                  # paredes: retângulos pequenos
            x, y = 200.0 + (i % 6) * 8.0, (i // 6) * 6.0
            m.add_lwpolyline([(x, y), (x + 5, y), (x + 5, y + 4), (x, y + 4)], close=True,
                             dxfattribs={"layer": "PAREDE"})
    assert er.layer_e_parede("PAREDE")
    tab = _grade(d)
    assert "PAREDE" in tab and 0.5 <= tab["PAREDE"]["fracao"] < 1.0, tab


# ══════════════════════════════════════════════════════════════════════════
#  2. O que NÃO marca
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_cabecalho():
    """Sem cabeçalho há falso positivo medido (cobertura empilhada, rack)."""
    assert "TAB-X" not in _grade(lambda m: _tabela(m, "TAB-X", cab=None))


def test_CONTROLE_sem_texto_por_linha():
    assert "TAB-X" not in _grade(lambda m: _tabela(m, "TAB-X", textos=False))


# ── 🩸 05/10 (revisão da Projetos): a REDE EM ESCADA com a palavra do cabeçalho ──
def _escada(m, layer, n, vao, passo, rotulos, h, extra=(), h_extra=0.3):
    """Ramais paralelos de mesmo vão fechados pelos sub-gerais nas pontas, a
    alimentação chegando de fora, `rotulos` (texto, dx) em cada ramal e os
    textos `extra` ((texto, (x, y)))."""
    at = {"layer": layer}
    for i in range(n):
        m.add_line((0.0, i * passo), (vao, i * passo), dxfattribs=at)
    for x in (0.0, vao):
        m.add_line((x, 0.0), (x, (n - 1) * passo), dxfattribs=at)
    m.add_line((-50.0, -20.0), (0.0, 0.0), dxfattribs=at)
    for i in range(n - 1):
        for s, dx_ in rotulos:
            m.add_text(s, dxfattribs={"layer": "TXT", "height": h, "insert": (dx_, i * passo + 0.2)})
    for s, p in extra:
        m.add_text(s, dxfattribs={"layer": "ARQ-TXT", "height": h_extra, "insert": p})


_SPK = dict(n=8, vao=30.0, passo=3.0, rotulos=[("DN25", 15.0)], h=0.2)
_SPK3 = dict(_SPK, rotulos=[("DN25", 15.0), ("L=30,00", 3.0), ("i=1%", 25.0)])
_CALHA = dict(n=6, vao=40.0, passo=1.5, rotulos=[("ELETROCALHA 200x100", 20.0)], h=0.25)


@pytest.mark.parametrize("rede,extra", [
    (_SPK, [("SALA DE QUADROS", (10.0, 10.0))]),           # a palavra no meio (nome de sala)
    (_SPK, [("VER NOTA 3", (10.0, 10.0))]),
    (_SPK, [("QUADRO DE ALARME", (12.0, 22.0))]),          # logo ACIMA: a letra pequena pro passo segura
    (_SPK3, [("VER NOTA 3", (10.0, 10.0))]),               # 3 rótulos por ramal: a letra segura
    (_SPK3, [("QUADRO DE ALARME", (12.0, 22.0))]),
    (_CALHA, [("QUADRO QD-1", (20.0, 3.0))]),              # letra grande pro passo: a palavra no meio segura
], ids=["sala", "nota", "quadro-acima", "3-rotulos-nota", "3-rotulos-quadro-acima", "eletrocalha-quadro"])
def test_CONTROLE_rede_em_escada_com_a_palavra_do_cabecalho(rede, extra):
    tab = _grade(lambda m: _escada(m, "SPK-REDE", extra=extra, **rede))
    assert "SPK-REDE" not in tab, tab


def test_CONTROLE_rede_em_escada_sem_palavra():
    assert "SPK-REDE" not in _grade(lambda m: _escada(m, "SPK-REDE", **_SPK))


def test_CUSTO_DOCUMENTADO_eletrocalhas_com_a_palavra_logo_acima_marcam():
    """O limite medido que fica: eletrocalhas paralelas a 1,5 m fechadas nas
    pontas, rótulo de 0,25 m (letra ≥ 10 % do passo) e "QUADRO" logo acima do
    topo — a forma, a letra e o cabeçalho de uma tabela. Só rebaixa."""
    tab = _grade(lambda m: _escada(m, "SPK-REDE", extra=[("QUADRO QD-1", (20.0, 8.0))], **_CALHA))
    assert "SPK-REDE" in tab, tab


def test_a_tabela_composta_com_o_cabecalho_de_secao_no_meio_marca():
    """Seções empilhadas (informações / classificação / legenda): os títulos de
    seção ficam NO MEIO da caixa, mas a tabela é densa de texto (≥ 3 por faixa)."""
    def d(m):
        ys = _tabela(m, "TAB-X", linhas=9, passo=2.0, cab=None, textos=False)
        for k, (ya, yb) in enumerate(zip(ys, ys[1:])):
            for j, xf in enumerate((0.02, 0.2, 0.5, 0.8)):
                s = ("LEGENDA" if (k, j) == (4, 0) else "CLASSIFICAÇÃO" if (k, j) == (2, 0) else "x%d-%d" % (k, j))
                m.add_text(s, dxfattribs={"layer": "TXT", "height": 0.35, "insert": (xf * 97.5, (ya + yb) / 2.0)})
    tab = _grade(d)
    assert "TAB-X" in tab, tab


def test_o_cabecalho_de_coluna_dentro_da_primeira_linha_marca():
    """ITEM / DESCRIÇÃO / QUANT. escritos DENTRO da faixa de cima (entre a
    penúltima e a última linha), sem título acima: é a faixa de cima."""
    def d(m):
        ys = _tabela(m, "TAB-X", cab=None)
        for s, xf in (("ITEM", 0.02), ("DESCRIÇÃO", 0.2), ("QUANT.", 0.7)):
            m.add_text(s, dxfattribs={"layer": "TXT", "height": 1.5, "insert": (xf * 97.5, ys[-2] + 1.5)})
    assert "TAB-X" in _grade(d)


def test_CONTROLE_grade_densa_de_texto_sem_palavra_de_cabecalho():
    """Elevação de rack: 8 portas numeradas por fileira, letra grande pro passo,
    denso de texto — mas nenhuma palavra de cabeçalho: não é tabela."""
    def d(m):
        ys = _tabela(m, "RACK-X", linhas=7, passo=2.0, cab=None, textos=False)
        for k, (ya, yb) in enumerate(zip(ys, ys[1:])):
            for j in range(8):
                m.add_text("%02d" % (8 * k + j + 1), dxfattribs={"layer": "TXT", "height": 0.5,
                                                                 "insert": (5.0 + 11.0 * j, (ya + yb) / 2.0)})
    assert "RACK-X" not in _grade(d)


def test_CONTROLE_cabecalho_no_meio_numa_caixa_rala_de_texto():
    """A mesma caixa com UM texto por faixa e a palavra no meio: não é tabela."""
    def d(m):
        ys = _tabela(m, "TAB-X", linhas=9, passo=2.0, cab=None, textos=False)
        for k, (ya, yb) in enumerate(zip(ys, ys[1:])):
            m.add_text("LEGENDA" if k == 4 else "x%d" % k,
                       dxfattribs={"layer": "TXT", "height": 0.35, "insert": (2.0, (ya + yb) / 2.0)})
    assert "TAB-X" not in _grade(d)


@pytest.mark.parametrize("h,marca", [(0.05, False), (0.3, True)])
def test_a_letra_pequena_pro_passo_nao_e_tabela(h, marca):
    """A mesma grade com o cabeçalho em cima: letra de 5 % do passo é rótulo de
    planta (fica); de 30 %, é tabela (marca)."""
    def d(m):
        ys = _tabela(m, "TAB-X", textos=False, cab=None)
        for ya, yb in zip(ys, ys[1:]):
            m.add_text("Ø 25 mm", dxfattribs={"layer": "TXT", "height": h * 4.93,
                                              "insert": (2.0, (ya + yb) / 2.0)})
        m.add_text("SIMBOLOGIA", dxfattribs={"layer": "TXT", "height": h * 4.93, "insert": (30.0, ys[-1] + 1.5)})
    assert ("TAB-X" in _grade(d)) is marca


def test_CONTROLE_texto_sem_altura_nao_prova_a_tabela():
    def d(m):
        _tabela(m, "TAB-X")
    doc = ezdxf.new("R2018")
    m = doc.modelspace()
    d(m)
    walls = [dx.WallSegment(layer="TAB-X", length=1269.7)]
    sem = [dx.TextAnnotation(layer="T", text=t.dxf.text, position=(t.dxf.insert[0], t.dxf.insert[1]), height=0)
           for t in m.query("TEXT")]
    com = [dx.TextAnnotation(layer="T", text=t.dxf.text, position=(t.dxf.insert[0], t.dxf.insert[1]),
                             height=t.dxf.height) for t in m.query("TEXT")]
    assert "TAB-X" not in dx.layers_grade_de_tabela(m, walls, sem, 1.0)
    assert "TAB-X" in dx.layers_grade_de_tabela(m, walls, com, 1.0)


def test_CONTROLE_escada_com_cota_por_degrau():
    """Degraus de mesma largura entre as duas longarinas, com a cota escrita em
    cada degrau: é a forma da tabela, sem cabeçalho."""
    def d(m):
        for k in range(4):
            x0 = k * 5.0
            for i in range(13):
                m.add_line((x0, i * 0.28), (x0 + 1.2, i * 0.28), dxfattribs={"layer": "ESCADA"})
                m.add_text("28", dxfattribs={"layer": "COTA", "height": 0.1,
                                              "insert": (x0 + 0.5, i * 0.28 + 0.1)})
            for x in (x0, x0 + 1.2):
                m.add_line((x, 0.0), (x, 12 * 0.28), dxfattribs={"layer": "ESCADA"})
            m.add_text("SOBE", dxfattribs={"layer": "COTA", "height": 0.2, "insert": (x0 + 0.3, 3.5)})
    assert "ESCADA" not in _grade(d)


def test_CONTROLE_par_de_faces_nao_e_linha_de_tabela():
    """Faces de parede a 15 cm (0,5 % do vão) fechadas nas pontas, ao lado de um
    texto de quadro: o espaçamento < 2 % do vão não é tabela."""
    def d(m):
        for i in range(6):
            m.add_line((0.0, i * 0.15), (30.0, i * 0.15), dxfattribs={"layer": "MURO-X"})
            m.add_text("QUADRO %d" % i, dxfattribs={"layer": "T", "height": 0.05,
                                                    "insert": (1.0, i * 0.15 + 0.05)})
        for x in (0.0, 30.0):
            m.add_line((x, 0.0), (x, 0.75), dxfattribs={"layer": "MURO-X"})
    assert "MURO-X" not in _grade(d)


@pytest.mark.parametrize("bordas", [(True, False), (False, True)])
def test_CONTROLE_sem_a_borda_de_uma_ponta(bordas):
    assert "TAB-X" not in _grade(lambda m: _tabela(m, "TAB-X", bordas=bordas))


def test_CONTROLE_tabela_pequena_menos_de_20_m():
    """Tabela de 2 m × 5 linhas: ~16 m de grade, 35 % de um layer de ~46 m."""
    tab = _grade(lambda m: (_tabela(m, "TAB-X", vao=2.0, linhas=5, passo=0.4),
                            _rede(m, "TAB-X", n=1, comp=30.0), _rede(m, "REDE", n=3)))
    assert "TAB-X" not in tab, tab
    # CONTROLE: a mesma tabela com 5 m de vão (~34 m de grade) marca
    tab = _grade(lambda m: (_tabela(m, "TAB-X", vao=5.0, linhas=5, passo=0.4),
                            _rede(m, "TAB-X", n=1, comp=30.0), _rede(m, "REDE", n=3)))
    assert "TAB-X" in tab, tab


@pytest.mark.parametrize("n,marca", [(10, False), (5, True)])
def test_a_fracao_minima_de_20_por_cento(n, marca):
    """A tabela (~1,26 mil m) num layer com rede de verdade: com 10 ramais de
    600 m ela é 17 % (fica); com 5, 30 % (marca)."""
    tab = _grade(lambda m: (_tabela(m, "TUBO-X"), _rede(m, "TUBO-X", n=n, comp=600.0)))
    assert ("TUBO-X" in tab) is marca, tab


def test_a_copia_exata_conta_uma_vez(tmp_path):
    """A tabela colada 2× no mesmo lugar: o walls conta 1× (H84) e a grade também.
    Uma vez, ela é 14 % do layer (fica); contada 2×, passaria de 20 %."""
    def d(m):
        _tabela(m, "REDE-X")
        _tabela(m, "REDE-X", textos=False, cab=None)
        _rede(m, "REDE-X", n=10, comp=800.0, subida=40.0)
    ex = _ler(tmp_path, d)
    assert 9000 < ex.get_walls_by_layer()["REDE-X"] < 9500        # a cópia saiu do walls
    assert "REDE-X" not in (ex.metadata.get("layers_grade_de_tabela") or {})


def test_CONTROLE_arco_nao_e_linha_de_tabela():
    """As 'linhas' em arco (polilinha com bulge) entre as bordas, com texto e
    cabeçalho: o lado em arco não é linha de tabela."""
    def d(m):
        for i in range(11):
            y = i * 4.93
            m.add_lwpolyline([(0.0, y, 0, 0, 0.2), (97.5, y)], format="xyseb", dxfattribs={"layer": "ARCO-X"})
        _tabela(m, "BORDA-Y")                       # o texto, o cabeçalho e as bordas noutro layer...
        for x in (0.0, 97.5):                       # ...e as bordas também no layer dos arcos
            m.add_line((x, 0.0), (x, 49.3), dxfattribs={"layer": "ARCO-X"})
    assert "ARCO-X" not in _grade(d)


def test_CONTROLE_rede_sem_tabela():
    def d(m):
        _rede(m, "REDE", n=20, comp=300.0)
        for i in range(6):                     # paralelas de mesmo vão, sem borda nas pontas
            m.add_line((0.0, 400.0 + i * 3.0), (80.0, 400.0 + i * 3.0), dxfattribs={"layer": "REDE"})
        m.add_text("LEGENDA", dxfattribs={"layer": "T", "height": 1.0, "insert": (5.0, 410.0)})
    assert "REDE" not in _grade(d)


def test_CONTROLE_a_tabela_de_outro_layer_nao_marca_a_rede():
    tab = _grade(lambda m: (_tabela(m, "TABELA-Y"), _rede(m, "REDE", n=20, comp=300.0)))
    assert "TABELA-Y" in tab and "REDE" not in tab, tab


def test_CONTROLE_layer_acima_do_teto_nao_e_medido(monkeypatch):
    monkeypatch.setattr(dx, "_TUBO_MAX_SEG", 10)
    assert "TAB-X" not in _grade(lambda m: _tabela(m, "TAB-X"))


def test_tabela_em_layer_de_anotacao_fica_com_o_aviso_de_anotacao(tmp_path):
    """O detector não filtra anotação (igual ao H79); o prompt dá a vez ao
    rótulo de anotação, que já tira o layer da chave."""
    assert er.layer_is_anotacao("A-ANNO-TEXT")
    ex = _ler(tmp_path, lambda m: (_tabela(m, "A-ANNO-TEXT"), _rede(m, "REDE", n=12, comp=2000.0, subida=60.0)))
    assert "A-ANNO-TEXT" in (ex.metadata.get("layers_grade_de_tabela") or {})
    linha = next(l for l in ex.to_structured_prompt().splitlines() if l.strip().startswith("A-ANNO-TEXT:"))
    assert "ANOTAÇÃO DO DESENHO" in linha and "GRADE DE TABELA" not in linha


def test_a_falha_do_detector_nao_derruba_a_extracao(tmp_path, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("sabotagem do teste")
    monkeypatch.setattr(dx, "layers_grade_de_tabela", quebra)
    ex = _ler(tmp_path, _o_caso)
    assert "layers_grade_de_tabela" not in ex.metadata and ex.get_walls_by_layer()


# ══════════════════════════════════════════════════════════════════════════
#  3. O selo
# ══════════════════════════════════════════════════════════════════════════
def test_a_linha_confirmada_em_metro_cai():
    conf, obs, reb = er.selo_apos_grade_de_tabela(
        "confirmado", "layer TUBO-INC", "ml", ["TUBO-INC"], {"TUBO-INC"})
    assert reb and conf == "estimado" and er.MARCA_GRADE_DE_TABELA in obs
    assert er.MARCA_GRADE_DE_TABELA in er.MARCAS_DE_REBAIXAMENTO


@pytest.mark.parametrize("conf,unit,citado", [
    ("confirmado", "m²", ["PAREDE"]),       # a hachura do layer é medida: área não é tocada
    ("confirmado", "un", ["PAREDE"]),
    ("confirmado", "ml", ["OUTRO"]),
    ("estimado", "ml", ["PAREDE"]),
])
def test_CONTROLE_area_contagem_outro_layer_ou_ja_estimado_seguem(conf, unit, citado):
    c, obs, reb = er.selo_apos_grade_de_tabela(conf, "x", unit, citado, {"PAREDE"})
    assert not reb and c == conf and er.MARCA_GRADE_DE_TABELA not in obs


@pytest.mark.parametrize("unit", ["m", "metro", "metros", "mts", "m linear", "ML", "m.l.", "m.l", "mt"])
def test_a_trava_vale_pra_toda_unidade_de_comprimento(unit):
    conf, _o, reb = er.selo_apos_grade_de_tabela("confirmado", "layer TUBO-INC", unit, ["TUBO-INC"],
                                                 {"TUBO-INC"})
    assert reb and conf == "estimado", unit


# os nomes que o leitor de layers da observação corta (começa com '-', espaço, acento)
@pytest.mark.parametrize("layer,obs", [
    ("-ABC-07", "Fonte: comprimento do layer '-ABC-07' = 72,30 m."),
    ("Q1 ABC_INCÊNDIO", "Fonte: layer 'Q1 ABC_INCÊNDIO' = 1.977,90 m."),
    ("TUBO-INC", "Fonte: comprimento do TUBO-INC = 1.187,72 m."),
])
def test_a_trava_acha_o_layer_que_o_leitor_da_observacao_corta(layer, obs):
    from main import _layers_da_obs
    conf, o, reb = er.selo_apos_grade_de_tabela("confirmado", obs, "ml", _layers_da_obs(obs), {layer.upper()})
    assert reb and conf == "estimado" and er.MARCA_GRADE_DE_TABELA in o, (layer, _layers_da_obs(obs))


def test_o_laco_de_producao_rebaixa_a_linha():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Tubulação de incêndio",
            "unit": "ml", "quantity": 1187.72, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'TUBO-INC' = 1187.72 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"TUBO-INC": 1187.72}, extra={"_tab_ly": {"TUBO-INC"}})
    assert itens[0].confidence.value == "estimado" and "GRADE DE TABELA" in itens[0].observations


def test_CONTROLE_o_laco_sem_a_marca_segue_como_veio():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Tubulação de incêndio",
            "unit": "ml", "quantity": 1187.72, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'TUBO-INC' = 1187.72 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"TUBO-INC": 1187.72}, extra={"_tab_ly": set()})
    assert "GRADE DE TABELA" not in itens[0].observations


class _Extr:
    def __init__(self, md, walls):
        self.metadata = md
        self._w = walls

    def get_walls_by_layer(self):
        return dict(self._w)

    def get_layers_secao_de_parede(self):
        return set()

    def get_areas_by_layer(self):
        return {}

    def get_polygon_areas_by_layer(self):
        return {}


def _roda(marcador, escopo):
    import _executa
    import main
    esc = dict(vars(main))
    esc.update(escopo)
    return _executa.roda("process_job", marcador, esc, tamanho=1)


_MD = {"layers_grade_de_tabela": {"TUBO-INC": {"m": 1187.72, "fracao": 1.0, "cabecalho": "simbologia",
                                               "caixas": 1}}}


def test_a_chave_do_selo_nao_indexa_o_layer():
    """Sem a marca, a linha estimada de 1.187,72 citando o layer seria PROMOVIDA."""
    ex = _Extr(dict(_MD), {"TUBO-INC": 1187.72, "REDE": 300.0})
    esc = _roda("_nao_prova_ig = _layers_que_nao_provam(extraction.metadata)",
                {"extraction": ex, "_indice_geom": {"comprimento": [], "area": [], "contagem": []}})
    assert dict(esc["_indice_geom"]["comprimento"]) == {"REDE": 300.0}
    assert er.prova_da_geometria(1187.72, "ml", "Fonte: layer 'TUBO-INC' = 1187,72 m",
                                 esc["_indice_geom"]) == ""
    # CONTROLE: sem a marca, o índice tem o layer e a linha seria promovida
    sem = _roda("_nao_prova_ig = _layers_que_nao_provam(extraction.metadata)",
                {"extraction": _Extr({}, {"TUBO-INC": 1187.72, "REDE": 300.0}),
                 "_indice_geom": {"comprimento": [], "area": [], "contagem": []}})
    assert er.prova_da_geometria(1187.72, "ml", "Fonte: layer 'TUBO-INC' = 1187,72 m",
                                 sem["_indice_geom"]) != ""


def test_o_resgate_automatico_nao_preenche_com_o_layer():
    ex = _Extr(dict(_MD), {"TUBO-INC": 1187.72, "REDE": 300.0})
    esc = _roda("_nao_prova_rs = _layers_que_nao_provam(extraction.metadata)", {"extraction": ex})
    assert set(esc["_compr_ly"]) == {"REDE"}, esc["_compr_ly"]


def test_o_laco_le_os_layers_marcados_da_extracao():
    ex = _Extr(dict(_MD), {})
    esc = _roda("_tab_ly = {str(_k).strip().upper() for _k in", {"extraction": ex})
    assert esc["_tab_ly"] == {"TUBO-INC"}


# ══════════════════════════════════════════════════════════════════════════
#  4. O cross-check (DXF_CONFIRM_CROSSCHECK, desligado hoje) respeita a marca
# ══════════════════════════════════════════════════════════════════════════
def _cats_do_cross_check():
    """As categorias do cross-check, recortadas do próprio `process_job`."""
    import _executa
    esc = {}
    _executa.roda("process_job", "_AREA_CATS = {", esc)
    _executa.roda("process_job", "_LEN_CATS = {", esc)
    return {"_AREA_CATS": esc["_AREA_CATS"], "_LEN_CATS": esc["_LEN_CATS"]}


def _item_parede(conf):
    """O quadro de áreas no layer de parede: a linha cita o layer em metro."""
    return {"item_num": "1", "description": "Parede de alvenaria",
            "unit": "ml", "quantity": 3461.79, "confidence": conf,
            "observations": "Fonte: comprimento do layer 'PAREDE' = 3461.79 m."}


def test_CONTROLE_com_o_cross_check_ligado_a_parede_que_bate_vira_medida(monkeypatch):
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_parede("estimado")], areas={}, compr={"PAREDE": 3461.79},
        extra={"_tab_ly": set(), "_hard_len_by_cat": {"paredes": {3461.79}}, **_cats_do_cross_check()})
    assert itens[0].confidence.value == "confirmado", itens[0].observations


def test_com_o_cross_check_ligado_a_linha_rebaixada_nao_volta(monkeypatch):
    """A trava marca `_rebaixado_pela_fonte`: o cross-check não desfaz o rebaixamento."""
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_parede("confirmado")], areas={}, compr={"PAREDE": 3461.79},
        extra={"_tab_ly": {"PAREDE"}, "_hard_len_by_cat": {"paredes": {3461.79}}, **_cats_do_cross_check()})
    assert itens[0].confidence.value == "estimado" and "GRADE DE TABELA" in itens[0].observations


def test_o_layer_marcado_nao_vira_medida_dura_do_cross_check():
    from test_crosscheck_respeita_as_marcas import _W, _medidas_duras
    walls = (_W("PAREDE", 3461.79), _W("PAREDE-INT", 30.0))
    comp, _ = _medidas_duras({"layers_grade_de_tabela": {"PAREDE": {"fracao": 0.74}}}, walls=walls)
    assert comp.get("paredes") == {30.0}, comp
    comp0, _ = _medidas_duras({}, walls=walls)                      # CONTROLE: sem a marca, entra
    assert comp0.get("paredes") == {3461.79, 30.0}, comp0
