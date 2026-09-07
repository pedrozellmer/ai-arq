# -*- coding: utf-8 -*-
"""`pilares=0` numa prancha de FÔRMA não dizia por quê.

🚨 27/08/2026. Puxando a família nº1 das correções de campo — itens de
ESTRUTURA que o cliente preenche à mão — cheguei no **EVANDRO ALVES**
(job `2933cc30`, 15/08). Ele fez tudo certo: escolheu o modo "estrutura" no
upload e mandou o projeto estrutural (DWG + PDF de 18 pranchas). Recebeu **30
itens com ZERO medido** e preencheu 17 linhas na mão:

    Pilares  concreto 0 → 5 m³    fôrma 0 → 100 m²   armadura 0 → 1500 kg
    Vigas    concreto 0 → 5 m³    fôrma 0 →  60 m²   armadura 0 → 1500 kg
    Lajes    concreto 0 → 40 m³   fôrma 0 → 155 m²   armadura 0 → 1000 kg

Quase todos números REDONDOS — é frustração, não medição (mesmo padrão do
cliente-53 em [[project_caso_giovani_20260815]]).

📊 E não é só ele. Em todos os projetos com `project_type='estrutura'`:

    un   (contagem)   60 itens   37 medidos   62%
    kg   (aço)       142 itens    5 medidos    3,5%
    m³   (concreto)   55 itens    0 medidos    0%   ← nunca, nenhuma vez
    m²   (fôrma)      53 itens    0 medidos    0%   ← nunca, nenhuma vez

**Contar, o motor conta. Volume e fôrma, nunca mediu.**

🔎 O fio: o arquivo `005-1515-1PV-FOR-R03 levantamento volume.dxf` — "FOR" é
FÔRMA, a prancha que é literalmente feita de retângulo de pilar e viga — deu:

    hachuras=51 paredes=2545 cotas=198 textos=390  ->  pilares=0

O detector tem CINCO filtros em série (nome do layer, 4 lados, retângulo,
escala, ilegível) e o log mostrava só o total. Impossível separar "a prancha
não tem pilar" de "o nome do layer não bateu".

🔑 Mesma cegueira do `blocos=0` de 26/08 — que só foi resolvida quando passou a
contar o descarte, e aí respondeu de primeira.

🚨 Este commit NÃO muda o filtro. Medir antes de mexer: em 10/08, 5 de 5 ideias
minhas morreram no teste ([[feedback_motor_sempre_pode_melhorar]]).
"""
import functools
import io
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fonte(nome):
    return io.open(os.path.join(_BACKEND, nome), encoding="utf-8").read()


# 🪤 06/09/2026 — `_consider_pilar_poly` tem DOIS chamadores: o laço de
# LWPOLYLINE e o de POLYLINE ("heavy", o formato do AutoCAD antigo). A prancha
# sintética só desenhava LWPOLYLINE, então apagar o laço de POLYLINE deixava o
# arquivo verde e devolvia a cegueira original — `pilares=0` sem nenhum motivo
# contado — justamente em arquivo de projeto velho. O parâmetro `formato`
# monta a MESMA prancha nos dois tipos de entidade.
_FORMATOS = ("LWPOLYLINE", "POLYLINE")


def _prancha_de_forma(caminho, formato="LWPOLYLINE"):
    import ezdxf
    doc = ezdxf.new("R2010"); doc.header["$INSUNITS"] = 6   # metros
    msp = doc.modelspace()
    for lay in ("PILAR", "PIL", "COLUNA", "EIXOS"):
        if lay not in doc.layers: doc.layers.add(lay)
    if formato == "LWPOLYLINE":
        def _fecha(layer, pts):
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
    elif formato == "POLYLINE":
        def _fecha(layer, pts):
            msp.add_polyline2d(pts, close=True, dxfattribs={"layer": layer})
    else:
        raise AssertionError("formato de contorno desconhecido: %r" % (formato,))
    _fecha("PILAR", [(0,0),(0.20,0),(0.20,0.40),(0,0.40)])                       # ACEITO
    _fecha("PILAR", [(2,0),(2.2,0),(2.2,.2),(2.4,.2),(2.4,.4),(2,.4)])           # nao_e_4_lados
    _fecha("PILAR", [(4,0),(5.0,0),(4.5,0.4),(4,0.4)])                           # nao_e_retangulo
    _fecha("PILAR", [(10,0),(20,0),(20,10),(10,10)])                             # fora_de_escala
    _fecha("PIL",    [(0,5),(0.2,5),(0.2,5.4),(0,5.4)])                          # nome_do_layer
    _fecha("COLUNA", [(1,5),(1.2,5),(1.2,5.4),(1,5.4)])
    _fecha("EIXOS",  [(2,5),(2.2,5),(2.2,5.4),(2,5.4)])
    # 🔑 Pilar REDONDO (Ø 30 cm): entra por um TERCEIRO laço, o de CIRCLE, que
    # nem passa por `_consider_pilar_poly`. Sem ele na prancha, apagar o laço
    # de CIRCLE não quebrava nada.
    msp.add_circle((6, 0), 0.15, dxfattribs={"layer": "PILAR"})
    # e um círculo em layer que NÃO é de pilar não pode virar pilar
    msp.add_circle((8, 0), 0.15, dxfattribs={"layer": "EIXOS"})
    doc.saveas(caminho); return caminho


