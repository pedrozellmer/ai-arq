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


def test_o_process_job_grava_o_sinal_junto_da_memoria():
    from _corpo import fonte
    arvore = ast.parse(fonte("main.py"))
    chama = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "_pranchas_perto_do_teto"]
    assert len(chama) == 1 and [ast.unparse(a) for a in chama[0].args] == ["_res"], (
        [ast.unparse(a) for c in chama for a in c.args])
    logs = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "_log_error" and n.args
            and isinstance(n.args[0], ast.Constant) and n.args[0].value == "pdfvec:perto-do-teto"]
    assert len(logs) == 1, len(logs)


# ── MemoryError não é engolido nas etapas que a planilha lê ──────────────────
_FUNCOES_VIGIADAS = {
    "pdfvec_rooms.py": ("_dedupe_rooms", "_drop_lattice", "_middle_layer"),
    "pdfvec_walls.py": ("_form_local_segments", "_extract_raw_segments"),
}


def _handlers_que_engolem_sem_memoryerror_antes(src, funcoes):
    """[(funcao, linha)] de todo `except Exception` sem um `except MemoryError:
    raise` ANTES dele no mesmo try."""
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
                if nome == "MemoryError":
                    protegido = (len(h.body) == 1 and isinstance(h.body[0], ast.Raise)
                                 and h.body[0].exc is None)
                if nome == "Exception" and not protegido:
                    faltando.append((n.name, h.lineno))
    return faltando


@pytest.mark.parametrize("arquivo", sorted(_FUNCOES_VIGIADAS))
def test_nenhum_except_Exception_engole_MemoryError(arquivo):
    from _corpo import fonte
    faltando = _handlers_que_engolem_sem_memoryerror_antes(fonte(arquivo),
                                                           _FUNCOES_VIGIADAS[arquivo])
    assert not faltando, (
        "handler que engole MemoryError calado em %s: %s — sob pressão de memória "
        "a geometria muda sem erro nenhum" % (arquivo, faltando))


def test_as_funcoes_vigiadas_existem_e_tem_os_seis_handlers():
    """Se uma função mudar de nome, o guarda acima passaria olhando o vazio."""
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
    src_sem = ("def _dedupe_rooms(r):" + chr(10) + "    try:" + chr(10) + "        x = 1" + chr(10)
               + "    except Exception:" + chr(10) + "        pass" + chr(10))
    src_engole = ("def _dedupe_rooms(r):" + chr(10) + "    try:" + chr(10) + "        x = 1" + chr(10)
                  + "    except MemoryError:" + chr(10) + "        pass" + chr(10)
                  + "    except Exception:" + chr(10) + "        pass" + chr(10))
    assert _handlers_que_engolem_sem_memoryerror_antes(src_sem, ("_dedupe_rooms",))
    assert _handlers_que_engolem_sem_memoryerror_antes(src_engole, ("_dedupe_rooms",)), (
        "um `except MemoryError: pass` também engole — tem que ser `raise`")


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
