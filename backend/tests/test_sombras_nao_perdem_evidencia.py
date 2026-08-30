# -*- coding: utf-8 -*-
"""Os 3 consertos de 15/08 (feitos em 30/08) — e os guardas pra não regredirem.

🩸 Contexto: o radar de acurácia fez DUAS leituras (15/08 e 29/08) e as duas
saíram vazias pelos MESMOS motivos: a régua da sombra era a leitura da própria
IA (motor conferindo motor), `cotas_derivacao` era calculado e descartado pela
keep-list, e MAX_PAGES=3 cortava 43 páginas em 3 sem avisar. Estes testes
CHAMAM o código (lição do apagão de 29h: guarda que lê fonte não pega nada).
"""
import importlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── conserto 1: a régua diz de onde veio ────────────────────────────────────

def test_regua_prefere_o_cliente():
    import main
    assert main._regua_da_sombra(85.5, 9205.0) == (85.5, "cliente")


def test_regua_cai_pra_ia_quando_cliente_nao_informou():
    import main
    assert main._regua_da_sombra(0, 9205.0) == (9205.0, "ia_quadro")
    assert main._regua_da_sombra(None, 9205.0) == (9205.0, "ia_quadro")


def test_regua_sem_fonte_nenhuma_diz_que_nao_tem():
    import main
    assert main._regua_da_sombra(0, None) == (None, None)
    assert main._regua_da_sombra("lixo", "lixo") == (None, None)


def test_a_sombra_aceita_e_propaga_a_fonte():
    """A assinatura nova existe de ponta a ponta (async → _run)."""
    import inspect

    import dxf_rooms_shadow as drs
    assert "regua_fonte" in inspect.signature(drs.shadow_rooms_async).parameters
    assert "regua_fonte" in inspect.signature(drs._run).parameters
    # e o gravador usa: a string aparece no fonte da _run (fraco sozinho,
    # mas junto com a assinatura fecha o caminho)
    assert "regua_fonte" in inspect.getsource(drs._run)


# ── consertos 2 e 3: evidência sobrevive e o corte fala ─────────────────────

def _roda_shadow_pdf(monkeypatch, paginas, medida_fake):
    """Chama pdf_vector._run DE VERDADE, com sleep anulado, _measure_page
    dublado e log capturado."""
    import pdf_vector as pv
    monkeypatch.setattr(pv.time, "sleep", lambda *_: None)
    monkeypatch.setattr(pv, "_measure_page", lambda *a, **k: dict(medida_fake))
    capturado = {}

    def log_fn(stage, payload, job_id, severity="error"):
        capturado["stage"] = stage
        capturado["payload"] = json.loads(payload)

    pv._run(paginas, "job-teste", "api-key-fake", log_fn)
    return capturado["payload"]


def test_cotas_derivacao_SOBREVIVE_no_resumo(monkeypatch, tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-fake")
    pg = [(str(f), "a.pdf", "arquitetura", 0)]
    payload = _roda_shadow_pdf(monkeypatch, pg, {
        "file": "a.pdf", "page": 0, "scale": 50, "scale_src": "cotas",
        "scale_derivada_por_cota": True,
        "cotas_derivacao": {"votos": 3, "n_cotas": 12, "confianca": 0.8},
        "err_cotas_derive": None, "rooms_m2": 10.0,
        "campo_desconhecido": "NAO pode passar",
    })
    pagina = payload["pages"][0]
    assert pagina["cotas_derivacao"]["votos"] == 3, pagina
    assert pagina["scale_derivada_por_cota"] is True
    # 🧪 controle positivo: a keep-list continua FILTRANDO o que não conhece
    assert "campo_desconhecido" not in pagina


def test_erro_da_terceira_fonte_deixa_rastro(monkeypatch, tmp_path):
    """A pergunta de 40 falhas sem resposta: agora o PORQUÊ chega ao banco."""
    f = tmp_path / "b.pdf"
    f.write_bytes(b"%PDF-fake")
    payload = _roda_shadow_pdf(monkeypatch, [(str(f), "b.pdf", "x", 0)], {
        "file": "b.pdf", "page": 0, "skip": "sem escala",
        "err_cotas_derive": "ValueError: sem par de cota",
    })
    assert payload["pages"][0]["err_cotas_derive"].startswith("ValueError")


def test_o_corte_do_teto_diz_N_de_M(monkeypatch, tmp_path):
    """Dois jobs de 43 páginas viravam 3 e o log dizia 'medi 3'. Agora diz
    de quantas."""
    import pdf_vector as pv
    monkeypatch.setattr(pv, "MAX_PAGES", 3)
    f = tmp_path / "c.pdf"
    f.write_bytes(b"%PDF-fake")
    pgs = [(str(f), "c.pdf", "x", i) for i in range(11)]
    payload = _roda_shadow_pdf(monkeypatch, pgs, {"file": "c.pdf", "page": 0})
    assert payload["n"] == 3
    assert payload["de"] == 11, payload


def test_teto_agora_e_env():
    import pdf_vector as pv
    os.environ["PDFVEC_MAX_PAGES"] = "5"
    try:
        importlib.reload(pv)
        assert pv.MAX_PAGES == 5
    finally:
        del os.environ["PDFVEC_MAX_PAGES"]
        importlib.reload(pv)
        assert pv.MAX_PAGES == 8  # default novo (era 3 fixo)