def _extrair(montar):
    from dwg_extractor import extract_dxf
    cam = os.path.join(tempfile.mkdtemp(prefix="_pilar_"), "prancha.dxf")
    try:
        montar(cam); return extract_dxf(cam)
    finally:
        try: os.remove(cam)
        except OSError: pass



@pytest.mark.parametrize("formato", _FORMATOS)
def test_cada_filtro_do_pilar_conta_separado(formato):
    """Cinco motivos diferentes, cinco ações diferentes. Um total só não serve.

    🪤 O guarda antigo procurava as quatro strings `_desc_pil["..."] += 1` no
    fonte. Um `return` antes delas deixava o texto intacto e o contador morto —
    e a prancha de fôrma voltava a dizer `pilares=0` sem motivo.

    🪤 06/09/2026 — e depois disso a prancha sintética só existia em
    LWPOLYLINE, então apagar o laço de POLYLINE (o formato pesado, comum em
    arquivo de AutoCAD antigo) também ficava verde. Agora a MESMA prancha roda
    nos dois formatos.
    """
    ex = _extrair(functools.partial(_prancha_de_forma, formato=formato))
    d = dict(ex.pilares_descartados or {})

    assert d.get("nome_do_layer", 0) == 3, (
        "[%s] o filtro de NOME recusou %r contornos de 4 lados — esperava 3"
        % (formato, d.get("nome_do_layer")))
    assert d.get("nao_e_4_lados", 0) == 1, (
        "[%s] polilinha de 6 vértices no layer PILAR foi recusada SEM CONTAR "
        "(nao_e_4_lados=%r): o filtro está mudo e `pilares=0` volta a não "
        "dizer nada" % (formato, d.get("nao_e_4_lados")))
    assert d.get("nao_e_retangulo", 0) == 1, (
        "[%s] trapézio no layer PILAR não foi contado: %r"
        % (formato, d.get("nao_e_retangulo")))
    assert d.get("fora_de_escala", 0) == 1, (
        "[%s] retângulo de 10 × 10 m não foi contado como fora de escala: %r"
        % (formato, d.get("fora_de_escala")))
    # 🩸 ACHADO 06/09/2026: o 5º contador (`ilegivel`) NUNCA é incrementado —
    # o `except Exception: return` de `_consider_pilar_poly` engole o erro sem
    # contar. `assert "ilegivel" in d` não provava nada (a chave nasce no
    # dicionário inicial). Enquanto o contador estiver morto, o guarda honesto
    # é este: a chave existe E vale zero. Se alguém ligar o contador de
    # verdade, este assert avisa — e aí a nota sai daqui.
    assert d.get("ilegivel", None) == 0, (
        "[%s] o 5º contador saiu do dicionário ou passou a contar: %s"
        % (formato, d))


@pytest.mark.parametrize("formato", _FORMATOS)
def test_CONTROLE_o_pilar_BOM_continua_passando(formato):
    """Contar descarte não pode virar descartar tudo.

    Sem este controle, um detector que recusasse todo mundo (e contasse
    direitinho) passaria pelo teste acima.

    🔑 O pilar REDONDO entra por outro laço (CIRCLE) — e o círculo no layer
    `EIXOS` tem que continuar de fora.
    """
    ex = _extrair(functools.partial(_prancha_de_forma, formato=formato))
    aceitos = [(r.layer, round(r.w_m, 3), round(r.h_m, 3),
                bool(getattr(r, "circular", False)))
               for r in (ex.struct_rects or [])]
    assert sorted(aceitos) == sorted([
        ("PILAR", 0.2, 0.4, False),   # retângulo 20 × 40 cm
        ("PILAR", 0.3, 0.3, True),    # pilar redondo Ø 30 cm
    ]), (
        "[%s] a lista de pilares ACEITOS mudou: %s. Esperado o retângulo de "
        "20 × 40 cm (pelo laço de %s) E o pilar redondo de Ø 30 cm (pelo laço "
        "de CIRCLE), e NADA do layer EIXOS." % (formato, aceitos, formato))

def test_guarda_os_NOMES_dos_layers_recusados():
    """🔑 É o nome que decide entre "não tem pilar" e "o layer se chama PIL"."""
    ext = _fonte("dwg_extractor.py")
    assert "_amostra_layers" in ext, "não guarda nenhum nome de layer recusado"
    i = ext.find("def _consider_pilar_poly")
    trecho = ext[i:i + 3000]
    assert "if len(_pp) == 4:" in trecho, (
        "a amostra não filtra por contorno de 4 lados — todo traço solto do "
        "desenho entraria e a amostra viraria ruído")


def test_o_contador_CHEGA_no_log():
    """🪤 Contar e não gravar é o mesmo que não contar."""
    m = _fonte("main.py")
    assert "_descarte_de_pilares(extraction)" in m, "o contador não é usado"
    i = m.find('f"pilares={len(extraction.struct_rects or [])}')
    assert i > 0, "não achei o `pilares=` no log de geometria"
    assert "_descarte_de_pilares" in m[i:i + 1600], (
        "o descarte não está no MESMO log do `pilares=` — separado, ninguém "
        "cruza os dois")


