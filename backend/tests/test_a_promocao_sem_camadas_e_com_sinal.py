# -*- coding: utf-8 -*-
"""A promoção não calcula camadas, e a falta de memória continua visível.

🩸 10/09/2026 — reprocesso interno do job 5f28b6ab, primeira medição do pico por
etapa: a prancha mais pesada foi de 1.051 MB (depois das cotas) a 1.680 MB só no
passo de camadas (+629 MB), perto do teto de 1.907 MiB. E `out["layers"]` não é
lido por ninguém — nem o índice da promoção nem a keep-list da sombra.

🪤 Mas as camadas eram o ÚNICO passo que acusou falta de memória desde 02/09.
Tirar sem pôr outro sinal no lugar deixaria prancha no limite invisível. Por isso
este passo vem com dois sinais:
- log `pdfvec:perto-do-teto` quando o pico passa de 90% do teto (só observação);
- MemoryError deixa de ser engolido nas etapas que a planilha LÊ (salas e
  paredes): em vez de pular uma sala calado, vira `err_rooms`/`err_walls`.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

_FORA = ("secs", "etapas", "mem_etapas", "mem_kb", "mem_kb_inicio",
         "layers", "camadas", "err_layers")


# ── o interruptor das camadas ──────────────────────────────────────────────
def _mede_com_viewport(tmp_path, monkeypatch, espiao):
    import pdfvec_layers
    import pdf_vector
    from test_o_filho_devolve_o_proprio_pico import _pdf_em_branco, _sem_vision
    _sem_vision(monkeypatch)
    monkeypatch.setattr(pdfvec_layers, "scale_from_viewport",
                        lambda *a, **k: {"main_scale": 100.0,
                                         "main_bbox": (0.0, 0.0, 842.0, 595.0),
                                         "viewports": [], "page_size": (842.0, 595.0)})
    monkeypatch.setattr(pdfvec_layers, "summarize_layers", espiao)
    return pdf_vector._measure_page(_pdf_em_branco(tmp_path), 0, "")


def test_com_PDFVEC_CAMADAS_0_o_passo_nao_roda_e_o_resto_fica_igual(tmp_path, monkeypatch):
    chamadas = []

    def _espiao(*a, **k):
        chamadas.append(a)
        return {"n_layers": 0}

    monkeypatch.delenv("PDFVEC_CAMADAS", raising=False)
    com = _mede_com_viewport(tmp_path, monkeypatch, _espiao)
    assert len(chamadas) == 1 and "layers" in com["etapas"], (chamadas, com["etapas"])

    monkeypatch.setenv("PDFVEC_CAMADAS", "0")
    sem = _mede_com_viewport(tmp_path, monkeypatch, _espiao)
    assert len(chamadas) == 1, "com PDFVEC_CAMADAS=0 as camadas rodaram assim mesmo"
    assert "layers" not in sem and "layers" not in sem["etapas"], sem
    assert sem.get("camadas") == "puladas: a promoção não lê", sem
    assert ({k: v for k, v in com.items() if k not in _FORA}
            == {k: v for k, v in sem.items() if k not in _FORA}), (
        "pular as camadas mudou outra etapa da medição")


def test_a_PROMOCAO_manda_pular_as_camadas():
    from test_o_filho_da_medicao_diz_onde_morreu import _o_que_chegou_no_sp_run
    _argv, kw, _logs = _o_que_chegou_no_sp_run(rc=0, stdout="{}")
    assert (kw.get("env") or {}).get("PDFVEC_CAMADAS") == "0", kw.get("env")


def test_CONTROLE_a_SOMBRA_continua_calculando_camadas():
    """A receita comum do filho não pode levar o interruptor: a sombra e o
    pré-orçamento não pediram pra pular nada."""
    import filho_protegido
    assert "PDFVEC_CAMADAS" not in filho_protegido.ENV_DO_FILHO


# ── o sinal de perto do teto ────────────────────────────────────────────────
def _prancha(nome, vmpeak_kb):
    return {"arquivo": nome, "pagina": 0, "mem_kb": {"VmPeak": vmpeak_kb}}


def test_perto_do_teto_pega_a_prancha_na_FRONTEIRA_e_ordena_pelo_pico():
    import main
    limite_kb = int(2_000_000_000 * 0.9) // 1024
    achadas = main._pranchas_perto_do_teto(
        [_prancha("abaixo.pdf", limite_kb - 1), _prancha("na-fronteira.pdf", limite_kb),
         _prancha("acima.pdf", limite_kb + 50_000), {"arquivo": "sem-mem.pdf"}],
        teto_bytes=2_000_000_000)
    assert [a[0] for a in achadas] == ["acima.pdf p0", "na-fronteira.pdf p0"], achadas


def test_perto_do_teto_usa_o_teto_do_filho_protegido(monkeypatch):
    """O teto vem de UM lugar. Se o filho mudar o teto, o sinal acompanha."""
    import filho_protegido
    import main
    p = [_prancha("media.pdf", 900_000)]
    assert main._pranchas_perto_do_teto(p) == []
    monkeypatch.setattr(filho_protegido, "RLIMIT_BYTES", 1_000_000_000)
    assert [a[0] for a in main._pranchas_perto_do_teto(p)] == ["media.pdf p0"]


def test_a_linha_do_log_diz_quantas_e_quais():
    import main
    linha = main._linha_perto_do_teto([("a.pdf p0", 1800), ("b.pdf p3", 1750)],
                                      teto_bytes=2_000_000_000)
    assert linha.startswith("2 prancha(s) acima de 90% do teto"), linha
    assert "(1907 MiB)" in linha and "a.pdf p0=1800MB" in linha, linha
    assert "VmPeak=" not in linha, "a série do p95 casa 'VmPeak=' — outro log não pode imitar"


def test_o_process_job_grava_o_sinal_so_com_prancha_pesada():
    """🩸 10/09/2026 (revisão adversarial): a 1ª versão deste guarda só
    conferia na AST que a chamada e o log EXISTIAM — quatro mutantes (o `if`
    que nunca dispara, argumento trocado) passavam verdes. Agora o bloco real
    do `process_job` é EXECUTADO com `_log_error` espionado."""
    import _executa
    import main
    logs = []

    def _prancha_real(nome, pico_mb):
        return {"arquivo": nome, "pagina": 0, "rooms_m2": 10.0, "walls_m": 5.0,
                "mem_kb": {"VmPeak": pico_mb * 1024, "VmHWM": pico_mb * 512},
                "mem_kb_inicio": {"VmSize": 14 * 1024}, "etapas": {"rooms": 1.0},
                "mem_etapas": {}}

    def _roda(pranchas):
        logs.clear()
        escopo = dict(vars(main))
        escopo.update({
            "_pdfvec_por_prancha": {p["arquivo"]: p for p in pranchas},
            "_pdfvec_area_m2": 20.0, "job_id": "job-teste",
            "_log_error": lambda stage, msg, *a, **k: logs.append((stage, msg)),
        })
        _executa.roda("process_job", "_perto = _pranchas_perto_do_teto(", escopo, tamanho=1)
        return [m for st, m in logs if st == "pdfvec:perto-do-teto"]

    msgs = _roda([_prancha_real("pesada.pdf", 1800), _prancha_real("leve.pdf", 900)])
    assert len(msgs) == 1, msgs
    assert "pesada.pdf p0=1800MB" in msgs[0] and "leve.pdf" not in msgs[0], msgs[0]
    assert _roda([_prancha_real("leve.pdf", 900)]) == [], "alarme sem prancha pesada"


# ── falta de memória não é engolida nas etapas que a planilha lê ─────────────
#: 🩸 10/09/2026 (revisão adversarial): nas funções de SALA a falta de memória
#: vem do GEOS como GEOSException("bad allocation"/"std::bad_alloc") — o handler
#: tem que perguntar a `e_falta_de_memoria`; `except MemoryError` não pega. Nas
#: de PAREDE o parse é Python puro (pdfminer): MemoryError de verdade basta.
_FUNCOES_DE_SALA = ("_dedupe_rooms", "_drop_lattice", "_middle_layer")
_FUNCOES_DE_PAREDE = ("_form_local_segments", "_extract_raw_segments")
_FUNCOES_VIGIADAS = {
    "pdfvec_rooms.py": _FUNCOES_DE_SALA,
    "pdfvec_walls.py": _FUNCOES_DE_PAREDE,
}


def _pergunta_a_regua(handler):
    """O `except Exception as X` chama e_falta_de_memoria(X) e relança?"""
    if not handler.name:
        return False
    for n in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if (isinstance(n, ast.If) and isinstance(n.test, ast.Call)
                and getattr(n.test.func, "id", None) == "e_falta_de_memoria"
                and [ast.unparse(a) for a in n.test.args] == [handler.name]
                and any(isinstance(x, ast.Raise) for x in n.body)):
            return True
    return False


def _handlers_que_engolem(src, funcoes, aceita_so_memoryerror):
    """[(funcao, linha)] de todo `except Exception` que engole falta de memória."""
    faltando = []
    for n in ast.walk(ast.parse(src)):
        if not (isinstance(n, ast.FunctionDef) and n.name in funcoes):
            continue
        for t in ast.walk(n):
            if not isinstance(t, ast.Try):
                continue
            protegido = False
            for h in t.handlers:
                nome = ast.unparse(h.type) if h.type is not None else ""
                if nome == "MemoryError" and aceita_so_memoryerror:
                    protegido = (len(h.body) == 1 and isinstance(h.body[0], ast.Raise)
                                 and h.body[0].exc is None)
                if nome == "Exception" and not (protegido or _pergunta_a_regua(h)):
                    faltando.append((n.name, h.lineno))
    return faltando


def test_nenhum_handler_de_SALA_engole_a_falta_de_memoria_do_GEOS():
    from _corpo import fonte
    faltando = _handlers_que_engolem(fonte("pdfvec_rooms.py"), _FUNCOES_DE_SALA,
                                     aceita_so_memoryerror=False)
    assert not faltando, (
        "handler de sala que engole a falta de memória do GEOS: %s — "
        "`except MemoryError` não pega GEOSException('bad allocation')" % faltando)


def test_nenhum_handler_de_PAREDE_engole_MemoryError():
    from _corpo import fonte
    faltando = _handlers_que_engolem(fonte("pdfvec_walls.py"), _FUNCOES_DE_PAREDE,
                                     aceita_so_memoryerror=True)
    assert not faltando, faltando


def test_as_funcoes_vigiadas_existem_e_tem_os_seis_handlers():
    """Se uma função mudar de nome, os guardas acima passariam olhando o vazio."""
    from _corpo import fonte
    total = 0
    for arquivo, funcoes in _FUNCOES_VIGIADAS.items():
        arv = ast.parse(fonte(arquivo))
        nomes = {n.name for n in ast.walk(arv) if isinstance(n, ast.FunctionDef)}
        assert set(funcoes) <= nomes, (arquivo, set(funcoes) - nomes)
        for n in ast.walk(arv):
            if isinstance(n, ast.FunctionDef) and n.name in funcoes:
                total += sum(1 for t in ast.walk(n) if isinstance(t, ast.Try)
                             for h in t.handlers
                             if h.type is not None and ast.unparse(h.type) == "Exception")
    assert total == 6, total


def test_CONTROLE_o_guarda_REPROVA_handler_sem_a_protecao():
    nl = chr(10)
    sem = nl.join(["def _dedupe_rooms(r):", "    try:", "        x = 1",
                   "    except Exception:", "        pass", ""])
    so_memoryerror = nl.join(["def _dedupe_rooms(r):", "    try:", "        x = 1",
                              "    except MemoryError:", "        raise",
                              "    except Exception:", "        pass", ""])
    engole = nl.join(["def _form_local_segments(r):", "    try:", "        x = 1",
                      "    except MemoryError:", "        pass",
                      "    except Exception:", "        pass", ""])
    certo = nl.join(["def _dedupe_rooms(r):", "    try:", "        x = 1",
                     "    except Exception as _e:", "        if e_falta_de_memoria(_e):",
                     "            raise MemoryError(str(_e)) from _e", "        pass", ""])
    assert _handlers_que_engolem(sem, _FUNCOES_DE_SALA, False)
    assert _handlers_que_engolem(so_memoryerror, _FUNCOES_DE_SALA, False), (
        "a versão do commit 2961a96 (só MemoryError) tem que ser REPROVADA nas de sala")
    assert _handlers_que_engolem(engole, _FUNCOES_DE_PAREDE, True), (
        "um `except MemoryError: pass` também engole — tem que ser `raise`")
    assert not _handlers_que_engolem(certo, _FUNCOES_DE_SALA, False)


class _FaceQueEstoura:
    def __init__(self, erro):
        self._erro = erro

    @property
    def exterior(self):
        raise self._erro("sem memória montando o polígono")


def test_MemoryError_na_sala_SOBE_em_vez_de_pular_a_sala():
    import pdfvec_rooms
    with pytest.raises(MemoryError):
        pdfvec_rooms._middle_layer([_FaceQueEstoura(MemoryError)], 0.01, 1.0, 1000.0)


def test_CONTROLE_outro_erro_na_sala_continua_pulado():
    import pdfvec_rooms
    assert pdfvec_rooms._middle_layer([_FaceQueEstoura(ValueError)], 0.01, 1.0, 1000.0) == []


class _PaginaQueEstoura:
    height = 842.0
    lines = rects = curves = []

    def __init__(self, erro):
        self._erro = erro

    @property
    def page_obj(self):
        raise self._erro("sem memória lendo o conteúdo da página")


def test_MemoryError_na_parede_NAO_cai_no_parse_completo():
    import pdfvec_walls
    with pytest.raises(MemoryError):
        pdfvec_walls._extract_raw_segments(_PaginaQueEstoura(MemoryError))
