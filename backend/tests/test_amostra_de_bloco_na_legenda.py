# -*- coding: utf-8 -*-
"""O SÍMBOLO desenhado na legenda da prancha não sai como peça "✓ MEDIDO".

🩸 26/09/2026, job 32a27efc (muro de arrimo, 7 DXF do Eberick, folha inteira
no modelo). A planilha trouxe "Pilar nasce = 1 un ✓ MEDIDO" em 3 pranchas. O
único INSERT 'IND PILAR NASCE' de cada folha era o símbolo da coluna
"LEGENDA PILARES:" — "PILAR NASCE" logo ao lado, "PILAR MORRE" e "PILAR
CONTINUA" alinhados embaixo. Na planta, nenhum: a verdade era 0. O motor
conta todo INSERT; o prompt diz que contagem de bloco é MEDIDO; e a trava de
anotação só olha LAYER citado.

📏 17 DXF de 6 clientes: 43 blocos com amostra contada como peça, 0 falso
positivo em 1.440 inserções. No banco, piso de 21 linhas confirmadas em 6
jobs (1,2% das contagens de bloco confirmadas).

🔑 Três pedaços, um guarda cada:
  1. `amostras_de_legenda` (pura): rótulo ao lado que repete o nome, numa
     COLUNA de rótulos;
  2. o extrator grava `amostras_legenda` pelas posições que FICARAM depois da
     leitura por folha, e conta pra IA na MESMA linha do bloco;
  3. `selo_apos_amostra_de_legenda` SÓ REBAIXA a linha cuja quantidade é a
     contagem do bloco (a amostra está dentro do número) — e o motor a chama
     entre a trava de anotação e a da soma.
Dados 100% sintéticos: o repo é público.
"""
import ast
import functools
import io
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
from dwg_extractor import amostras_de_legenda  # noqa: E402
from engine_rules import selo_apos_amostra_de_legenda as rebaixa  # noqa: E402

H = 2.0          # altura do rótulo (a do caso: 2 mm)


def _coluna(linhas, x=100.0, y=60.0, h=H, passo=6.0, lado=3.0, folga=2.0):
    """Legenda: por linha, o símbolo (caixa lado × lado) e o rótulo à direita,
    todos os rótulos no mesmo x. `linhas` = [(bloco ou None, rótulo)]."""
    ins, tx = [], []
    for k, (bloco, rot) in enumerate(linhas):
        yk = y - k * passo
        if bloco:
            ins.append((bloco, (x, yk, x + lado, yk + lado), (x, yk)))
        tx.append((rot, x + lado + folga, yk - 1.2, h))
    return ins, tx


def _n(res, nome):
    return len(res.get(nome, []))


# ══════════════════════════════════════════════════════════════════════════
#  1. A REGRA PURA
# ══════════════════════════════════════════════════════════════════════════
def test_P1_o_caso_o_simbolo_da_LEGENDA_PILARES_e_amostra():
    ins, tx = _coluna([(None, "PILAR CONTINUA"), (None, "PILAR MORRE"),
                       ("IND PILAR NASCE", "PILAR NASCE")])
    tx.append(("LEGENDA PILARES:", 100.0, 66.0, 2.5))
    # a planta, longe: eixos de pilar com o nome do pilar ao lado
    for k in range(3):
        ins.append(("Eixos do pilar", (10.0 + 40 * k, 10.0, 13.0 + 40 * k, 13.0),
                    (10.0 + 40 * k, 10.0)))
        tx.append(("P%d" % (k + 1), 15.0 + 40 * k, 9.0, H))
    res = amostras_de_legenda(ins, tx)
    assert res == {"IND PILAR NASCE": [(100.0, 48.0)]}, res


def test_P2_amostra_mais_pecas_de_verdade_so_a_da_legenda_conta():
    ins, tx = _coluna([("SECCIONAMENTO DE ELETRODUTO", "- SECCIONAMENTO DE ELETRODUTO."),
                       ("BUCHA DE REDUÇÃO", "- BUCHA DE REDUÇÃO."),
                       ("CONDU. C", '- CONDULETE TIPO "C".')])
    for k in range(6):                                   # as 6 da planta
        ins.append(("SECCIONAMENTO DE ELETRODUTO",
                    (1000.0 + 50 * k, 500.0, 1003.0 + 50 * k, 503.0), (1000.0 + 50 * k, 500.0)))
    res = amostras_de_legenda(ins, tx)
    assert res["SECCIONAMENTO DE ELETRODUTO"] == [(100.0, 60.0)], "só a da legenda"
    assert _n(res, "BUCHA DE REDUÇÃO") == 1
    assert _n(res, "CONDU. C") == 1, "abreviação do nome: 'condu' → 'condulete'"


