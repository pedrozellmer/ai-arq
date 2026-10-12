# -*- coding: utf-8 -*-
"""SOMBRA: a escala em uso da página de PDF ao lado do grupo mais forte das
cotas dela. Só registro — não decide nada.

🔬 12/10/2026 — fila de 07/10, item (n). A escala DECLARADA (carimbo, rótulo da
vista, texto) entra sem juiz nenhum, e um PDF escrevia "1:75" com as cotas
dando 1:53. A regra que barraria "a declarada ÷ √2" não subiu: nas 545 páginas
PDF do acervo a assinatura não se separa de um 1:50 de verdade lido alto (dos
113 grupos fortes perto de uma escala conhecida, 6 ficam de 3 a 10 % ACIMA
dela). O que sobe é o registro, pra decidir com número de produção.

Regras que os guardas prendem:
- só registra o grupo FORTE pela régua do juiz (≥ 10 famílias, amplitude ≥ 3),
  com a escala de desenho mais próxima e a razão crua — sem sim/não;
- a busca do grupo é a MESMA do `juiz_desmente` (uma função só);
- custa só casar e buscar: os tokens da folha inteira saem da MESMA passada de
  leitura que a validação já faz, e a validação recebe o que sempre recebeu;
- não decide: com a chave ligada ou desligada, escala, validação e medidas da
  página são as mesmas; erro na sombra não vira falha da prancha;
- a linha vai pro log `pdfvec:cotas-x-escala`, que é de diagnóstico.

🪤 Fixture SINTÉTICA (pikepdf / listas), nunca arquivo de cliente.
"""
import ast
import io
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as M  # noqa: E402
import pdf_vector  # noqa: E402
import pdfvec_carimbo  # noqa: E402
import pdfvec_cotas as C  # noqa: E402

_MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
_PT_M = 0.0254 / 72.0
#: 12 cotas diferentes, de 0,60 a 6,40 m (amplitude 10,7)
_VALORES = (0.60, 0.85, 1.10, 1.45, 1.80, 2.25, 2.70, 3.20, 3.90, 4.60, 5.50, 6.40)
#: 20 cotas diferentes (cada uma 15 % acima da anterior)
_VINTE = tuple(round(0.5 * 1.15 ** i, 3) for i in range(20))


def _pares(esc, valores=_VALORES, ruido=0.0):
    return [(esc * (1 + ruido * ((i % 3) - 1)), v) for i, v in enumerate(valores)]


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede bloqueada no guarda")))
    monkeypatch.setitem(sys.modules, "fitz", None)
    monkeypatch.delenv("PDFVEC_GRUPO_DE_COTAS", raising=False)


# ── o resumo do grupo (puro) ───────────────────────────────────────────────

def test_o_grupo_forte_sai_com_a_escala_de_desenho_mais_proxima_e_a_razao():
    g = C.resumo_do_grupo_forte(_pares(52.6, ruido=0.005))
    assert g and g["familias"] == 12 and g["amplitude"] > 10, g
    assert abs(g["escala"] - 52.6) < 0.5 and g["padrao"] == 50, g
    assert abs(g["razao_padrao"] - g["escala"] / 50) < 0.001, g
    assert set(g) == {"escala", "familias", "amplitude", "padrao", "razao_padrao"}, "sem sim/não: só número"


def test_a_escala_mais_proxima_e_pela_razao_nos_dois_sentidos():
    perto = {110.0: 100, 71.9: 75, 38.0: 40, 88.4: 100, 53.0: 50, 61.5: 75, 60.5: 50, 290.0: 300}
    for esc, padrao in perto.items():
        assert C.resumo_do_grupo_forte(_pares(esc))["padrao"] == padrao, esc
    assert set(C.ESCALAS_PADRAO) <= set(C.ESCALAS_DE_DESENHO) and 40 in C.ESCALAS_DE_DESENHO


