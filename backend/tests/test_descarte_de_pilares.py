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
Giovani em [[project_caso_giovani_20260815]]).

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
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fonte(nome):
    return io.open(os.path.join(_BACKEND, nome), encoding="utf-8").read()


def test_cada_filtro_do_pilar_conta_separado():
    """Cinco motivos diferentes, cinco ações diferentes. Um total só não serve."""
    ext = _fonte("dwg_extractor.py")
    i = ext.find("def _consider_pilar_poly")
    assert i > 0, "o detector de pilar sumiu"
    trecho = ext[i:i + 3000]
    for chave in ("nome_do_layer", "nao_e_4_lados", "nao_e_retangulo",
                  "fora_de_escala"):
        assert '_desc_pil["%s"] += 1' % chave in trecho, (
            "o filtro %r recusa pilar sem contar" % chave)


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
        Edvaldo (RACIONAL) não tem nenhuma — 2.158 LINE, 448 HATCH, 0
        LWPOLYLINE. Os 54 pilares dele são HACHURA, no layer `S-COLS`.
    "COLS" entrou porque é o padrão AIA (Structural Columns) e apareceu num
    arquivo real. 🪤 "COLUNA" foi testado e RECUSADO: o Tiago (METAL-AR) tem o
    layer `AC-Indicação coluna Frigorígenas`, que é coluna de ar-condicionado.

    A regra continua valendo pro PRÓXIMO que quiser alargar: meça primeiro.
    """
    import structural_extractor as se
    assert se._PILAR_TOKENS == ("PILAR", "COLUMN", "COLS"), (
        "os tokens de pilar mudaram: %r. Meça com o log em produção "
        "(stage motor:geometria, campo pilares_descartados) e traga a amostra "
        "de NOMES antes de alargar de novo." % (se._PILAR_TOKENS,))