def test_P3_simbolo_a_8_8_alturas_do_rotulo_e_pego():
    """A BUCHA do caso elétrico estava a 8,8h do rótulo: 6h a perdia."""
    ins, tx = _coluna([("BUCHA DE REDUÇÃO", "- BUCHA DE REDUÇÃO."), (None, "- LUVA."),
                       (None, "- CURVA 90.")], folga=8.8 * H)
    assert _n(amostras_de_legenda(ins, tx), "BUCHA DE REDUÇÃO") == 1


def test_CONTROLE_P3_rotulo_alem_de_10_alturas_nao_e_do_simbolo():
    ins, tx = _coluna([("BUCHA DE REDUÇÃO", "- BUCHA DE REDUÇÃO."), (None, "- LUVA."),
                       (None, "- CURVA 90.")], folga=10.5 * H)
    assert amostras_de_legenda(ins, tx) == {}


@pytest.mark.parametrize("bloco, rotulo, porque", [
    ("ELETRODUTO DESCENDO", "- INDICAÇÃO DE ELETRODUTO QUE DESCE",
     "1 palavra em comum com ≥5 letras"),
    ("SPOT", "SPOT EMBUTIDO NO FORRO", "todas as palavras do nome"),
    ("LUZ TETO ALTA", "LUZ DE TETO", "2 palavras em comum, nenhuma com 5 letras"),
    ("REDUCAO", "- REDUÇÃO.", "acento não separa a palavra"),
])
def test_as_formas_de_o_rotulo_repetir_o_nome(bloco, rotulo, porque):
    ins, tx = _coluna([(bloco, rotulo), (None, "- LUVA."), (None, "- CURVA 90.")])
    assert _n(amostras_de_legenda(ins, tx), bloco) == 1, porque


def test_vizinho_da_coluna_sem_palavra_tambem_conta():
    """A coluna é de TEXTOS alinhados — o código curto do lado também é rótulo."""
    ins, tx = _coluna([("BUCHA DE REDUÇÃO", "- BUCHA DE REDUÇÃO."), (None, "C1"), (None, "C2")])
    assert _n(amostras_de_legenda(ins, tx), "BUCHA DE REDUÇÃO") == 1


# ── controles negativos ──────────────────────────────────────────────────────
def test_N1_etiqueta_ao_lado_da_peca_na_planta_SEM_coluna_nao_e_amostra():
    """📏 Sem a coluna entravam 6 falsos: a etiqueta da peça repete o nome."""
    ins = [("ARANDELA", (0.0, 0.0, 3.0, 3.0), (0.0, 0.0)),
           ("CONEXAO TE DRENAGEM", (200.0, 0.0, 203.0, 3.0), (200.0, 0.0)),
           ("JOELHO DRENAGEM", (200.0, 4.0, 203.0, 7.0), (200.0, 4.0))]
    tx = [("ARANDELA h=1,40m", 5.0, -1.2, H),
          ("Drenagem Superficial", 205.0, 2.0, H)]
    assert amostras_de_legenda(ins, tx) == {}


def test_N2_nome_curto_nao_casa_com_rotulo_de_legenda():
    """O 'C' do interruptor aparece 18× numa legenda de interruptores."""
    ins, tx = _coluna([("C", "SIMPLES HOTEL (01 TECLA)"), ("E", "C01; C02"),
                       ("C", "TRIPLO HOTEL (03 TECLAS)")])
    assert amostras_de_legenda(ins, tx) == {}


def test_N3_rotulo_que_nao_repete_o_nome_nao_marca():
    """Limite documentado: SOLDA × "CONEXÃO APARAFUSADA" escapa."""
    ins, tx = _coluna([("SOLDA", "- CONEXÃO APARAFUSADA."), (None, "- LUVA."),
                       (None, "- CURVA 90.")])
    assert amostras_de_legenda(ins, tx) == {}


