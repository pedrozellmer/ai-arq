# -*- coding: utf-8 -*-
"""A chave do selo: respeita a dúvida escrita e roda antes de quem a descreve.

🩸 27/09/2026 — triagem dos 33 projetos de 20–27/09:
  · 11 de 16 e-mails de "planilha pronta" se contradiziam ("✓ 383 medidos" no
    placar, "131 medidos do CAD" no aviso do MESMO e-mail): a chave promovia
    DEPOIS da recontagem do aviso, do retrato do selo e da planilha (.xlsx sem
    as promoções — ela nem pedia pra refazer);
  · das 28 promoções da chave ainda no ar, 20 traziam no próprio texto a dúvida
    da IA ("confirmar escala", "valor muito pequeno — escala incorreta", "pode
    estar multiplicado", "layer MISTO, marcar estimado"), e uma tinha acabado
    de ser rebaixada pela rede de procedência ("LIDO de um texto");
  · prancha com régua "ambigua" (dois fatores batem com as cotas) não era
    ressalva: 17 selos em m/m²/m³ em 3 jobs.
"""
import ast
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
from dwg_extractor import ressalva_da_escala_ambigua  # noqa: E402

_INDICE = {"comprimento": [("ELETRICA", 104.33)], "area": [], "contagem": []}


def _linha(obs, q=104.33, u="ml"):
    return {"description": "Eletroduto", "unit": u, "quantity": q,
            "confidence": "estimado", "origem": "dxf_geom", "observations": obs}


# ══════════════════════════════════════════════════════════════════════════
#  1) A dúvida escrita pela IA sobre o número
# ══════════════════════════════════════════════════════════════════════════
_DUVIDAS = [
    "Unidade do desenho suspeita — confirmar escala com projetista.",
    "Unidade suspeita corrigida por plausibilidade — confirmar escala.",
    "Valor muito pequeno — provável que seja trecho de detalhe ou escala incorreta.",
    "ATENÇÃO: o valor pode incluir múltiplas plantas sobrepostas.",
    "o arquivo contém múltiplas plantas sobrepostas; este valor pode estar multiplicado.",
    "3 hachuras em 2 padrões distintos — layer MISTO, marcar estimado.",
    "⚠ CONFERIR A GRANDEZA: esta linha saiu em ml e o serviço é medido em M3.",
    "Marcado como ESTIMADO — a soma do layer pode incluir traço que não é deste item.",
    "Atenção: área maior que a cozinha identificada (7,1 m²).",
    "Confirmar se o valor inclui múltiplas plantas.",
    "Valor baixo — pode ser trecho específico ou elemento de legenda.",
    "Confirmar se o comprimento representa leito de cabos ou eletroduto.",
    "O layer contém ambas as faces da parede; eixo ≈ metade.",
    "Provavelmente símbolo de layout.",
    # uma frase que só casa UM padrão, pra cada padrão que outra frase cobria
    # junto (a sabotagem mostrou: tirar o padrão não reprovava nada)
    "Valor muito pequeno para o ambiente.",
    "Confirmar a escala do arquivo.",
    "Possível escala incorreta no arquivo.",
]
_SEM_DUVIDA = [
    "Fonte: comprimento do layer ELETRICA = 104,33 m (COMPRIMENTOS POR LAYER).",
    "A associação deste layer à largura específica do leito deve ser confirmada.",
    "Fonte: área hachurada do layer PISO = 42,10 m². Sem sobreposição com o item 3.",
    "Não há duplicação entre pranchas.",
    "Pintura das duas faces da parede.",
]


def test_as_duvidas_da_ia_sobre_o_numero_sao_reconhecidas():
    for t in _DUVIDAS:
        assert er.ressalva_do_numero(t), t


def test_CONTROLE_fonte_limpa_duvida_de_especificacao_e_negacao_nao_sao_duvida():
    for t in _SEM_DUVIDA:
        assert er.ressalva_do_numero(t) == "", (t, er.ressalva_do_numero(t))


def test_a_chave_nao_promove_linha_com_duvida_escrita():
    for t in _DUVIDAS:
        obs = "Fonte: comprimento do layer 'ELETRICA' = 104,33 m. " + t
        assert er.selo_com_prova_da_geometria([_linha(obs)], _INDICE) == [], t


def test_a_chave_nao_desfaz_a_rede_de_procedencia():
    obs = (er.MARCA_LIDO_DE_TEXTO + ", não medido da geometria. "
           "Fonte: comprimento do layer 'ELETRICA' = 104,33 m.")
    assert er.selo_com_prova_da_geometria([_linha(obs)], _INDICE) == []


