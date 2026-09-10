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

import pytest

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
    """Chama pdf_vector._run DE VERDADE, com sleep anulado, o filho da sombra
    dublado e log capturado.

    🪤 09/09/2026: dublava `_measure_page`, que a `_run` chamava direto. A
    sombra passou a medir num FILHO protegido (RLIMIT_AS de 2 GB, o mesmo da
    promoção) e a dublagem virou espionagem de telefone desligado — dois
    testes daqui ficaram vermelhos. O que eles provam não mudou: é a `_run`
    que tem que preservar a evidência da medição no resumo."""
    import pdf_vector as pv
    monkeypatch.setattr(pv.time, "sleep", lambda *_: None)
    monkeypatch.setattr(pv, "medir_pagina_em_filho",
                        lambda *a, **k: dict(medida_fake))
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


# ══════════════════════════════════════════════════════════════════════════
#  🩸 A PAREDE MEDIDA NÃO PODE MORRER NA KEEP-LIST
# ══════════════════════════════════════════════════════════════════════════
def test_a_PAREDE_medida_sobrevive_no_resumo(monkeypatch, tmp_path):
    """🩸 09/09/2026. `_measure_page` roda `detect_walls` e devolve `walls_m`,
    `n_walls` e `err_walls`. Nenhum dos três estava na keep-list — resultado:
    **ZERO página com `walls_m` no banco**, em todos os dias medidos.

    🪤 E o custo não foi só perder o número. Eu li a AUSÊNCIA DE REGISTRO como
    ausência de MEDIÇÃO e quase afirmei ao Pedro que "o motor acha ambiente e
    não acha parede em 78% das páginas" — conclusão que o dado não sustenta. É
    o mesmo erro do `poligonos=0`, que eu tinha apontado poucas horas antes no
    mesmo dia.

    🔑 Por que a parede é o campo que mais importa no PDF, medido em 09/09:
      • linhas em `ml` saem **83,3% zeradas**;
      • dos 909 m² zerados do PDF, **789 (86,8%) são parede/pintura**, e o
        m² de parede sai de comprimento × pé-direito;
      • sem `walls_m` no log não dá pra saber se falta MEDIR ou falta
        ENTREGAR — e são consertos completamente diferentes.
    """
    f = tmp_path / "p.pdf"
    f.write_bytes(b"%PDF-fake")
    payload = _roda_shadow_pdf(monkeypatch, [(str(f), "p.pdf", "arq", 0)], {
        "file": "p.pdf", "page": 0, "scale": 50, "scale_src": "carimbo",
        "n_rooms": 12, "rooms_m2": 140.0,
        "walls_m": 276.3, "n_walls": 41,
    })
    pagina = payload["pages"][0]
    assert pagina.get("walls_m") == 276.3, pagina
    assert pagina.get("n_walls") == 41, pagina


def test_o_ERRO_do_passo_de_parede_tambem_sobrevive(monkeypatch, tmp_path):
    """🔑 Se `detect_walls` estourar, o motivo tem que chegar. Sem isto,
    "não mediu" e "estourou" viram a mesma ausência — foi essa confusão que
    custou 40 falhas sem resposta na 3ª fonte de escala (conserto de 15/08)."""
    f = tmp_path / "q.pdf"
    f.write_bytes(b"%PDF-fake")
    payload = _roda_shadow_pdf(monkeypatch, [(str(f), "q.pdf", "arq", 0)], {
        "file": "q.pdf", "page": 0, "scale": 50, "n_rooms": 3,
        "err_walls": "ValueError: sem pares de paralelas",
    })
    assert payload["pages"][0]["err_walls"].startswith("ValueError")


def test_o_stderr_do_passo_de_parede_e_CORTADO(monkeypatch, tmp_path):
    """🪤 `err_walls` entrou na keep-list junto com `walls_m`. Se ele entrar
    INTEIRO, repete o estouro dos 2.000 caracteres da coluna que hoje já parte
    o JSON — o mesmo defeito, por um campo novo."""
    import json as _j
    f = tmp_path / "r.pdf"
    f.write_bytes(b"%PDF-fake")
    payload = _roda_shadow_pdf(monkeypatch, [(str(f), "r.pdf", "arq", 0)], {
        "file": "r.pdf", "page": 0, "scale": 50,
        "err_walls": "Traceback " + "x" * 600,
    })
    assert len(payload["pages"][0]["err_walls"]) <= 120, (
        "err_walls foi inteiro pro log e vai estourar a coluna")
    _j.dumps(payload)