def test_N6_coluna_de_nomes_de_ambiente_perto_de_bloco_de_outro_nome():
    ins, tx = _coluna([("VASO SANITARIO", "BANHEIRO"), (None, "COZINHA"), (None, "SALA")])
    assert amostras_de_legenda(ins, tx) == {}


def test_CONTROLE_uma_palavra_curta_em_comum_nao_basta():
    ins, tx = _coluna([("TUBO GUIA", "TUBO DE COBRE"), (None, "- LUVA."), (None, "- CURVA 90.")])
    assert amostras_de_legenda(ins, tx) == {}


def test_CONTROLE_simbolo_largo_demais_nao_e_amostra():
    """Mais de 12 alturas de largura é desenho, não símbolo de legenda."""
    ins, tx = _coluna([("IND PILAR NASCE", "PILAR NASCE"), (None, "PILAR MORRE"),
                       (None, "PILAR CONTINUA")], lado=13 * H, folga=1.0)
    assert amostras_de_legenda(ins, tx) == {}


def test_CONTROLE_rotulo_longe_na_vertical_nao_e_do_simbolo():
    ins, tx = _coluna([(None, "PILAR MORRE"), (None, "PILAR CONTINUA"), (None, "PILAR NASCE")])
    ins = [("IND PILAR NASCE", (100.0, 80.0, 103.0, 83.0), (100.0, 80.0))]   # ~10h acima
    assert amostras_de_legenda(ins, tx) == {}


def test_CONTROLE_coluna_longe_demais_na_vertical_nao_e_coluna():
    ins, tx = _coluna([("IND PILAR NASCE", "PILAR NASCE"), (None, "PILAR MORRE"),
                       (None, "PILAR CONTINUA")], passo=16 * H)
    assert amostras_de_legenda(ins, tx) == {}


@pytest.mark.parametrize("ins, tx", [
    ([], [("PILAR NASCE", 0, 0, 2)]),
    ([("IND PILAR NASCE", (0, 0, 1, 1), (0, 0))], []),
    (None, None),
    ([("X", None, (0, 0)), ("Y",)], [("a", "b", 0, 1), ("PILAR", 0, 0, 0)]),
])
def test_entrada_vazia_ou_torta_nao_quebra(ins, tx):
    assert amostras_de_legenda(ins, tx) == {}


# ══════════════════════════════════════════════════════════════════════════
#  2. O EXTRATOR — caixa pela inserção, número pelas posições que ficaram
# ══════════════════════════════════════════════════════════════════════════
def _legenda_no_dxf(msp, x, y, h, bloco_escala):
    """Coluna "LEGENDA PILARES" no desenho: o símbolo é o bloco inserido
    ESCALADO (a definição é pequena e em volta da origem)."""
    for k, rot in enumerate(("PILAR CONTINUA", "PILAR MORRE", "PILAR NASCE")):
        msp.add_text(rot, dxfattribs={"height": h, "insert": (x + 2.5 * h, y - 3 * k * h - 0.6 * h)})
    msp.add_blockref("IND PILAR NASCE", (x + 0.75 * h, y - 6 * h + 0.75 * h),
                     dxfattribs={"xscale": bloco_escala, "yscale": bloco_escala})


def _prancha(tmp_path, na_planta=0):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    blk = doc.blocks.new("IND PILAR NASCE")
    blk.add_circle((0, 0), 0.15)                        # × 10 = 3 de diâmetro
    # molde de atributo LONGE do desenho (× 10 = 40): não é o símbolo, e a
    # caixa não pode esticar até ele
    blk.add_attdef("NUMERO", (4, 0), dxfattribs={"height": 0.2})
    eix = doc.blocks.new("Eixos do pilar")
    eix.add_line((-1, 0), (1, 0))
    eix.add_line((0, -1), (0, 1))
    msp = doc.modelspace()
    for k in range(3):
        msp.add_blockref("Eixos do pilar", (100 + 300 * k, 100))
        msp.add_text("P%d" % (k + 1), dxfattribs={"height": 2, "insert": (104 + 300 * k, 99)})
    for k in range(na_planta):
        msp.add_blockref("IND PILAR NASCE", (400 + 300 * k, 100),
                         dxfattribs={"xscale": 10, "yscale": 10})
    _legenda_no_dxf(msp, 740.0, 170.0, 2.0, 10)
    p = str(tmp_path / "prancha.dxf")
    doc.saveas(p)
    return p