def test_grupo_fraco_nao_e_registrado():
    assert C.resumo_do_grupo_forte(_pares(50, _VALORES[:9])) is None            # 9 famílias
    assert C.resumo_do_grupo_forte(_pares(50, _VALORES[:10]))                   # controle: 10 basta
    assert C.resumo_do_grupo_forte(_pares(50, [1.0 + 0.1 * i for i in range(12)])) is None    # amplitude 2,1
    assert C.resumo_do_grupo_forte([]) is None
    assert C.resumo_do_grupo_forte(None) is None


def test_e_o_grupo_MAIS_forte_da_folha():
    g = C.resumo_do_grupo_forte(_pares(53, _VALORES) + _pares(200, _VINTE))
    assert g["familias"] == 20 and g["padrao"] == 200, g


def test_os_pares_podem_vir_fora_de_ordem():
    pares = _pares(200, _VINTE) + _pares(53, _VALORES)
    assert C.resumo_do_grupo_forte(pares) == C.resumo_do_grupo_forte(list(reversed(pares)))


def test_a_busca_do_grupo_e_a_mesma_do_juiz():
    """A busca saiu do `juiz_desmente` pra uma função só; o juiz segue igual."""
    d = C.juiz_desmente(_pares(40, ruido=0.01), 50)
    assert d and d["familias"] == 12 and d["apoio"] == 0 and abs(d["escala"] - 40) < 1.5
    g = C.resumo_do_grupo_forte(_pares(40, ruido=0.01))
    assert (g["escala"], g["familias"], g["amplitude"]) == (d["escala"], d["familias"], d["amplitude"])
    assert C._grupo_mais_forte([]) is None
    fonte = io.open(C.__file__, encoding="utf-8").read()
    corpo = fonte[fonte.index("def juiz_desmente("):fonte.index("def prova_desmentida_pela_linha_de_cota(")]
    assert "_grupo_mais_forte(ps)" in corpo, "o juiz voltou a ter a busca dele"


def test_o_grupo_mais_forte_e_o_de_mais_familias_nao_o_ultimo():
    """Um grupo de 12 cotas diferentes a 1:40 e, DEPOIS dele na ordem, um de 15
    pares que são só 3 cotas repetidas a 1:100: vale o de mais famílias. (A
    janela dos 15 pares não é pulada pelo atalho — tem mais pares do que as 12
    famílias do melhor — e mesmo assim não o troca.)"""
    forte = _pares(40)                                                        # 12 famílias
    repetido = [(100.0, v) for v in (1.0, 2.0, 4.0) for _ in range(5)]       # 15 pares, 3 famílias
    fam, _amp, esc = C._grupo_mais_forte(sorted(forte + repetido))
    assert (fam, esc) == (12, 40)
    g = C.resumo_do_grupo_forte(forte + repetido)
    assert (g["escala"], g["familias"]) == (40, 12)
    # e com o repetido ANTES do forte na ordem: o mesmo
    fam, _amp, esc = C._grupo_mais_forte(sorted([(10.0, v) for v in (1.0, 2.0, 4.0) for _ in range(5)] + forte))
    assert (fam, esc) == (12, 40)


# ── no PDF: os tokens da folha inteira, na mesma passada ───────────────────

_PAREDE = b"2 w 40 320 m 560 320 l 560 800 l 40 800 l h S 52 332 m 548 332 l 548 788 l 52 788 l h S "


def _cadeia(esc, valores=_VALORES, x0=60.0, y0=780.0, passo=36.0):
    return [(x0, y0 - passo * i, ("%.2f" % v).replace(".", ","), v / (_PT_M * esc))
            for i, v in enumerate(valores)]


def _pdf(tmp_path, cotas, nome="folha.pdf"):
    pikepdf = pytest.importorskip("pikepdf")
    pdf = pikepdf.Pdf.new()
    pg = pdf.add_blank_page(page_size=(1191, 842))
    pg.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica)))
    corpo = b"1 w "
    for x, y, txt, L in cotas:
        corpo += b"%.2f %.2f m %.2f %.2f l S " % (x, y - 4, x + L, y - 4)
        corpo += b"BT /F1 9 Tf %.2f %.2f Td (%s) Tj ET " % (x + L / 2 - 9, y, txt.encode("latin-1"))
    pg.Contents = pdf.make_stream(corpo + _PAREDE)
    p = str(tmp_path / nome)
    pdf.save(p)
    return p


