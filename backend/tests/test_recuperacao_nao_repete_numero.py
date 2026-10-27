# -*- coding: utf-8 -*-
"""A recuperação de comprimento não repete o número que outra linha já tem.

🩸 26/10/2026 — job de cliente (DWG elétrico): o layer de eletroduto somava
364,01 m com DOIS diâmetros. A IA deu o total ao Ø50 e deixou o Ø25 zerado de
propósito; o passo que "recupera" comprimento preencheu o Ø25 com o mesmo
total — 728 m na planilha, e o cliente aprovou as duas linhas.

A trava de rateio só contava linhas ZERADAS citando o mesmo total; a gêmea que
já tem o número ficava de fora. 📏 120 d, clientes: 2 de 25 recuperações
repetiam o número de outra linha — as 2 erradas.

🔑 RECUPERACAO_NAO_REPETE_NUMERO=1 não preenche; com 0 só conta (`repetiria=`).
🪤 Executa o laço do `process_job` recortado do fonte, como o vizinho
`test_a_linha_recuperada_nao_manda_zerar` (não reimplementa a régua).
"""
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_CHAVE = "RECUPERACAO_NAO_REPETE_NUMERO"
_OBS_TOTAL = ("Fonte: layer 'E-POWR-CNDT' = 364.01 m (comprimento total de eletrodutos). "
              "Este item recebe o total provisório.")
_OBS_ZERADA = ("Comprimento total do layer E-POWR-CNDT = 364,01 m, alocado ao item do Ø50. "
               "Preencher quantidade após separação por diâmetro.")


class _It:
    def __init__(self, desc, unit, qty, obs):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations = obs
        self.confidence = "estimado"


def _roda(itens, job_id=None):
    """Recorta e EXECUTA o laço que recupera comprimento, como no motor."""
    from _corpo import fonte
    src = fonte("main.py")
    i = src.index("_fix = _corrigir_comprimento_medido(")
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
        "_tem_cad_compr": True,
        "_texto_veio_da_leitura_de_pdf": main._texto_veio_da_leitura_de_pdf,
    }
    if job_id is not None:          # caminho de produção: a chave POR JOB
        ns["job_id"] = job_id
        ns["_chave_do_job"] = main._chave_do_job
    exec(compile(codigo, "laco-do-comprimento", "exec"), ns)
    return ns


def _par():
    return (_It("Eletroduto de aço galvanizado — Ø 50 mm", "ml", 364.01, _OBS_TOTAL),
            _It("Eletroduto de aço galvanizado — Ø 25 mm", "ml", 0, _OBS_ZERADA))


def test_CONTROLE_desligada_recupera_como_antes_e_so_conta(monkeypatch):
    monkeypatch.delenv(_CHAVE, raising=False)
    a, b = _par()
    ns = _roda([a, b])
    assert ns["_n_rec"] == 1 and float(b.quantity) == 364.01, "o cenário não recuperou — não prova nada"
    assert ns["_n_repetiria"] == 1


def test_ligada_a_gemea_zerada_nao_recebe_o_mesmo_total(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    a, b = _par()
    ns = _roda([a, b])
    assert float(b.quantity or 0) == 0, "repetiu o total que já está na outra linha"
    assert ns["_n_rec"] == 0 and ns["_n_repetiria"] == 1 and ns["_n_ambiguo"] == 1
    assert (b.observations or "").startswith("⚠ MEDIÇÃO COMPARTILHADA"), b.observations
    assert float(a.quantity) == 364.01, "mexeu na linha que já tinha o número"


def test_CONTROLE_ligada_numero_diferente_segue_recuperando(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    a = _It("Eletrocalha perfurada 100×50 mm", "ml", 47.36, "Fonte: layer 'E-CABL-TRAY' = 47.36 m.")
    _, b = _par()
    ns = _roda([a, b])
    assert ns["_n_rec"] == 1 and float(b.quantity) == 364.01
    assert ns["_n_repetiria"] == 0


def test_CONTROLE_ligada_o_mesmo_numero_em_AREA_nao_conta(monkeypatch):
    """Só comprimento ocupa o total de um layer de comprimento."""
    monkeypatch.setenv(_CHAVE, "1")
    a = _It("Piso vinílico", "m²", 364.01, "Área informada.")
    _, b = _par()
    ns = _roda([a, b])
    assert ns["_n_rec"] == 1 and float(b.quantity) == 364.01
    assert ns["_n_repetiria"] == 0


def test_a_avaliacao_liga_so_para_ela(monkeypatch):
    monkeypatch.delenv(_CHAVE, raising=False)
    monkeypatch.setitem(main._CHAVES_DA_AVALIACAO, "evrecu01", {_CHAVE: "1"})
    a, b = _par()
    _roda([a, b], job_id="evrecu01")
    assert float(b.quantity or 0) == 0
    a, b = _par()
    _roda([a, b], job_id="abc12345")
    assert float(b.quantity) == 364.01


def test_a_chave_e_avaliavel_e_o_contador_vai_pro_log():
    from _corpo import fonte
    src = fonte("main.py")
    assert '_chave_do_job(job_id, "%s")' % _CHAVE in src
    assert '"%s"' % _CHAVE in src[src.index("_CHAVES_AVALIAVEIS = frozenset"):][:4000]
    assert 'f"repetiria={_n_repetiria}"' in src