@pytest.fixture(autouse=True)
def _folha_ligada(monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)


def _bloco(ex, nome):
    return next((b for b in ex.blocks if b.name == nome), None)


def test_o_extrator_marca_o_simbolo_da_legenda(tmp_path):
    ex = dx.extract_dxf(_prancha(tmp_path))
    b = _bloco(ex, "IND PILAR NASCE")
    assert (b.count, b.amostras_legenda) == (1, 1)
    assert _bloco(ex, "Eixos do pilar").amostras_legenda == 0
    assert ex.metadata.get("amostras_de_legenda") == {"IND PILAR NASCE": 1}


def test_a_peca_da_planta_continua_peca(tmp_path):
    ex = dx.extract_dxf(_prancha(tmp_path, na_planta=2))
    b = _bloco(ex, "IND PILAR NASCE")
    assert (b.count, b.amostras_legenda) == (3, 1), "a contagem não muda; 1 de 3 é da legenda"


def test_a_ia_fica_sabendo_na_MESMA_linha_do_bloco(tmp_path):
    txt = dx.extract_dxf(_prancha(tmp_path, na_planta=2)).to_structured_prompt()
    secao = txt.split("CONTAGEM DE BLOCOS", 1)[1].split("\n\n", 1)[0]
    linhas = [ln for ln in secao.splitlines() if "IND PILAR NASCE" in ln]
    assert len(linhas) == 1, secao
    assert "IND PILAR NASCE: 3 un" in linhas[0]
    assert "[1 delas = símbolo desenhado na LEGENDA, não peça]" in linhas[0]
    assert not any("LEGENDA, não peça" in ln for ln in secao.splitlines()
                   if "Eixos do pilar" in ln)


def test_CONTROLE_sem_legenda_nada_muda(tmp_path):
    doc = ezdxf.readfile(_prancha(tmp_path, na_planta=2))
    msp = doc.modelspace()
    for t in list(msp.query("TEXT")):
        if t.dxf.text.startswith("PILAR"):
            msp.delete_entity(t)
    p = str(tmp_path / "sem_legenda.dxf")
    doc.saveas(p)
    ex = dx.extract_dxf(p)
    assert _bloco(ex, "IND PILAR NASCE").amostras_legenda == 0
    assert "amostras_de_legenda" not in ex.metadata
    assert "LEGENDA, não peça" not in ex.to_structured_prompt()


def _folha_com_legenda_no_detalhe(tmp_path):
    """A folha do guarda vizinho (planta em cima, DETALHE D embaixo, caixa
    (4,6)-(12,12), em metros) + a coluna da legenda DENTRO do detalhe e uma
    peça 'IND PILAR NASCE' de verdade na planta."""
    import test_desenho_no_modelo as tdm
    p = tdm._folha(tmp_path)
    doc = ezdxf.readfile(p)
    blk = doc.blocks.new("IND PILAR NASCE")
    blk.add_circle((0, 0), 0.015)
    msp = doc.modelspace()
    _legenda_no_dxf(msp, 6.0, 11.0, 0.1, 5)
    msp.add_blockref("IND PILAR NASCE", (10, 24), dxfattribs={"xscale": 5, "yscale": 5})
    doc.saveas(p)
    return p


def test_o_numero_sai_das_posicoes_que_FICARAM_depois_da_leitura_por_folha(tmp_path):
    """A legenda caiu num desenho 'fora' e a folha já tirou o símbolo da
    contagem: sobrou a peça da planta, e ela NÃO é amostra."""
    ex = dx.extract_dxf(_folha_com_legenda_no_detalhe(tmp_path))
    b = _bloco(ex, "IND PILAR NASCE")
    assert (b.count, b.amostras_legenda) == (1, 0)
    assert "amostras_de_legenda" not in ex.metadata


def test_CONTROLE_sem_a_leitura_por_folha_o_simbolo_volta_a_ser_amostra(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_folha_com_legenda_no_detalhe(tmp_path))
    b = _bloco(ex, "IND PILAR NASCE")
    assert (b.count, b.amostras_legenda) == (2, 1)


