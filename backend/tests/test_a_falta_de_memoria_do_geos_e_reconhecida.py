# -*- coding: utf-8 -*-
"""A falta de memória que vem de DENTRO do GEOS é reconhecida — e a envoltória
não roda na promoção.

🩸 10/09/2026 — a revisão adversarial do meu próprio conserto (commit 2961a96)
achou, por três lentes independentes: no shapely 2.1.2 / GEOS 3.13.1 a falta de
memória dentro do GEOS chega como `GEOSException("bad allocation")` (Windows) ou
`GEOSException("std::bad_alloc")` (Linux), NÃO como MemoryError. Os
`except MemoryError: raise` que eu tinha posto em `pdfvec_rooms` nunca
disparavam, e o meu guarda simulava um MemoryError de Python — tipo que essas
chamadas nunca produzem. Sob teto real, os céticos reproduziram: dedupe com 24
salas em vez de 12, e uma sala de ponte de 12,45 m² aceita.

🔑 Guarda de exceção tem que levantar a exceção que a BIBLIOTECA levanta.
"""
import json
import os
import subprocess
import sys

import pytest
from shapely.errors import GEOSException
from shapely.geometry import Polygon

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import filho_protegido as fp  # noqa: E402


# ── a régua ──────────────────────────────────────────────────────────────────
def test_reconhece_MemoryError_e_o_bad_alloc_do_GEOS_nos_dois_sistemas():
    assert fp.e_falta_de_memoria(MemoryError())
    assert fp.e_falta_de_memoria(GEOSException("bad allocation"))      # Windows (MSVC)
    assert fp.e_falta_de_memoria(GEOSException("std::bad_alloc"))     # Linux (libstdc++)
    assert fp.e_falta_de_memoria("GEOSException: std::bad_alloc")     # texto de um err_*
    assert fp.e_falta_de_memoria("MemoryError: ")


def test_CONTROLE_erro_de_topologia_nao_e_falta_de_memoria():
    assert not fp.e_falta_de_memoria(GEOSException("TopologyException: side location conflict"))
    assert not fp.e_falta_de_memoria(ValueError("geometria vazia"))
    assert not fp.e_falta_de_memoria("GEOSException: IllegalArgumentException: invalid")
    assert not fp.e_falta_de_memoria(None)
    assert not fp.e_falta_de_memoria("")


# ── os handlers de sala, com a exceção que o GEOS levanta de verdade ─────────
class _CascaQueEstoura:
    def __init__(self, erro):
        self._erro = erro

    def intersection(self, outra):
        raise self._erro


class _ArvoreFalsa:
    def __init__(self, geoms):
        self._n = len(list(geoms))

    def query(self, geom, predicate=None):
        return list(range(self._n))


def test_GEOS_sem_memoria_no_DEDUPE_sobe_como_MemoryError(monkeypatch):
    import pdfvec_rooms
    monkeypatch.setattr(pdfvec_rooms, "STRtree", _ArvoreFalsa)
    rooms = [(10.0, _CascaQueEstoura(GEOSException("bad allocation")), 0.0),
             (12.0, _CascaQueEstoura(GEOSException("bad allocation")), 0.0)]
    with pytest.raises(MemoryError):
        pdfvec_rooms._dedupe_rooms(rooms)


def test_CONTROLE_topologia_no_DEDUPE_continua_pulada(monkeypatch):
    import pdfvec_rooms
    monkeypatch.setattr(pdfvec_rooms, "STRtree", _ArvoreFalsa)
    rooms = [(10.0, _CascaQueEstoura(GEOSException("TopologyException: x")), 0.0),
             (12.0, _CascaQueEstoura(GEOSException("TopologyException: x")), 0.0)]
    mantidas, descartadas = pdfvec_rooms._dedupe_rooms(rooms)
    assert len(mantidas) == 2 and descartadas == 0


class _FaceQueEstoura:
    def __init__(self, erro):
        self._erro = erro

    @property
    def exterior(self):
        raise self._erro


def test_GEOS_sem_memoria_montando_a_SALA_sobe_como_MemoryError():
    import pdfvec_rooms
    with pytest.raises(MemoryError):
        pdfvec_rooms._middle_layer([_FaceQueEstoura(GEOSException("std::bad_alloc"))],
                                   0.01, 0.5, 1000.0)


def test_CONTROLE_topologia_montando_a_SALA_continua_pulada():
    import pdfvec_rooms
    assert pdfvec_rooms._middle_layer(
        [_FaceQueEstoura(GEOSException("TopologyException: x"))], 0.01, 0.5, 1000.0) == []


class _PonteQueEstoura:
    def __init__(self, erro):
        self._erro = erro

    def intersection(self, outra):
        raise self._erro