def _segs(path):
    import pdfplumber
    from pdfvec_rooms import _collect_raw_segments_rapido
    with pdfplumber.open(path) as pdf:
        return _collect_raw_segments_rapido(pdf.pages[0])


def _chave(tok):
    return (tok["text"], tok["value_m"], tuple(round(c, 3) for c in tok["center"]),
            tuple(round(c, 3) for c in tok["bbox"]))


def test_a_validacao_recebe_os_MESMOS_tokens_com_ou_sem_a_sombra(tmp_path):
    """Duas cadeias: 12 cotas à esquerda e 3 à direita. A região (a direita)
    devolve as 3 de sempre; a lista da sombra fica com as 15 da folha."""
    p = _pdf(tmp_path, _cadeia(50, x0=60) + _cadeia(50, valores=(0.90, 1.80, 2.70), x0=700))
    regiao = (650, 0, 1191, 842)
    antes = C.extract_cota_tokens(p, 0, regiao)
    todos = []
    depois = C.extract_cota_tokens(p, 0, regiao, _todos=todos)
    assert [_chave(t) for t in depois] == [_chave(t) for t in antes] and len(antes) == 3
    assert len(todos) == 15
    assert sorted(_chave(t) for t in todos) == sorted(_chave(t) for t in C.extract_cota_tokens(p, 0, None))
    # e sem região as duas listas são a mesma coisa
    todos2 = []
    inteira = C.extract_cota_tokens(p, 0, None, _todos=todos2)
    assert [_chave(t) for t in inteira] == [_chave(t) for t in todos2] and len(inteira) == 15
    # a lista da sombra não é a da validação: mexer numa não mexe na outra
    for t in todos:
        t["value_m"] = -1
    assert all(t["value_m"] > 0 for t in depois)


def test_a_lista_da_sombra_tem_teto(tmp_path, monkeypatch):
    p = _pdf(tmp_path, _cadeia(50, x0=60) + _cadeia(50, valores=(0.90, 1.80, 2.70), x0=700))
    monkeypatch.setattr(C, "MAX_TOKENS", 5)
    todos = []
    dentro = C.extract_cota_tokens(p, 0, (650, 0, 1191, 842), _todos=todos)
    assert len(dentro) == 3 and len(todos) == 5


def test_validate_scale_repassa_a_lista_e_nao_muda_o_resultado(tmp_path):
    p = _pdf(tmp_path, _cadeia(50))
    sem = C.validate_scale(p, 0, 50, None, walls=[], rooms=[])
    todos = []
    com = C.validate_scale(p, 0, 50, None, walls=[], rooms=[], _todos=todos)
    assert com == sem and len(todos) == 12


def test_no_pdf_o_grupo_da_folha_sai_dos_tokens_guardados(tmp_path):
    p = _pdf(tmp_path, _cadeia(52.6))
    todos = []
    C.extract_cota_tokens(p, 0, (0, 0, 10, 10), _todos=todos)        # a região não tem cota nenhuma
    g = C.resumo_do_grupo_forte(C.pares_cota_linha(todos, _segs(p)))
    assert g and abs(g["escala"] - 52.6) < 1.0 and g["padrao"] == 50, g


# ── a página inteira (o caminho da produção) ───────────────────────────────

def _mede(monkeypatch, path, carimbo=50):
    monkeypatch.setattr(pdfvec_carimbo, "read_carimbo_scale",
                        lambda *a, **k: {"main_scale": carimbo, "declared_scales": [carimbo], "indicadas": False})
    return pdf_vector._measure_page(path, 0, "sem-chave")


_DE_RELOGIO = ("secs", "etapas", "mem_etapas", "mem_kb", "mem_kb_inicio")