# ══════════════════════════════════════════════════════════════════════════
#  3. O SELO — só rebaixa, e só a contagem que inclui a amostra
# ══════════════════════════════════════════════════════════════════════════
AMOSTRAS = {"IND PILAR NASCE": (1, 1), "SECCIONAMENTO DE ELETRODUTO": (7, 1)}

#: as três formas com que a IA escreveu a linha no caso (texto reescrito)
OBS_DO_CASO = [
    "Fonte: 1 INSERT do bloco 'IND PILAR NASCE' (CONTAGEM DE BLOCOS). Indica um pilar que nasce.",
    "Fonte: bloco 'IND PILAR NASCE' — 1 INSERT contado em 'CONTAGEM DE BLOCOS'.",
    "Fonte: 1 INSERT do bloco 'IND PILAR NASCE' contado na seção CONTAGEM DE BLOCOS.",
]


@pytest.mark.parametrize("obs", OBS_DO_CASO)
def test_P1_a_linha_do_caso_sai_laranja_com_o_aviso_na_frente(obs):
    conf, nova, mexeu = rebaixa("confirmado", obs, 1, "un", AMOSTRAS)
    assert (conf, mexeu) == ("estimado", True)
    assert nova.startswith("⚠ 1 das 1 inserções do bloco 'IND PILAR NASCE' são o SÍMBOLO "
                           "desenhado na LEGENDA da prancha — na planta: 0."), nova
    assert nova.endswith(obs), "a observação da IA fica inteira, depois do aviso"


def test_P2_contagem_inflada_rebaixa_e_diz_quantas_sao_da_planta():
    obs = "Fonte: 7 INSERTs do bloco 'SECCIONAMENTO DE ELETRODUTO'."
    conf, nova, mexeu = rebaixa("confirmado", obs, 7, "un", AMOSTRAS)
    assert (conf, mexeu) == ("estimado", True)
    assert nova.startswith("⚠ 1 das 7 inserções do bloco 'SECCIONAMENTO DE ELETRODUTO' "
                           "são o SÍMBOLO desenhado na LEGENDA da prancha — na planta: 6."), nova


def test_P2_CONTROLE_a_IA_ja_descontou_a_amostra_fica_como_esta():
    obs = "Fonte: bloco 'SECCIONAMENTO DE ELETRODUTO', 7 INSERTs menos 1 da legenda."
    assert rebaixa("confirmado", obs, 6, "un", AMOSTRAS) == ("confirmado", obs, False)


@pytest.mark.parametrize("unit", ["m", "m²", "kg", "vb"])
def test_N4_so_vale_pra_contagem(unit):
    assert rebaixa("confirmado", OBS_DO_CASO[0], 1, unit, AMOSTRAS)[2] is False


def test_N5_linha_que_cita_outro_bloco_nao_muda():
    """A linha dos 33 pilares cita 'Eixos do pilar: 33 un' e também o 'IND
    PILAR NASCE' — mas 33 não é a contagem do bloco com amostra."""
    obs = ("33 pilares contados, confirmado pela contagem de blocos 'Eixos do pilar: "
           "33 un'. Bloco 'IND PILAR NASCE: 1 un' indica 1 pilar que nasce.")
    assert rebaixa("confirmado", obs, 33, "un", AMOSTRAS) == ("confirmado", obs, False)


def test_CONTROLE_linha_que_ja_esta_laranja_nao_ganha_aviso_de_novo():
    assert rebaixa("estimado", OBS_DO_CASO[0], 1, "un", AMOSTRAS) == (
        "estimado", OBS_DO_CASO[0], False)


def test_CONTROLE_bloco_sem_amostra_nao_rebaixa():
    assert rebaixa("confirmado", OBS_DO_CASO[0], 1, "un",
                   {"IND PILAR NASCE": (1, 0)}) == ("confirmado", OBS_DO_CASO[0], False)


@pytest.mark.parametrize("amostras", [{}, None, {"IND PILAR NASCE": "x"},
                                      {"IND PILAR NASCE": (None, 1)}])
def test_CONTROLE_sem_amostra_valida_nada_muda(amostras):
    assert rebaixa("confirmado", OBS_DO_CASO[0], 1, "un", amostras) == (
        "confirmado", OBS_DO_CASO[0], False)