def test_GEOS_sem_memoria_medindo_a_PONTE_sobe_em_vez_de_aceitar_sala_fabricada(monkeypatch):
    """A pior das quatro: engolir aqui subestima a fração de ponte e a trava
    contra sala fabricada deixa passar — reproduzido sob teto real (12,45 m²)."""
    import pdfvec_rooms
    monkeypatch.setattr(pdfvec_rooms, "STRtree", _ArvoreFalsa)
    quadrado = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    with pytest.raises(MemoryError):
        pdfvec_rooms._middle_layer([quadrado], 0.01, 0.5, 1000.0,
                                   bridges=[_PonteQueEstoura(GEOSException("bad allocation"))])


# ── o classificador da saída do filho ────────────────────────────────────────
def test_classificador_reconhece_o_bad_alloc_do_GEOS_como_memoria():
    import main
    tipo, det = main._saida_do_filho_pdfvec(0, {"n_rooms": 3,
                                               "err_rooms": "GEOSException: std::bad_alloc"})
    assert tipo == "memoria" and "bad_alloc" in det, (tipo, det)


def test_CONTROLE_classificador_nao_chama_topologia_de_memoria():
    import main
    assert main._saida_do_filho_pdfvec(0, {"n_rooms": 3,
                                          "err_rooms": "GEOSException: TopologyException"}) == (None, "")


# ── a envoltória fora da promoção ────────────────────────────────────────────
def test_com_PDFVEC_ENVOLTORIA_0_a_envoltoria_nao_roda_e_o_resto_fica_igual(tmp_path, monkeypatch):
    from test_a_promocao_sem_camadas_e_com_sinal import _mede_com_viewport
    fora = ("secs", "etapas", "mem_etapas", "mem_kb", "mem_kb_inicio", "layers", "camadas",
            "err_layers", "envelope_m2", "envelope_m2_150", "envelope_top", "envoltoria")

    monkeypatch.delenv("PDFVEC_ENVOLTORIA", raising=False)
    com = _mede_com_viewport(tmp_path, monkeypatch, lambda *a, **k: {})
    assert "envoltoria" in com["etapas"] and "envelope_top" in com, com

    monkeypatch.setenv("PDFVEC_ENVOLTORIA", "0")
    sem = _mede_com_viewport(tmp_path, monkeypatch, lambda *a, **k: {})
    assert "envoltoria" not in sem["etapas"], sem["etapas"]
    assert not any(k.startswith("envelope") for k in sem), sem
    assert sem.get("envoltoria") == "pulada: a promoção não lê", sem
    assert ({k: v for k, v in com.items() if k not in fora}
            == {k: v for k, v in sem.items() if k not in fora}), "pular a envoltória mudou as salas"


def test_a_PROMOCAO_manda_pular_a_envoltoria_e_a_SOMBRA_nao():
    from test_o_filho_da_medicao_diz_onde_morreu import _o_que_chegou_no_sp_run
    _argv, kw, _logs = _o_que_chegou_no_sp_run(rc=0, stdout="{}")
    assert (kw.get("env") or {}).get("PDFVEC_ENVOLTORIA") == "0", kw.get("env")
    assert "PDFVEC_ENVOLTORIA" not in fp.ENV_DO_FILHO


# ── a prova que só o Linux dá: teto de memória REAL dentro do GEOS ───────────
@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="RLIMIT_AS de verdade: Linux (o CI é Linux, a produção também)")
def test_no_linux_a_falta_de_memoria_REAL_do_GEOS_e_reconhecida():
    nl = chr(10)
    codigo = nl.join([
        "import json, resource, sys",
        "sys.path.insert(0, sys.argv[1])",
        "import filho_protegido as f",
        "from shapely.geometry import Point",
        "vm = int(open('/proc/self/status').read().split('VmSize:')[1].split()[0]) * 1024",
        "lim = vm + 64_000_000",
        "resource.setrlimit(resource.RLIMIT_AS, (lim, lim))",
        "try:",
        "    g = Point(0, 0).buffer(1e6, quad_segs=4_000_000)",
        "    print(json.dumps({'sem_erro': True, 'n': len(g.exterior.coords)}))",
        "except BaseException as e:",
        "    print(json.dumps({'tipo': type(e).__name__, 'texto': str(e)[:200],",
        "                      'reconhece': f.e_falta_de_memoria(e)}))",
    ])
    r = subprocess.run([sys.executable, "-c", codigo, _BACKEND], capture_output=True,
                       text=True, timeout=120)
    linhas = [l for l in (r.stdout or "").splitlines() if l.startswith("{")]
    if not linhas:
        pytest.skip("o filho não devolveu resultado (rc=%s): %s"
                    % (r.returncode, (r.stderr or "")[-300:]))
    d = json.loads(linhas[-1])
    if d.get("sem_erro"):
        pytest.skip("a alocação coube no teto; nada a provar nesta máquina")
    print(chr(10) + "[GEOS sem memória no Linux] %s: %s" % (d["tipo"], d["texto"]))
    assert d["reconhece"], d