def test_CONTROLE_pagina_SEM_parede_nao_inventa_campo(monkeypatch, tmp_path):
    """🧪 O outro lado: a keep-list só copia o que EXISTE. Página que não mediu
    parede não pode ganhar `walls_m: 0` — zero medido e nada medido são coisas
    diferentes, e é justamente a confusão que este arquivo combate."""
    f = tmp_path / "s.pdf"
    f.write_bytes(b"%PDF-fake")
    payload = _roda_shadow_pdf(monkeypatch, [(str(f), "s.pdf", "arq", 0)], {
        "file": "s.pdf", "page": 0, "scale": 50, "n_rooms": 5, "rooms_m2": 60.0,
    })
    assert "walls_m" not in payload["pages"][0], payload["pages"][0]


# ══════════════════════════════════════════════════════════════════════════
#  🔑 O RESUMO CABE POR CONSTRUÇÃO — e diz o que ficou de fora
# ══════════════════════════════════════════════════════════════════════════
def test_o_payload_NUNCA_sai_como_JSON_quebrado(monkeypatch, tmp_path):
    """🩸 A coluna do error_log corta em 2.000 caracteres. Cortar no FIM parte
    o JSON no meio e a linha inteira vira ilegível — leva junto as páginas que
    mediram bem. Já aconteceu em 30/07, e voltou a acontecer quando o `err` do
    filho morto entrou com 400 chars.

    🔑 Sem orçamento, cada campo novo na keep-list é uma roleta: o log some em
    silêncio no dia em que o job tiver páginas demais. Aqui: 8 páginas gordas,
    e o resultado tem que continuar sendo JSON válido.
    """
    import json as _j
    gordo = {"file": "prancha-com-nome-bem-comprido.pdf", "scale": 50,
             "scale_src": "carimbo", "n_rooms": 40, "rooms_m2": 812.4,
             "n_grupos": 6, "grupo_maior_m2": 640.2, "grupo_maior_comodos": 31,
             "envelope_m2": 900.0, "envelope_m2_150": 950.0,
             "envelope_top": [1, 2, 3], "walls_m": 1234.5, "n_walls": 210,
             "escala_validada": True, "cotas_batem": 13, "cotas_encontradas": 40,
             "n_viewports": 4, "n_views": 7, "scale_snapped": True,
             "indicadas": False,
             "err_rooms": "X" * 300, "err_walls": "Y" * 300,
             "err_viewport": "Z" * 300, "err_carimbo": "W" * 300}
    bruto, payload = _roda_a_sombra_gorda(monkeypatch, tmp_path, 8, gordo)
    assert len(bruto) <= 2000, "o payload passou do corte da coluna: %d" % len(bruto)
    _j.loads(bruto)          # 🧪 continua sendo JSON válido


def test_o_que_ficou_de_FORA_e_declarado(monkeypatch, tmp_path):
    """🚫 Corte silencioso lê como 'foi tudo'. Se página não coube, o resumo
    diz quantas — é a mesma regra do `n de m` que consertou o corte de 15/08."""
    gordo = {"file": "p.pdf", "scale": 50, "n_rooms": 30, "rooms_m2": 500.0,
             "walls_m": 900.0, "n_walls": 120, "err_rooms": "X" * 300,
             "err_walls": "Y" * 300, "err_viewport": "Z" * 300}
    _b, payload = _roda_a_sombra_gorda(monkeypatch, tmp_path, 12, gordo)
    if len(payload.get("pages", [])) < 12:
        assert payload.get("cortadas", 0) > 0, (
            "páginas ficaram de fora e o resumo não disse: %r" % payload)
        assert (len(payload["pages"]) + payload["cortadas"]) == 12, payload


def test_CONTROLE_job_pequeno_NAO_perde_pagina_nem_declara_corte(monkeypatch, tmp_path):
    """🧪 O outro lado: um orçamento apertado demais cortaria sempre, e o
    guarda acima passaria feliz. Job normal tem que sair inteiro."""
    magro = {"file": "p.pdf", "scale": 50, "n_rooms": 3, "rooms_m2": 40.0}
    _b, payload = _roda_a_sombra_gorda(monkeypatch, tmp_path, 4, magro)
    assert len(payload["pages"]) == 4, payload
    assert "cortadas" not in payload, payload