def test_a_pagina_medida_leva_o_grupo_de_cotas(tmp_path, monkeypatch):
    out = _mede(monkeypatch, _pdf(tmp_path, _cadeia(52.6)))
    g = out.get("cotas_grupo")
    assert g and g["familias"] == 12 and g["padrao"] == 50 and abs(g["razao_padrao"] - 1.052) < 0.02, out
    assert out.get("scale") == 50 and out.get("scale_src") == "carimbo"
    assert not [k for k in out if k.startswith("err_")], out


def test_a_sombra_NAO_DECIDE_ligada_ou_desligada_a_medicao_e_a_mesma(tmp_path, monkeypatch):
    p = _pdf(tmp_path, _cadeia(52.6))
    ligada = _mede(monkeypatch, p)
    monkeypatch.setenv("PDFVEC_GRUPO_DE_COTAS", "0")
    desligada = _mede(monkeypatch, p)
    assert "cotas_grupo" in ligada and "cotas_grupo" not in desligada
    a = {k: v for k, v in ligada.items() if k not in _DE_RELOGIO and k != "cotas_grupo"}
    b = {k: v for k, v in desligada.items() if k not in _DE_RELOGIO}
    assert a == b, {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
    assert "escala_validada" in a and "cotas_encontradas" in a and "scale" in a


def test_desligada_a_chamada_da_validacao_e_a_de_sempre(tmp_path, monkeypatch):
    """Com PDFVEC_GRUPO_DE_COTAS=0 a validação é chamada como antes da sombra:
    sem a lista (nem vazia) — nenhum trabalho a mais na página."""
    vistos = []
    real = C.validate_scale

    def espia(*a, **k):
        vistos.append(sorted(k))
        return real(*a, **k)

    monkeypatch.setattr(C, "validate_scale", espia)
    p = _pdf(tmp_path, _cadeia(52.6))
    _mede(monkeypatch, p)
    monkeypatch.setenv("PDFVEC_GRUPO_DE_COTAS", "0")
    _mede(monkeypatch, p)
    assert len(vistos) == 2 and "_todos" in vistos[0] and "_todos" not in vistos[1], vistos


def test_CONTROLE_folha_de_poucas_cotas_nao_registra_nada(tmp_path, monkeypatch):
    out = _mede(monkeypatch, _pdf(tmp_path, _cadeia(50, valores=_VALORES[:6])))
    assert "cotas_grupo" not in out and "cotas_grupo_erro" not in out, out


def test_CONTROLE_sem_os_tracos_da_pagina_a_sombra_nem_comeca(tmp_path, monkeypatch):
    """Sem a leitura única da página não há traço pra casar: a sombra não pede
    os tokens e não deixa rastro nenhum (nem de erro)."""
    monkeypatch.setenv("PDFVEC_PARSE_UNICO", "0")
    out = _mede(monkeypatch, _pdf(tmp_path, _cadeia(52.6)))
    assert "parse_unico" not in out and out.get("scale") == 50, out
    assert "cotas_grupo" not in out and "cotas_grupo_erro" not in out, out


def test_erro_na_sombra_nao_vira_falha_da_prancha(tmp_path, monkeypatch):
    """O erro fica numa chave que NÃO começa com `err_`: o main trata todo
    `err_*` com cara de falta de memória como prancha não medida, e avisa o
    cliente — por causa de uma linha de log, não."""
    def _quebra(*a, **k):
        raise MemoryError("sem memória na sombra")
    monkeypatch.setattr(C, "resumo_do_grupo_forte", _quebra)
    out = _mede(monkeypatch, _pdf(tmp_path, _cadeia(52.6)))
    assert "cotas_grupo" not in out
    assert out.get("cotas_grupo_erro", "").startswith("MemoryError"), out
    assert not [k for k in out if k.startswith("err_")], out
    assert M._saida_do_filho_pdfvec(0, out)[0] is None
    assert out.get("scale") == 50 and "cotas_encontradas" in out


# ── a linha do log ─────────────────────────────────────────────────────────

_G = {"escala": 52.6, "familias": 34, "amplitude": 12.5, "padrao": 50, "razao_padrao": 1.052}


def test_a_linha_diz_a_escala_em_uso_a_fonte_e_o_grupo():
    ln = M._linha_das_cotas_x_escala("folha_p0", {"scale": 50, "scale_src": "texto", "escala_validada": False,
                                                  "cotas_grupo": dict(_G)})
    assert ln == ("folha_p0: escala=50 fonte=texto validada=nao grupo=52.6 familias=34 amplitude=12.5 "
                  "razao=1.052 padrao=50 razao_padrao=1.052"), ln
    ln = M._linha_das_cotas_x_escala("x_p3", {"scale": 75.0, "scale_src": "viewport", "escala_validada": True,
                                              "cotas_grupo": dict(_G, escala=53.1, padrao=50, razao_padrao=1.062)})
    assert "escala=75 fonte=viewport validada=sim grupo=53.1" in ln and "razao=0.708" in ln, ln


def test_CONTROLE_sem_grupo_ou_sem_escala_nao_ha_linha():
    assert M._linha_das_cotas_x_escala("p", {"scale": 50, "scale_src": "carimbo"}) == ""
    assert M._linha_das_cotas_x_escala("p", {"cotas_grupo": dict(_G)}) == ""
    assert M._linha_das_cotas_x_escala("p", {"scale": 0, "cotas_grupo": dict(_G)}) == ""
    assert M._linha_das_cotas_x_escala("p", {"scale": "abc", "cotas_grupo": dict(_G)}) == ""
    assert M._linha_das_cotas_x_escala("p", {"scale": 50, "cotas_grupo": "lixo"}) == ""
    assert M._linha_das_cotas_x_escala("p", {"scale": 50, "cotas_grupo": {"escala": 0}}) == ""
    assert M._linha_das_cotas_x_escala("p", None) == "" and M._linha_das_cotas_x_escala("p", {}) == ""
    # fonte desconhecida não derruba a linha
    assert "fonte=?" in M._linha_das_cotas_x_escala("p", {"scale": 50, "cotas_grupo": dict(_G)})


def test_a_etapa_do_log_e_de_diagnostico():
    assert "pdfvec:cotas-x-escala" in M._STAGES_DIAGNOSTICO


def _process_job():
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "process_job"), None)
    assert fn is not None, "não achei o process_job"
    return fn


