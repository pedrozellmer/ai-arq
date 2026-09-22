# -*- coding: utf-8 -*-
"""Linha que GANHOU número medido para de mandar o cliente informar a área.

🩸 14/09/2026 — a linha sai zerada e ganha "Área NÃO medida (lida de PDF por IA,
não da geometria) — informe a área no upload". Depois o passo do comprimento
RECUPERA a medição do layer e preenche o número — e o texto antigo fica. O
cliente lê, na mesma linha: "⚠ QUANTIDADE RECUPERADA: o motor mediu 16,98 m
neste layer" e "Área NÃO medida — informe a área no upload".

🚨 E o conselho não é só contraditório: se obedecido, ELE ZERA O NÚMERO de
volta (o campo do upload cai no caminho que zera). É o achado 7 de 05/08, que
criou `_limpa_aviso_nao_medida` — a função existia e faltava chamá-la no único
ponto onde uma linha zerada volta a ter número.

📏 Medido na base (30 dias): 57 linhas em ~10 jobs diziam as duas coisas.

🪤 O teste EXECUTA o laço do `process_job`, recortado do fonte — não lê texto.
Era o único jeito de provar o ponto de chamada: o laço mora dentro da função de
5 mil linhas que sobe o motor inteiro.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_AVISO_ZERA = ("Área NÃO medida (lida de PDF por IA, não da geometria) — "
               "preencha a metragem, informe a área no upload ou envie o DXF pra medir.")


class _It:
    def __init__(self, desc, unit, qty, obs):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations = obs
        self.confidence = "estimado"


def _roda_o_laco_do_comprimento(itens):
    """Recorta e EXECUTA o laço que recupera comprimento, como no motor."""
    import textwrap
    from _corpo import fonte
    src = fonte("main.py")
    i = src.index("_fix = _corrigir_comprimento_medido(")
    # 🪤 Começa no `_cita = {}`, não no laço que recupera: quem conta as
    # citações do MESMO total é o laço de cima, e reimplementar essa contagem
    # aqui seria reescrever a régua dentro do teste — erro já registrado.
    # 🪤 `bloco_desde` não serve: ele recorta o bloco de uma linha que ABRE
    # escopo, e `_cita = {}` não abre. Aqui o recorte vai do início daquela
    # linha até o relatório, que é onde os dois laços acabam.
    ini = src.rindex(chr(10), 0, src.rindex("_cita = {}", 0, i)) + 1
    fim = src.index('print(f"[comprimento]', i)
    codigo = textwrap.dedent(src[ini:src.rindex(chr(10), 0, fim) + 1])
    ns = {
        "all_items": itens,
        "_corrigir_comprimento_medido": main._corrigir_comprimento_medido,
        "_limpa_aviso_nao_medida": main._limpa_aviso_nao_medida,
        "_medida_comprimento_obs": main._medida_comprimento_obs,
        "_medida_e_base_de_calculo": main._medida_e_base_de_calculo,
        "_Conf2": type("C", (), {"ESTIMADO": "estimado"}),
        "_n_uni": 0, "_n_rec": 0, "_n_ambiguo": 0,
        # 22/09: os cenários daqui são de CAD ("layer A-WALL") — o job tem DXF.
        "_tem_cad_compr": True,
        "_texto_veio_da_leitura_de_pdf": main._texto_veio_da_leitura_de_pdf,
    }
    exec(compile(codigo, "laco-do-comprimento", "exec"), ns)
    return ns


def test_a_linha_RECUPERADA_para_de_mandar_informar_a_area():
    it = _It("Alvenaria de vedação — bloco cerâmico", "m²", 0,
             "Comprimento total do layer A-WALL = 16,98 m. | " + _AVISO_ZERA)
    ns = _roda_o_laco_do_comprimento([it])
    assert ns["_n_rec"] == 1, "o cenário não recuperou nada — o guarda não prova nada"
    assert float(it.quantity or 0) > 0, it.quantity
    obs = it.observations or ""
    assert "QUANTIDADE RECUPERADA" in obs, obs
    assert "informe a área no upload" not in obs, (
        "a linha ganhou número medido e o texto ainda manda informar a área — "
        "conselho que ZERA o número de volta: %s" % obs)
    assert "NÃO medida" not in obs, obs
    assert "Comprimento total do layer" in obs, (
        "a limpeza levou junto a medição que a IA escreveu: %s" % obs)


def test_CONTROLE_linha_que_so_teve_a_UNIDADE_corrigida_mantem_o_aviso():
    """Prova que o guarda sabe distinguir: sem recuperar quantidade, a linha
    continua sem medição nossa e o aviso segue verdadeiro."""
    it = _It("Rodapé em porcelanato", "un", 16.98,
             "Comprimento total do layer A-RODA = 16,98 m. | " + _AVISO_ZERA)
    ns = _roda_o_laco_do_comprimento([it])
    assert ns["_n_rec"] == 0 and ns["_n_uni"] == 1, (ns["_n_rec"], ns["_n_uni"])
    assert "UNIDADE CORRIGIDA" in (it.observations or "")
    assert "informe a área no upload" in (it.observations or ""), (
        "o aviso sumiu de uma linha que NÃO ganhou medição nossa")


def test_CONTROLE_medicao_compartilhada_nao_preenche_nem_limpa():
    """Duas linhas citando o MESMO total: nenhuma recebe o número (rateio), e
    o aviso não pode sumir — elas continuam sem medição própria."""
    obs = "Comprimento total do layer A-WALL = 965,77 m. | " + _AVISO_ZERA
    a = _It("Parede drywall", "m²", 0, obs)
    b = _It("Fita de junta", "m²", 0, obs)
    ns = _roda_o_laco_do_comprimento([a, b])
    assert ns["_n_ambiguo"] == 2 and ns["_n_rec"] == 0
    for it in (a, b):
        assert float(it.quantity or 0) == 0
        assert "MEDIÇÃO COMPARTILHADA" in (it.observations or "")
        assert "informe a área no upload" in (it.observations or "")