def test_CONTROLE_sem_duvida_a_chave_promove():
    for t in _SEM_DUVIDA[:3]:
        obs = "Fonte: comprimento do layer 'ELETRICA' = 104,33 m. " + t
        prom = er.selo_com_prova_da_geometria([_linha(obs)], _INDICE)
        assert [p["indice"] for p in prom] == [0], t


# ══════════════════════════════════════════════════════════════════════════
#  2) Régua "ambigua" é ressalva de escala
# ══════════════════════════════════════════════════════════════════════════
def test_regua_ambigua_vira_ressalva():
    assert ressalva_da_escala_ambigua({"status": "ambigua", "motivo": "0,01 e 0,001 batem"}) \
        == "0,01 e 0,001 batem"
    assert ressalva_da_escala_ambigua({"status": "ambigua"})
    md = {"escala_ambigua": "0,01 e 0,001 batem"}
    assert er.extraction_has_quality_caveat(md)
    for u in ("m", "m²", "m³"):
        assert er.caveat_atinge_unidade(md, u), u
    for u in ("un", "kg"):
        assert not er.caveat_atinge_unidade(md, u), u


def test_CONTROLE_outras_reguas_nao_sao_ressalva():
    for st in ("validada", "corrigida", "corrigida_lfac", None, "nao-decidiu"):
        assert ressalva_da_escala_ambigua({"status": st}) == "", st
    assert ressalva_da_escala_ambigua(None) == ""
    assert not er.extraction_has_quality_caveat({"regua_cotas_status": "nao-decidiu"})


def test_o_extrator_grava_a_ressalva_da_regua_ambigua():
    """A função só vale se o extract_dxf a chama e grava a chave que a
    trava lê — o nome da chave é o da lista de ressalvas de escala."""
    src = open(os.path.join(os.path.dirname(_AQUI), "dwg_extractor.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "extract_dxf")
    chamadas = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "ressalva_da_escala_ambigua"]
    assert chamadas, "extract_dxf não chama ressalva_da_escala_ambigua"
    grava = [n for n in ast.walk(fn) if isinstance(n, ast.Subscript)
             and isinstance(n.ctx, ast.Store)
             and getattr(n.slice, "value", None) == "escala_ambigua"]
    assert grava, "extract_dxf não grava metadata['escala_ambigua']"
    assert "escala_ambigua" in er._RESSALVAS_SO_DE_ESCALA


# ══════════════════════════════════════════════════════════════════════════
#  3) A ordem: a chave antes de quem descreve o selo
# ══════════════════════════════════════════════════════════════════════════
def _process_job():
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    return next(n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.FunctionDef) and n.name == "process_job")


def _chamadas(fn, nome):
    return [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == nome]


def test_a_chave_e_a_tabela_rodam_antes_de_tudo_que_descreve_o_selo():
    fn = _process_job()
    chave = _chamadas(fn, "_chave_selo")
    tabela = _chamadas(fn, "_chave_tabela")
    assert len(chave) == 1 and len(tabela) == 1, (chave, tabela)
    ultima_promocao = max(chave[0], tabela[0])
    # a ÚLTIMA recontagem do aviso do plano B é a que o cliente lê
    recontagem = _chamadas(fn, "_recontar_aviso_planob")
    assert recontagem and ultima_promocao < max(recontagem), (ultima_promocao, recontagem)
    for nome in ("_retrato", "generate_spreadsheet", "_tirar_rejeitadas_pelo_cliente",
                 "_persist_items_to_supabase"):
        linhas = _chamadas(fn, nome)
        assert linhas, "sumiu %s do process_job" % nome
        assert ultima_promocao < min(linhas), (
            "a promoção (linha %d) roda DEPOIS de %s (linha %d): o que ela promove "
            "não chega a quem descreve o selo" % (ultima_promocao, nome, min(linhas)))


def test_a_rede_de_procedencia_escreve_a_marca_que_a_chave_respeita():
    fn = _process_job()
    usos = [n for n in ast.walk(fn) if isinstance(n, ast.alias)
            and n.name == "MARCA_LIDO_DE_TEXTO"]
    assert usos, "a rede de procedência não usa MARCA_LIDO_DE_TEXTO"
    rede = _chamadas(fn, "_ssg")
    assert rede and min(rede) < _chamadas(fn, "_chave_selo")[0], "a rede roda depois da chave"
    # 🪤 A marca escrita À MÃO no main (mesmo texto de hoje) funciona até alguém
    # editar a frase — e aí a chave para de reconhecê-la calada. A marca vem da
    # constante; o texto literal não pode existir no main.
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    assert er.MARCA_LIDO_DE_TEXTO not in src, (
        "o main escreve a marca da rede à mão — use MARCA_LIDO_DE_TEXTO")
