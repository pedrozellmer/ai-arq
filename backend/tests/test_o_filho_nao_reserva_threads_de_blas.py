# -*- coding: utf-8 -*-
"""O filho da medição de PDF não reserva endereço virtual pra threads de BLAS.

🔬 05/09/2026, PASSO 8 do estudo do teto. Medido em produção (filhote ev1c03c1,
PDF de 0,49 MB): VmPeak 1.717 MB contra VmHWM 385 MB — 1,3 GB de endereço
reservado que não é RAM. O RLIMIT_AS de 2 GB cobra ENDEREÇO, então a folga come
o teto: o filho do cliente-39 morreu com ~1 GB de RAM real.

Parte da reserva é o OpenBLAS (o numpy que o shapely importa) criando (nCPU−1)
threads com pilha + buffers no import, e as arenas do malloc da glibc. O filho
não faz operação BLAS nenhuma e é monothread em Python. Duas variáveis no env
do FILHO — nunca no do servidor — cortam isso. Zero mudança de comportamento.

🧪 Controle positivo em Linux: o mesmo `import numpy` com e sem
OPENBLAS_NUM_THREADS=1 — o VmSize com a variável não pode ser maior; o teste
imprime o delta pra ficar registrado no CI (a máquina do CI tem poucos CPUs,
então o ganho aqui é pequeno; o que importa é a direção).
"""
import os
import subprocess
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

from _corpo import fonte, sem_comentarios          # noqa: E402

_SRC = sem_comentarios(fonte("main.py"))
_SO_LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"),
                               reason="/proc e o OpenBLAS com threads são coisa de Linux; produção é Linux")


def _trecho_da_chamada():
    i = _SRC.find("_pr = _sp.run(_cmd")
    assert i > 0, "a chamada do filho sumiu ou mudou de nome"
    return _SRC[i:i + 500]


# ── o código de produção ───────────────────────────────────────────────────
def test_o_env_do_filho_LEVA_as_duas_variaveis():
    t = _trecho_da_chamada()
    assert '"OPENBLAS_NUM_THREADS": "1"' in t, (
        "o filho voltou a importar numpy com OpenBLAS multithread — cada thread "
        "reserva pilha + buffers de endereço virtual, que o RLIMIT_AS cobra")
    assert '"MALLOC_ARENA_MAX": "2"' in t
    assert "**os.environ" in t, "o env do filho tem que HERDAR o do servidor"
    assert '"PYTHONFAULTHANDLER": "1"' in t, "o passo 1 não pode ter saído junto"


def test_as_variaveis_NAO_sao_postas_no_processo_do_servidor():
    """🚨 Só no filho. No servidor, OPENBLAS_NUM_THREADS=1 mexeria em coisa que
    a gente não mediu, e MALLOC_ARENA_MAX=2 num processo com threads (uvicorn,
    sombra, e-mail) troca memória por contenção."""
    for v in ("OPENBLAS_NUM_THREADS", "MALLOC_ARENA_MAX"):
        assert f'os.environ["{v}"]' not in _SRC and f"os.environ['{v}']" not in _SRC, (
            f"{v} está sendo gravada no os.environ do SERVIDOR — isso é o passo 8 no lugar errado")
        assert f'os.environ.setdefault("{v}"' not in _SRC


def test_o_texto_do_menos_c_e_o_cronometro_NAO_mudaram():
    t = _trecho_da_chamada()
    assert "timeout=75" in t
    i = _SRC.find("_cmd = [_sysv.executable")
    assert "resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000)" in _SRC[i:i + 600], (
        "o passo 8 não mexe no valor do teto — isso é o passo 11, com dado")


# ── o comportamento, no sistema que importa ────────────────────────────────
def _vmsize_apos_import_numpy(env_extra: dict) -> int:
    code = ("import numpy\n"
            "s = open('/proc/self/status').read()\n"
            "print([l for l in s.splitlines() if l.startswith('VmSize')][0].split()[1])")
    env = {k: v for k, v in os.environ.items() if k not in ("OPENBLAS_NUM_THREADS", "MALLOC_ARENA_MAX")}
    env.update(env_extra)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
    if r.returncode != 0:
        pytest.skip(f"numpy não importou neste ambiente: {r.stderr[-200:]}")
    return int(r.stdout.strip())


@_SO_LINUX
def test_CONTROLE_com_a_variavel_o_endereco_virtual_do_import_nao_cresce():
    sem = _vmsize_apos_import_numpy({})
    com = _vmsize_apos_import_numpy({"OPENBLAS_NUM_THREADS": "1", "MALLOC_ARENA_MAX": "2"})
    print(f"\n[passo 8] VmSize após import numpy: sem={sem // 1024} MB · com={com // 1024} MB · "
          f"delta={(sem - com) // 1024} MB (nCPU={os.cpu_count()})")
    assert com <= sem, (
        f"com as variáveis o VmSize CRESCEU ({com} kB > {sem} kB) — a hipótese do passo 8 está errada")


# ── controle do guarda de fonte ───────────────────────────────────────────
def test_CONTROLE_guarda_reprova_a_chamada_do_passo_1_sozinha():
    antiga = ('_pr = _sp.run(_cmd, capture_output=True, text=True, timeout=75,\n'
              '              env={**os.environ, "PYTHONFAULTHANDLER": "1"})')
    assert '"OPENBLAS_NUM_THREADS": "1"' not in antiga