# ══════════════════════════════════════════════════════════════════════════
#  4. O MOTOR CHAMA — no lugar certo, com a contagem da extração
# ══════════════════════════════════════════════════════════════════════════
_MAIN = os.path.join(os.path.dirname(_AQUI), "main.py")


@functools.lru_cache(maxsize=1)
def _process_job():
    """Uma leitura só: o parse do main.py leva dezenas de segundos."""
    arv = ast.parse(io.open(_MAIN, encoding="utf-8").read())
    return next(n for n in ast.walk(arv)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == "process_job")


def _chamadas(fn, nome):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "") == nome]


def _lista_que_contem(fn, no):
    for pai in ast.walk(fn):
        for campo in ("body", "orelse", "finalbody"):
            lista = getattr(pai, campo, None)
            if isinstance(lista, list) and no in lista:
                return lista
    return None


def test_o_motor_chama_a_regra_uma_vez_e_usa_o_retorno():
    fn = _process_job()
    ch = _chamadas(fn, "_regra_amostra")
    assert len(ch) == 1, "a regra da amostra de legenda sumiu (ou tem isca) em process_job"
    alvos = {n.id for t in ch[0].targets for n in ast.walk(t) if isinstance(n, ast.Name)}
    assert {"conf", "obs_raw", "_era_legenda"} <= alvos, sorted(alvos)
    args = [getattr(a, "id", None) for a in ch[0].value.args]
    assert args == ["conf", "obs_raw", "qty", "normalized_unit", "_blocos_amostra"], args


def test_a_regra_roda_entre_a_trava_de_anotacao_e_a_da_soma_no_mesmo_bloco():
    """Incondicional e ANTES da soma: mesma lista de instruções que a trava da
    soma. Depois da de anotação: ela já pode ter rebaixado (aí esta não mexe)."""
    fn = _process_job()
    amostra = _chamadas(fn, "_regra_amostra")[0]
    soma = _chamadas(fn, "_regra_soma")[0]
    lista = _lista_que_contem(fn, soma)
    assert lista is not None and amostra in lista, (
        "a regra não está no mesmo bloco da trava da soma — atrás de um `if` "
        "ela vira opcional")
    assert lista.index(amostra) < lista.index(soma)
    anot = [n for n in ast.walk(fn) if isinstance(n, ast.If)
            and "_layer_is_anotacao" in {getattr(c.func, "id", None) for c in ast.walk(n.test)
                                          if isinstance(c, ast.Call)}
            and "_contagem_de_bloco_citada" in {getattr(c.func, "id", None)
                                                for c in ast.walk(n.test) if isinstance(c, ast.Call)}]
    assert anot and max(a.end_lineno for a in anot) < amostra.lineno


def test_o_rebaixamento_marca_rebaixado_pela_fonte():
    """Sem a marca, o cross-check re-promove o item que esta regra rebaixou."""
    fn = _process_job()
    ramos = [n for n in ast.walk(fn) if isinstance(n, ast.If)
             and isinstance(n.test, ast.Name) and n.test.id == "_era_legenda"]
    assert ramos, "sumiu o `if _era_legenda:`"
    assert any(isinstance(x, ast.Assign) and isinstance(x.value, ast.Constant)
               and x.value.value is True
               and any(getattr(t, "id", "") == "_rebaixado_pela_fonte" for t in x.targets)
               for r in ramos for x in ast.walk(r))


def test_a_contagem_das_amostras_vem_da_extracao():
    fn = _process_job()
    ds = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
          and any(getattr(t, "id", "") == "_blocos_amostra" for t in n.targets)
          and isinstance(n.value, ast.DictComp)]
    assert ds, "`_blocos_amostra` não é montado da extração"
    dc = ds[0].value
    assert "extraction" in {x.id for x in ast.walk(dc.generators[0].iter) if isinstance(x, ast.Name)}
    assert isinstance(dc.value, ast.Tuple)
    assert [getattr(e, "attr", None) for e in dc.value.elts] == ["count", "amostras_legenda"]


def test_a_regra_NAO_foi_reimplementada_no_motor():
    corpo = "".join(ast.dump(n) for n in _process_job().body)
    assert "desenhado na LEGENDA" not in corpo, "o texto do aviso voltou pro motor"
