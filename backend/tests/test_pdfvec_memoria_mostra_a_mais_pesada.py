# -*- coding: utf-8 -*-
"""A linha `pdfvec:memoria` mostra a prancha mais PESADA e a memória POR ETAPA.

🩸 10/09/2026 — revisão de 10 agentes sobre as pranchas de PDF que o filho da
promoção perde. O instrumento que decide o teto de memória tinha dois furos:

1. escolhia as 6 pranchas por ÁREA — no job aec7cac2 a única prancha com
   MemoryError ficou FORA da linha;
2. a memória por etapa era medida pelo filho e jogada fora pelo pai.

Estes guardas CHAMAM `main._linha_pdfvec_memoria` e `pdf_vector._measure_page`.
"""
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

#: A consulta que deu o p95 do teto em 05/09 casa ESTE texto. Mudar a ordem ou
#: o formato cega a série histórica sem erro nenhum.
_RX_P95 = re.compile(r"VmPeak=([0-9]+)MB VmHWM=([0-9]+)MB ini_VmSize=[0-9]+MB secs=([0-9]+)")


def _prancha(nome, m2, pico_mb, etapas=None, mem_etapas=None, secs=10.0):
    return {"arquivo": nome, "pagina": 0, "rooms_m2": m2, "secs": secs,
            "mem_kb": {"VmPeak": pico_mb * 1024, "VmHWM": (pico_mb // 2) * 1024},
            "mem_kb_inicio": {"VmSize": 14 * 1024},
            "etapas": etapas if etapas is not None else {"rooms": 5.0, "walls": 2.0},
            "mem_etapas": mem_etapas if mem_etapas is not None else {}}


def _linha(pranchas, **kw):
    import main
    return main._linha_pdfvec_memoria(pranchas, **kw)


def test_a_prancha_mais_PESADA_entra_mesmo_sendo_a_de_menor_area():
    """O caso aec7cac2: 8 pranchas, e a que estourou a memória é a de menor área."""
    pranchas = [_prancha("area%d.pdf" % i, 500.0 - i * 10, 300 + i) for i in range(7)]
    pranchas.append(_prancha("pesada.pdf", 12.0, 1800))
    # a ordem em que o pai passa: por área, decrescente
    linha = _linha(sorted(pranchas, key=lambda r: -r["rooms_m2"]))
    assert "pesada.pdf" in linha, (
        "a prancha mais pesada ficou fora da linha de memória: %r" % linha)
    assert linha.index("pesada.pdf") < linha.index("area6.pdf"), (
        "a mais pesada tem que vir primeiro: %r" % linha)


def test_o_prefixo_que_deu_o_p95_continua_casando():
    linha = _linha([_prancha("a.pdf", 10.0, 1500, secs=37.6),
                    _prancha("b.pdf", 20.0, 400, secs=8.0)])
    achados = _RX_P95.findall(linha)
    assert achados == [("1500", "750", "38"), ("400", "200", "8")], (linha, achados)


def test_a_memoria_POR_ETAPA_chega_no_log():
    me = {"parse": [800_000, 900_000, 1_500_000, 1_600_000],
          "rooms": [850_000, 950_000, 1_700_000, 1_750_000]}
    linha = _linha([_prancha("a.pdf", 10.0, 1750, mem_etapas=me)])
    # etapa:VmPeak/VmSize, em MiB
    assert "pico={parse:1562/1464,rooms:1708/1660}" in linha, linha


def test_checkpoint_ANTIGO_de_2_numeros_nao_quebra_a_linha():
    """Checkpoint salvo antes do deploy traz só [VmRSS, VmHWM]. Essa prancha sai
    sem `pico=` — e as outras continuam com o delas."""
    velho = _prancha("velho.pdf", 10.0, 900, mem_etapas={"rooms": [800_000, 900_000]})
    novo = _prancha("novo.pdf", 10.0, 1000,
                    mem_etapas={"rooms": [1, 2, 1_000_000, 1_024_000]})
    linha = _linha([velho, novo])
    assert "velho.pdf" in linha and "novo.pdf" in linha, linha
    assert "pico=" not in linha[linha.index("velho.pdf"):], linha
    assert "pico={rooms:1000/976}" in linha, linha


def test_o_pico_que_sai_primeiro_e_o_das_mais_LEVES():
    etapas = {("et%02d" % k): 1.0 for k in range(14)}
    me = {("et%02d" % k): [1, 2, 1_500_000, 1_600_000] for k in range(14)}
    pranchas = [_prancha("p%02d.pdf" % i, 10.0, 1900 - i, etapas=etapas, mem_etapas=me)
                for i in range(6)]
    linha = _linha(pranchas)
    assert len(linha) <= 1900, len(linha)
    assert "fora" not in linha, "cortou prancha antes de tirar o pico das leves: %r" % linha
    partes = linha.split(" | ")
    assert partes[0].startswith("p00.pdf") and "pico={" in partes[0], partes[0]
    assert partes[-1].startswith("p05.pdf") and "pico={" not in partes[-1], partes[-1]


def test_cabe_no_corte_do_log_e_DECLARA_as_pranchas_que_ficaram_fora():
    etapas = {("et%02d" % k): 1.0 for k in range(40)}
    pranchas = [_prancha("p%02d.pdf" % i, 10.0, 1900 - i, etapas=etapas) for i in range(9)]
    linha = _linha(pranchas)
    assert len(linha) <= 1900, len(linha)
    m = re.search(r"\(\+(\d+) fora\)", linha)
    assert m, "prancha ficou fora da linha sem aviso: %r" % linha[-200:]
    assert len(_RX_P95.findall(linha)) + int(m.group(1)) == 9, linha
    assert "p00.pdf" in linha, "a mais pesada nunca pode ser a que sai"
    assert "p08.pdf" not in linha


def test_CONTROLE_prancha_sem_memoria_nao_entra_e_job_sem_nada_nao_grava():
    assert _linha([]) == ""
    assert _linha([{"arquivo": "a.pdf", "pagina": 0, "mem_kb": {}}]) == ""
    linha = _linha([_prancha("com.pdf", 1.0, 500),
                    {"arquivo": "sem.pdf", "pagina": 1, "mem_kb": {}}])
    assert "com.pdf" in linha and "sem.pdf" not in linha, linha


def test_CONTROLE_job_normal_sai_inteiro_sem_corte_nem_fora():
    me = {"rooms": [1, 2, 300_000, 310_000]}
    linha = _linha([_prancha("a%d.pdf" % i, 10.0, 300 + i, mem_etapas=me) for i in range(3)])
    assert "fora" not in linha, linha
    assert linha.count("pico={") == 3, linha
    assert len(_RX_P95.findall(linha)) == 3, linha


def test_o_filho_grava_VmSize_e_VmPeak_POR_ETAPA(tmp_path, monkeypatch):
    """O outro lado do instrumento: se o filho não grava os 4 números, o pai não
    tem o que mostrar. Chama `_measure_page` de verdade, com `_mem_kb` dublado
    (no Windows não existe /proc)."""
    import pdf_vector
    from test_o_filho_devolve_o_proprio_pico import _pdf_em_branco, _sem_vision
    _sem_vision(monkeypatch)
    monkeypatch.setattr(pdf_vector, "_mem_kb", lambda: {
        "VmRSS": 100, "VmHWM": 200, "VmSize": 300, "VmPeak": 400})
    out = pdf_vector._measure_page(_pdf_em_branco(tmp_path), 0, "")
    assert out["mem_etapas"], out
    for etapa, v in out["mem_etapas"].items():
        assert list(v) == [100, 200, 300, 400], (etapa, v)
