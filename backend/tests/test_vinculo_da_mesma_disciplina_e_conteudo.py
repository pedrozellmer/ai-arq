# -*- coding: utf-8 -*-
"""O vínculo do Revit DA MESMA disciplina é o conteúdo, não o contexto.

🩸 30/09/2026 — H13 do estudo do acervo. Uma implantação "construir e demolir"
trazia o prédio inteiro dentro do vínculo de arquitetura: 16 linhas, 0 medidas,
e "fornecimento e instalação de toldo 3 un" — os 3 toldos estavam marcados
DEMOLIR. O Revit exporta um bloco por INSTÂNCIA × VISTA ("<base>_rvt-N-<vista>"),
com conteúdo diferente por vista (planta 1.503 peças × corte 15) e muitos
vazios (60 de 72): só a vista de planta, e cada instância uma vez.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402

BASE = "OBRA-ARQ-08PE-PREDIO"


def _peca(doc, nome):
    if nome not in doc.blocks:
        doc.blocks.new(nome).add_circle((0, 0), 0.1 + 0.01 * len(nome))


def _vinculo(doc, msp, nome, pecas, x=0.0):
    b = doc.blocks.new(nome)
    for i, (p, n) in enumerate(pecas.items()):
        _peca(doc, p)
        for k in range(n):
            b.add_blockref(p, (i * 3.0, k * 2.0))
    msp.add_blockref(nome, (x, 0))


def _arquivo(tmp_path, nome_arquivo="IMPLANTACAO-ARQ-EXE-R01.dxf", extra=None):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    if extra:
        extra(doc, msp)
    # instância 1: planta (com as peças) e corte (outra amostra)
    _vinculo(doc, msp, BASE + "_rvt-1-PLANTA TERREO",
             {"PORTA 80X210 - DEMOLIR": 3, "TOLDO - DEMOLIR": 3, "BACIA - EXISTENTE": 2})
    _vinculo(doc, msp, BASE + "_rvt-1-Corte 1", {"PORTA 80X210 - DEMOLIR": 1}, x=100)
    _vinculo(doc, msp, BASE + "_rvt-1-3D - Térreo", {"PORTA 80X210 - DEMOLIR": 9}, x=150)
    # instância 2: vazia na planta (não aparece) — e a 3 com 2 portas
    doc.blocks.new(BASE + "_rvt-2-PLANTA TERREO")
    msp.add_blockref(BASE + "_rvt-2-PLANTA TERREO", (200, 0))
    _vinculo(doc, msp, BASE + "_rvt-3-PLANTA TERREO", {"PORTA 80X210 - DEMOLIR": 2}, x=250)
    # a mesma instância 3 numa 2ª planta temática: não conta de novo
    _vinculo(doc, msp, BASE + "_rvt-3-PLANTA DE PISO", {"PORTA 80X210 - DEMOLIR": 1}, x=300)
    # vínculo de OUTRA disciplina: contexto
    _vinculo(doc, msp, "OBRA-HID-AGUA_rvt-1-PLANTA TERREO", {"REGISTRO": 7}, x=400)
    p = str(tmp_path / nome_arquivo)
    doc.saveas(p)
    return dx.extract_dxf(p)


def test_o_caso_as_pecas_de_dentro_do_vinculo_aparecem(tmp_path):
    # instância 1 pela planta (o corte e o 3D não somam), a 2 vazia não conta, a 3
    # uma vez só (a 2ª planta temática dela não soma de novo)
    pv = _arquivo(tmp_path).metadata.get("pecas_no_vinculo") or {}
    assert list(pv) == [BASE], pv
    d = pv[BASE]
    assert d["disciplina"] == "ARQ" and d["instancias"] == 2, d
    assert d["pecas"] == {"PORTA 80X210 - DEMOLIR": 5, "TOLDO - DEMOLIR": 3,
                          "BACIA - EXISTENTE": 2}, d


@pytest.mark.parametrize("vista", ["Corte 2", "{3D}", "Perspectiva Externa", "Detalhe 4"])
def test_instancia_que_so_aparece_em_vista_que_nao_e_planta_nao_conta(tmp_path, vista):
    def extra(doc, msp):
        _vinculo(doc, msp, BASE + "_rvt-4-" + vista, {"JANELA MAXIM-AIR - DEMOLIR": 6}, x=500)
    pv = _arquivo(tmp_path, extra=extra).metadata.get("pecas_no_vinculo") or {}
    assert "JANELA MAXIM-AIR - DEMOLIR" not in pv[BASE]["pecas"], pv


def test_vista_sem_tipo_como_o_nome_do_pavimento_entra(tmp_path):
    def extra(doc, msp):
        _vinculo(doc, msp, "OBRA-ARQ-ANEXO_rvt-1-1º Pav_", {"JANELA MAXIM-AIR - DEMOLIR": 6}, x=500)
    pv = _arquivo(tmp_path, extra=extra).metadata.get("pecas_no_vinculo") or {}
    assert pv["OBRA-ARQ-ANEXO"]["pecas"] == {"JANELA MAXIM-AIR - DEMOLIR": 6}, pv


def test_a_vista_que_repete_as_instancias_com_outro_n_nao_dobra(tmp_path):
    # o alojamento: a vista TIPOLOGIAS repete os 6 quartos no mesmo lugar, com OUTRO N
    def extra(doc, msp):
        for i in range(6):
            _vinculo(doc, msp, "OBRA-ARQ-ALOJ_rvt-%d-TÉRREO - ALOJAMENTO" % (31 + i),
                     {"BACIA": 1, "PIA": 1, "CHUVEIRO": 1}, x=600 + 10 * i)
            _vinculo(doc, msp, "OBRA-ARQ-ALOJ_rvt-%d-TÉRREO - TIPOLOGIAS" % (67 + i),
                     {"BACIA": 1}, x=700 + 10 * i)
    d = (_arquivo(tmp_path, extra=extra).metadata.get("pecas_no_vinculo") or {})["OBRA-ARQ-ALOJ"]
    assert d["instancias"] == 6 and d["pecas"] == {"BACIA": 6, "PIA": 6, "CHUVEIRO": 6}, d
    assert d["vista"] == "TÉRREO - ALOJAMENTO" and d["outras_vistas"] == ["TÉRREO - TIPOLOGIAS"], d


def test_a_ia_le_qual_vista_contou_e_quais_nao(tmp_path):
    txt = _arquivo(tmp_path).to_structured_prompt()
    assert "vista: PLANTA TERREO; outras vistas da mesma base NÃO somadas: PLANTA DE PISO" in txt, txt


def test_CONTROLE_arquivo_e_vinculo_sem_codigo_nao_contam(tmp_path):
    def extra(doc, msp):
        _vinculo(doc, msp, "CIDADE_CXA_rvt-1-PLANTA TERREO", {"CAIXA": 4}, x=500)
    pv = _arquivo(tmp_path, "IMPLANTACAO-EXE-R01.dxf", extra=extra).metadata.get("pecas_no_vinculo")
    assert not pv, pv


def test_o_main_passa_as_pecas_do_vinculo_pra_regra_do_selo():
    import ast
    sys.path.insert(0, _AQUI)
    from _corpo import fonte
    chamadas = [n for n in ast.walk(ast.parse(fonte("main.py"))) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_regra_vinculo"]
    assert len(chamadas) == 1, len(chamadas)
    assert [getattr(a, "id", None) for a in chamadas[0].args[-2:]] == ["_vinc_n", "_vinc_nomes"]


@pytest.mark.parametrize("cru,curto", [
    ("Rectangular Mullion - montante 50x75mm-9884787-PREDIO - TÉRREO - 1_100 _DEMOLIR _ CONSTRUIR_",
     "Rectangular Mullion - montante 50x75mm"),
    ("247 Porta de Abrir - 0_80x2_10 - DEMOLIR-13926749-PREDIO - TÉRREO", "247 Porta de Abrir - 0_80x2_10 - DEMOLIR"),
    ("247 Porta de Abrir - 0_80x2_10 - DEMOLIR-V14", "247 Porta de Abrir - 0_80x2_10 - DEMOLIR"),
    ("247 Porta de Abrir - 0_80x2_10 - DEMOLIR-V14-13926777-PREDIO", "247 Porta de Abrir - 0_80x2_10 - DEMOLIR"),
    ("TOLDO - DEMOLIR", "TOLDO - DEMOLIR"),       # sem id: fica
    ("Porta-0800x2100", "Porta-0800x2100"),                     # 4 dígitos é medida, não id
    ("Janela de Correr-1200-1000", "Janela de Correr-1200-1000"),  # medida com hífen também
])
def test_o_nome_da_peca_sem_o_id_e_a_vista_do_revit(cru, curto):
    assert dx._nome_da_peca_no_vinculo(cru) == curto


@pytest.mark.parametrize("cru,curto", [
    ("247 Porta P1_P2_P3 - 0_80x2_10 - DEMOLIR-V14-PREDIO - TÉRREO - 1_100 _DEMOLIR _ CONSTRUIR_",
     "247 Porta P1_P2_P3 - 0_80x2_10 - DEMOLIR"),
    ("Empty System Panel - Empty-V144-PREDIO - TÉRREO - 1_100 _DEMOLIR _ CONSTRUIR_",
     "Empty System Panel - Empty"),
    ("Janela basculante - EXISTENTE-V6-predio - térreo - 1_100 _demolir _ construir_",   # caixa diferente
     "Janela basculante - EXISTENTE"),
])
def test_a_variante_seguida_da_vista_da_instancia(cru, curto):
    assert dx._nome_da_peca_no_vinculo(cru, "PREDIO - TÉRREO - 1_100 _DEMOLIR _ CONSTRUIR_") == curto


def test_a_variante_junta_com_a_familia_de_dentro_do_mesmo_vinculo(tmp_path):
    vista = "PREDIO - TÉRREO"

    def extra(doc, msp):
        _vinculo(doc, msp, "OBRA-ARQ-ANEXO_rvt-1-" + vista,
                 {"Porta P1 - DEMOLIR-13926749-" + vista: 26, "Porta P1 - DEMOLIR-V14-" + vista: 7,
                  "Porta P1 - DEMOLIR-V8-" + vista: 3}, x=700)
    pv = _arquivo(tmp_path, extra=extra).metadata.get("pecas_no_vinculo") or {}
    assert pv["OBRA-ARQ-ANEXO"]["pecas"] == {"Porta P1 - DEMOLIR": 36}, pv


def test_a_mesma_familia_junta_e_a_peca_pequena_nao_some_no_corte(tmp_path):
    # 45 fragmentos de montante (id diferente cada) + 3 chuveiros a DEMOLIR
    pecas = {"Rectangular Mullion 50x75-%d-VISTA" % (9884700 + i): 2 for i in range(45)}
    pecas["CHUVEIRO - DEMOLIR"] = 3

    def extra(doc, msp):
        _vinculo(doc, msp, BASE + "_rvt-9-PLANTA TERREO", pecas, x=600)
    pv = _arquivo(tmp_path, extra=extra).metadata.get("pecas_no_vinculo") or {}
    assert pv[BASE]["pecas"]["Rectangular Mullion 50x75"] == 90, pv
    assert pv[BASE]["pecas"]["CHUVEIRO - DEMOLIR"] == 3, pv


def test_a_peca_pequena_com_fase_nao_cai_no_corte(tmp_path):
    # o caso: 100 linhas depois de juntar, e o toldo a DEMOLIR (3) empatava no fim
    pecas = {"PEÇA %02d" % i: 3 for i in range(60)}
    pecas["TOLDO - DEMOLIR"] = 3

    def extra(doc, msp):
        _vinculo(doc, msp, "OBRA-ARQ-ANEXO_rvt-1-PLANTA TERREO", pecas, x=800)
    pv = _arquivo(tmp_path, extra=extra).metadata.get("pecas_no_vinculo") or {}
    assert pv["OBRA-ARQ-ANEXO"]["pecas"].get("TOLDO - DEMOLIR") == 3, len(pv["OBRA-ARQ-ANEXO"]["pecas"])


def test_a_ia_le_as_pecas_e_a_fase(tmp_path):
    txt = _arquivo(tmp_path).to_structured_prompt()
    assert "PEÇAS DENTRO DO VÍNCULO DO REVIT DA MESMA DISCIPLINA" in txt
    assert "TOLDO - DEMOLIR: 3 un" in txt and "nunca fornecimento" in txt
    assert txt.count("o conteúdo deles é ESTE") == 1, txt   # uma vez, no cabeçalho
    assert "as peças de DENTRO dele" not in txt          # não em cada linha de vínculo
    assert "pecas_no_vinculo:" not in txt              # o dict cru não vai


def test_o_que_passa_do_limite_e_dito(tmp_path):
    pecas = {"PEÇA %03d" % i: 2 for i in range(130)}

    def extra(doc, msp):
        _vinculo(doc, msp, "OBRA-ARQ-ANEXO_rvt-1-PLANTA TERREO", pecas, x=900)
    ex = _arquivo(tmp_path, extra=extra)
    d = ex.metadata["pecas_no_vinculo"]["OBRA-ARQ-ANEXO"]
    assert len(d["pecas"]) == 100 and d["nao_listadas"] == {"tipos": 30, "pecas": 60}, d.get("nao_listadas")
    assert "(e mais 60 peça(s) em 30 tipo(s) não listados" in ex.to_structured_prompt()


def test_CONTROLE_sem_passar_do_limite_nao_ha_resto(tmp_path):
    d = _arquivo(tmp_path).metadata["pecas_no_vinculo"][BASE]
    assert "nao_listadas" not in d, d


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("nome", ["IMPLANTACAO-EXE-R01.dxf",          # o arquivo não diz a disciplina
                                  "PROJ-HID-EXE-R01.dxf"])             # outra disciplina
def test_CONTROLE_sem_a_mesma_disciplina_nao_ha_conteudo(tmp_path, nome):
    ex = _arquivo(tmp_path, nome)
    pv = ex.metadata.get("pecas_no_vinculo") or {}
    assert BASE not in pv, pv


def test_no_arquivo_hidraulico_o_vinculo_hidraulico_e_o_conteudo(tmp_path):
    pv = _arquivo(tmp_path, "PROJ-HID-EXE-R01.dxf").metadata.get("pecas_no_vinculo") or {}
    assert pv.get("OBRA-HID-AGUA", {}).get("pecas") == {"REGISTRO": 7}, pv


@pytest.mark.parametrize("nome,disc", [
    ("XYZ-ABC-HID-ALOJ-GO", "HID"), ("ABC_ES_EX_HT_000", "EST"), ("VITORIA-ES-ARQ-001", "ARQ"),
    ("PROJ-ARQ-HID", ""), ("SEM CODIGO NENHUM", ""), ("UNIV-PE-ARQ", "ARQ"), ("ESTRELA-01", ""),
])
def test_a_disciplina_pelo_codigo_no_nome(nome, disc):
    assert er.disciplina_do_nome(nome) == disc


# ── o selo ─────────────────────────────────────────────────────────────────────
def test_contagem_do_vinculo_nao_sai_com_selo():
    conf, obs, reb = er.selo_apos_peca_no_vinculo(
        "confirmado", "3 toldos — dentro do vínculo do Revit", 3, "un", {3, 5}, {"toldo - demolir"})
    assert (conf, reb) == ("estimado", True) and obs.startswith(er.MARCA_PECA_NO_VINCULO), obs
    conf, _o, reb = er.selo_apos_peca_no_vinculo(
        "confirmado", "Fonte: TOLDO - DEMOLIR", 3, "un", {3}, {"toldo - demolir"})
    assert reb is True


@pytest.mark.parametrize("conf,obs,q,u", [
    ("confirmado", "3 bacias da CONTAGEM DE BLOCOS 'BACIA'", 3, "un"),    # não cita o vínculo
    ("confirmado", "dentro do vínculo", 4, "un"),                          # número que não é do vínculo
    ("confirmado", "dentro do vínculo", 3, "m"),                           # não é contagem
    ("estimado", "dentro do vínculo", 3, "un"),                            # já laranja
])
def test_CONTROLE_selo_que_nao_e_do_vinculo(conf, obs, q, u):
    assert er.selo_apos_peca_no_vinculo(conf, obs, q, u, {3, 5}, {"toldo - demolir"})[2] is False
