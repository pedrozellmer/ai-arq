# -*- coding: utf-8 -*-
"""O cache do carimbo guarda só leitura COM escala. Negativo é reperguntado.

🩸 05/09/2026, A08 do cliente-39 (135fdfac). A escala do carimbo foi lida como
1:75 em cinco chamadas à Vision ao longo do dia. Na sexta (17:03) o Haiku
respondeu diferente — sem escala — e `read_carimbo_scale` gravou isso no
`carimbo_cache.json` (chave = sha256 do arquivo + página). A tentativa
seguinte (17:10) NEM CHAMOU a Vision: leu o cache e saiu "sem escala"; a
sombra também. Uma leitura ruim virava permanente pro arquivo até o próximo
deploy. Medido no error_log: 17:03 uma linha `llm:cache pdfvec-carimbo`
(out=18, contra 24-28 nas leituras certas); 17:10 nenhuma.

Regra nova: só grava no cache quando `main_scale` foi lido. Negativo custa
uma chamada do Haiku a mais na próxima vez — e dá a ela a chance de acertar.

🧪 Controles: positivo É gravado e reaproveitado (a 2ª chamada não pergunta
ao modelo); o guarda reprova a regra antiga.
"""
import json
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import pdfvec_carimbo as pc  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

_SRC = sem_comentarios(fonte("pdfvec_carimbo.py"))


class _DocFalso:
    def __len__(self):
        return 1

    def __getitem__(self, i):
        return object()

    def close(self):
        pass


def _arma(monkeypatch, tmp_path, respostas):
    """Isola o leitor: sem PDFium, sem rede, cache num arquivo temporário.
    `respostas` é a fila do que o 'modelo' devolve a cada chamada."""
    chamadas = []
    monkeypatch.setattr(pc, "_CACHE_PATH", str(tmp_path / "carimbo_cache.json"))
    monkeypatch.setattr(pc.pdfium, "PdfDocument", lambda *a, **k: _DocFalso())
    monkeypatch.setattr(pc, "_carimbo_crops", lambda page: [b"jpeg-falso"])
    monkeypatch.setattr(pc, "_load_api_key", lambda: "chave-falsa")

    class _Cliente:  # anthropic.Anthropic(api_key=...) sem rede
        def __init__(self, *a, **k):
            pass
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _Cliente)

    def _ask(client, model, jpegs):
        chamadas.append(model)
        return respostas.pop(0) if respostas else None
    monkeypatch.setattr(pc, "_ask_model", _ask)
    pdf = tmp_path / "prancha.pdf"
    pdf.write_bytes(b"%PDF-1.4 conteudo qualquer, so' pra ter hash")
    return str(pdf), chamadas


def _cache(tmp_path) -> dict:
    p = tmp_path / "carimbo_cache.json"
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


# ── o defeito: negativo não pode virar permanente ──────────────────────────
def test_leitura_SEM_escala_nao_e_gravada(monkeypatch, tmp_path):
    # Haiku diz "indicadas" (sem número) → não há fallback; resultado sem escala
    pdf, chamadas = _arma(monkeypatch, tmp_path, [{"scales": [], "indicadas": True}])
    r = pc.read_carimbo_scale(pdf, 0)
    assert r["main_scale"] is None and r["indicadas"] is True
    assert _cache(tmp_path) == {}, "negativo foi gravado — a próxima tentativa nem perguntaria à Vision"


def test_leitura_vazia_com_fallback_TAMBEM_nao_e_gravada(monkeypatch, tmp_path):
    # Haiku vazio → Sonnet vazio → confidence 'baixa' → não grava
    pdf, chamadas = _arma(monkeypatch, tmp_path, [{"scales": []}, {"scales": []}])
    r = pc.read_carimbo_scale(pdf, 0)
    assert r["main_scale"] is None and r["confidence"] == "baixa"
    assert len(chamadas) == 2, "o fallback Sonnet tem que ter rodado"
    assert _cache(tmp_path) == {}


def test_a_proxima_tentativa_PERGUNTA_de_novo_e_pode_acertar(monkeypatch, tmp_path):
    """A sequência real do dia: 1ª leitura ruim, 2ª leitura certa."""
    pdf, chamadas = _arma(monkeypatch, tmp_path,
                          [{"scales": [], "indicadas": True},      # 1ª: ruim
                           {"scales": ["1/75"]}])                  # 2ª: certa
    assert pc.read_carimbo_scale(pdf, 0)["main_scale"] is None
    assert pc.read_carimbo_scale(pdf, 0)["main_scale"] == 75, (
        "a 2ª tentativa tinha que perguntar de novo e ler 1:75 — antes ela lia o cache negativo")
    assert len(chamadas) == 2


# ── controles positivos: o cache continua servindo pro que presta ─────────
def test_CONTROLE_leitura_COM_escala_e_gravada_e_reaproveitada(monkeypatch, tmp_path):
    pdf, chamadas = _arma(monkeypatch, tmp_path, [{"scales": ["1:75", "1:20"]}])
    r1 = pc.read_carimbo_scale(pdf, 0)
    assert r1["main_scale"] == 75 and r1["declared_scales"] == ["1:75", "1:20"]
    assert len(_cache(tmp_path)) == 1, "positivo TEM que ser gravado"
    r2 = pc.read_carimbo_scale(pdf, 0)
    assert r2 == r1 and len(chamadas) == 1, "a 2ª leitura tinha que vir do cache, sem chamar o modelo"


def test_CONTROLE_use_cache_False_continua_sem_gravar_nada(monkeypatch, tmp_path):
    pdf, _ = _arma(monkeypatch, tmp_path, [{"scales": ["1:100"]}])
    pc.read_carimbo_scale(pdf, 0, use_cache=False)
    assert _cache(tmp_path) == {}


# ── fonte: a regra está no lugar certo ─────────────────────────────────────
def test_a_regra_esta_na_gravacao_do_cache():
    assert 'if use_cache and result["main_scale"] is not None:' in _SRC, (
        "a gravação do cache voltou a ser incondicional — negativo vira permanente de novo")
    assert _SRC.count("_cache_save(cache)") == 1


def test_CONTROLE_guarda_reprova_a_regra_antiga():
    antiga = "    if use_cache:\n        cache[key] = result\n        _cache_save(cache)\n"
    assert 'if use_cache and result["main_scale"] is not None:' not in antiga