def test_log_LIMPO_quando_nao_houve_descarte():
    """A maioria das pranchas é de arquitetura e não tem pilar nenhum. Se o
    sufixo aparecesse sempre, viraria ruído — foi o erro do `cotas=-`."""
    from main import _descarte_de_pilares as f

    class _Vazio:
        pilares_descartados = {}

    class _Zerado:
        pilares_descartados = {"nome_do_layer": 0, "nao_e_4_lados": 0,
                               "nao_e_retangulo": 0, "fora_de_escala": 0,
                               "ilegivel": 0, "amostra_layers": []}

    assert f(_Vazio()) == ""
    assert f(_Zerado()) == ""
    assert f(object()) == "", "objeto sem o campo não pode explodir o log"


def test_CONTROLE_POSITIVO_com_DXF_de_verdade():
    """🧪 Monta uma prancha de fôrma com pilares em nomes REAIS de projeto
    brasileiro e confere o que passa e o que é recusado.

    Este teste é a prova de que o instrumento funciona — e foi ele que mostrou
    que `COLUNA` (português) é recusado enquanto `COLUMN` (inglês) passa, num
    produto brasileiro.
    """
    import ezdxf
    from dwg_extractor import extract_dxf

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6            # metros
    msp = doc.modelspace()
    nomes = ["PILAR", "PILARES", "PIL", "P", "EST-P", "FORMA-PIL",
             "ESTRUT_PILAR", "COLUNA"]
    for i, lay in enumerate(nomes):
        if lay not in doc.layers:
            doc.layers.add(lay)
        x = i * 2.0
        msp.add_lwpolyline([(x, 0), (x + 0.20, 0), (x + 0.20, 0.40), (x, 0.40)],
                           close=True, dxfattribs={"layer": lay})
    cam = os.path.join(os.environ.get("TEMP", "."), "_teste_pilar_ctrl.dxf")
    doc.saveas(cam)
    try:
        ex = extract_dxf(cam)
        aceitos = {r.layer for r in (ex.struct_rects or [])}
        d = ex.pilares_descartados or {}

        # o que passa hoje
        assert "PILAR" in aceitos and "PILARES" in aceitos, aceitos
        # o que é recusado por NOME — e o contador tem que ver
        assert d.get("nome_do_layer", 0) >= 4, d
        recusados = dict(d.get("amostra_layers") or [])
        assert "PIL" in recusados and "COLUNA" in recusados, (
            "a amostra não trouxe os nomes recusados: %s" % recusados)
        # 🚨 documenta o estado ATUAL, não o desejado: se alguém alargar o
        # filtro pra pegar COLUNA/PIL, este teste avisa que o comportamento
        # mudou e obriga a revisar a decisão de propósito.
        assert "COLUNA" not in aceitos, (
            "o filtro passou a aceitar COLUNA — mudança de COMPORTAMENTO. "
            "Se foi de propósito, atualize este teste e meça o efeito.")
    finally:
        try:
            os.remove(cam)
        except OSError:
            pass


def test_o_filtro_so_muda_DEPOIS_de_medir():
    """🚨 Instrumento e conserto são commits separados. Alterar o filtro junto
    contamina a medição — não dá pra saber o que era antes.

    ✅ 01/09/2026 — A MEDIÇÃO FOI FEITA e o filtro foi alargado UMA vez, de
    ("PILAR","COLUMN") para incluir "COLS". O que o log de produção disse:
      · 213 pranchas com o log do descarte; **210 saem com `pilares=0`** (98,6%)
        e só 3 detectam pilar;
      · dos nomes recusados por NOME, a amostra real é DT-INS-AC, EQ-02,
        K-LEGEN, BORDAS ESPESSAS, Defpoints, "Nível 1", DI-Tabelas, Markups e
        "0" — **nenhum é layer de pilar**, ou seja, o filtro de nome estava
        ACERTANDO;
      · o gargalo é outro: o detector só olha polilinha FECHADA, e o arquivo do
        cliente-23 (RACIONAL) não tem nenhuma — 2.158 LINE, 448 HATCH, 0
        LWPOLYLINE. Os 54 pilares dele são HACHURA, no layer `S-COLS`.
    "COLS" entrou porque é o padrão AIA (Structural Columns) e apareceu num
    arquivo real. 🪤 "COLUNA" foi testado e RECUSADO: o cliente-54 (METAL-AR) tem o
    layer `AC-Indicação coluna Frigorígenas`, que é coluna de ar-condicionado.

    A regra continua valendo pro PRÓXIMO que quiser alargar: meça primeiro.
    """
    import structural_extractor as se
    assert se._PILAR_TOKENS == ("PILAR", "COLUMN", "COLS"), (
        "os tokens de pilar mudaram: %r. Meça com o log em produção "
        "(stage motor:geometria, campo pilares_descartados) e traga a amostra "
        "de NOMES antes de alargar de novo." % (se._PILAR_TOKENS,))