def _chama(no, nome):
    return isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == nome


def test_o_motor_grava_a_linha_num_try_SO_DELA():
    """🪤 Ponto de chamada. A linha mora no laço de medição, dentro do `try` que
    protege a promoção da prancha: sem um `try` próprio, uma falha no log cairia
    no `except` de fora e a prancha perderia a medição."""
    fn = _process_job()
    tries = [no for no in ast.walk(fn) if isinstance(no, ast.Try)
             and any(_chama(d, "_linha_das_cotas_x_escala") for b in no.body for d in ast.walk(b))]
    assert len(tries) >= 1, "o process_job não grava a linha das cotas × escala"
    t = min(tries, key=lambda no: no.end_lineno - no.lineno)             # o try mais de dentro
    assert t.end_lineno - t.lineno <= 8, "o try da sombra abraça mais do que a linha de log"
    assert len(t.handlers) == 1 and getattr(t.handlers[0].type, "id", "") == "Exception"
    assert [type(x) for x in t.handlers[0].body] == [ast.Pass]
    logs = [d for b in t.body for d in ast.walk(b) if _chama(d, "_log_error")]
    assert len(logs) == 1 and logs[0].args[0].value == "pdfvec:cotas-x-escala"
    sev = {k.arg: getattr(k.value, "value", None) for k in logs[0].keywords}
    assert sev.get("severity") == "info"
    chamada = next(d for b in t.body for d in ast.walk(b) if _chama(d, "_linha_das_cotas_x_escala"))
    assert [getattr(a, "id", None) for a in chamada.args] == ["_stem", "_vm"]
    # e nada dentro dele escreve na medição nem nas falhas
    nomes = {d.id for b in t.body for d in ast.walk(b) if isinstance(d, ast.Name) and isinstance(d.ctx, ast.Store)}
    assert nomes == {"_ln_cx"}, nomes