def test_TODO_campo_de_erro_e_truncado_por_PREFIXO(monkeypatch, tmp_path):
    """🪤 Antes a lista de campos a truncar era escrita à mão: `err_walls`
    entrou num dia e eu tive que lembrar de acrescentá-lo. Lista de exceção
    envelhece — o próximo `err_*` já nasce cortado."""
    gordo = {"file": "p.pdf", "scale": 50,
             "err_rooms": "A" * 400, "err_walls": "B" * 400,
             "err_viewport": "C" * 400, "err_carimbo": "D" * 400,
             "err_cotas": "E" * 400}
    _b, payload = _roda_a_sombra_gorda(monkeypatch, tmp_path, 1, gordo)
    pag = payload["pages"][0]
    for k, v in pag.items():
        if k.startswith("err") and isinstance(v, str):
            assert len(v) <= 120, "%s saiu com %d chars" % (k, len(v))


def _roda_a_sombra_gorda(monkeypatch, tmp_path, n_paginas, resposta):
    """Roda `_run` de verdade com o filho dublado; devolve (bruto, dict)."""
    import json as _j
    import pdf_vector as pv
    monkeypatch.setattr(pv.time, "sleep", lambda *_: None)
    monkeypatch.setattr(pv, "MAX_PAGES", max(n_paginas, 8))
    monkeypatch.setattr(pv, "medir_pagina_em_filho",
                        lambda pdf, pag, **_k: dict(resposta))
    unidades = []
    for i in range(n_paginas):
        f = tmp_path / ("g%d.pdf" % i)
        f.write_bytes(b"%PDF-1.4 x")
        unidades.append((str(f), "g%d.pdf" % i, "arq", i))
    gravados = []
    pv._run(unidades, "job-teste", "chave", lambda *a, **k: gravados.append(a))
    bruto = next((a[1] for a in gravados if a[0] == "pdfvec:shadow"), None)
    assert bruto is not None, "a sombra não gravou nada"
    return bruto, _j.loads(bruto)


@pytest.mark.parametrize("campo,valor", [
    ("escala_validada", True),      # a escala foi PROVADA por cota, ou é declaração?
    ("cotas_batem", 13),            # quantas cotas bateram
    ("cotas_encontradas", 40),      # quantas existiam
    ("n_viewports", 4),             # havia alternativa ao viewport de detalhe?
    ("n_views", 7),                 # quantas vistas a página tinha
    ("scale_snapped", True),        # escala exata ou aproximada pro padrão?
    ("indicadas", False),           # o carimbo disse "indicadas"?
    ("walls_m", 276.3),             # o comprimento de parede — o gargalo do PDF
    ("n_walls", 41),
])
def test_o_campo_que_RESPONDE_pergunta_chega_no_log(monkeypatch, tmp_path, campo, valor):
    """🩸 10/09/2026 — `_measure_page` produz 44 campos e a keep-list gravava
    21. TRÊS vezes num só dia eu quis decidir alguma coisa e o campo não estava
    lá: a parede, o polígono recusado, e o viewport alternativo. Nas três eu
    comecei a ler AUSÊNCIA DE REGISTRO como ausência de MEDIÇÃO.

    🔑 Cada campo desta lista responde uma pergunta que eu JÁ TIVE na mão e não
    consegui responder. Guarda por campo, não por contagem: tirar um de dentro
    da lista tem que reprovar aqui — a mutação mostrou que sem isto dava pra
    remover `escala_validada` e `n_viewports` sem nada acusar.
    """
    _b, payload = _roda_a_sombra_gorda(
        monkeypatch, tmp_path, 1,
        {"file": "p.pdf", "scale": 50, "n_rooms": 3, campo: valor})
    assert payload["pages"][0].get(campo) == valor, (
        "o campo %r não chegou no log — a decisão que ele responde volta a ser "
        "chute" % campo)


def test_CONTROLE_a_keep_list_continua_FILTRANDO_o_que_nao_conhece(monkeypatch, tmp_path):
    """🧪 O outro lado. Uma keep-list que aceitasse TUDO passaria em cada um dos
    testes acima e voltaria a estourar a coluna no 1º job grande — o defeito de
    09/09. O filtro tem que continuar existindo: campo que ninguém pediu não
    entra no resumo.

    🪤 Guarda por comportamento, não por leitura do fonte: um `assert "for k in
    keep" in fonte` passaria com a linha comentada logo abaixo.
    """
    _b, payload = _roda_a_sombra_gorda(
        monkeypatch, tmp_path, 1,
        {"file": "p.pdf", "scale": 50, "n_rooms": 3,
         "debug_interno_gigante": "Z" * 5000,
         "objeto_que_nao_vira_json": object()})
    pag = payload["pages"][0]
    assert "debug_interno_gigante" not in pag, (
        "a keep-list virou passa-tudo: campo interno vazou pro log")
    assert "objeto_que_nao_vira_json" not in pag, pag
