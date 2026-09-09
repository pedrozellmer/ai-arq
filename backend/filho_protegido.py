# -*- coding: utf-8 -*-
"""Trabalho pesado num processo FILHO com teto de memória do KERNEL.

🩸 POR QUE ESTE MÓDULO EXISTE (09/09/2026)

Em 03/09 um PDF de 2,63 MB fez a medição vetorial ir de 94,6 MB a 3.107,8 MB
contra um teto de 4 GiB, e o serviço ficou com **ZERO instância por 2 minutos**:
quem estivesse no site levou erro. A lição, escrita no comentário do conserto:

    memória não é proporcional a BYTES, é proporcional a quantos elementos
    vetoriais a prancha tem (~500× medido) — e teto de tamanho de arquivo
    não protege nada.

A produção foi consertada naquele dia. A SOMBRA não — e ficou seis dias com o
mesmo risco aberto. Quando fui consertar a sombra, escrevi uma **segunda cópia**
da receita; horas depois a auditoria achou uma **terceira porta** com o mesmo
risco, `POST /api/estimate-price`, que é **PÚBLICA e sem login**.

🔑 Três cópias da mesma decisão é a doença que esta casa persegue o dia inteiro:
a decisão é corrigida num lado e o cliente recebe o outro. Este módulo é o lado
único. Quem precisa rodar coisa que aloca sem limite — pdfplumber, shapely,
ezdxf, numpy — chama daqui.

⚠️ UM CONSUMIDOR AINDA NÃO MIGROU: o filho da medição vetorial de produção
(`main.py`, ~10900). Ele está entrelaçado com `_pdfvec_falhas`, seis diagnósticos
de saída muda e telemetria de memória por etapa, tudo provado em produção — mexer
nele no mesmo passo seria trocar risco conhecido por risco novo. O que importa
não é a duplicação em si, é a **DIVERGÊNCIA**: o guarda
`test_o_filho_protegido_e_um_so.py` exige que os números dele sejam os mesmos
daqui. ⏭️ Migrar quando houver uma janela sem cliente e bancada verde.

🪤 O que NÃO resolve, e já foi tentado:
- **Cronômetro**: `asyncio.wait_for` em volta de `run_in_threadpool` só para de
  ESPERAR. A thread continua viva alocando — não dá pra matar thread em Python.
  Só o kernel limita memória.
- **Teto de tamanho de arquivo**: o PDF que derrubou o serviço era 4,6× MENOR
  que o teto que existia.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

#: Teto de ENDEREÇO do filho. 📏 Escolhido com p95 medido (41 medições em 120
#: dias): mediana 270 MB, p90 1.252 MB, p95 1.544 MB, máximo 1.573 MB — zero
#: acima de 1.800 MB. 2 GB impediria as duas quedas de 03/09 e deixa folga.
#: 🚨 O MESMO número do filho da produção. Se um mudar, o guarda reprova.
RLIMIT_BYTES = 2_000_000_000

#: Env do FILHO — nunca do servidor.
#: 🪤 `RLIMIT_AS` cobra ENDEREÇO, não RAM. Medido em produção (PDF de 0,49 MB):
#: VmPeak 1.717 MB contra VmHWM 385 MB — 1,3 GB de endereço reservado que nunca
#: vira RAM. Parte é o OpenBLAS (que o numpy do shapely importa) criando
#: (nCPU−1) threads no import, parte são as arenas do malloc da glibc (128 MB
#: reservados por arena). Sem isto o teto mata medição legítima.
#: 🪤 `PYTHONFAULTHANDLER`: morte por OOM dentro de código C pula todo
#: try/except e sai com **stderr vazio** — sem ele, o diagnóstico é o silêncio.
#: Tem que estar no ambiente ANTES do `import numpy`, por isso no env e não no
#: texto do `-c`.
ENV_DO_FILHO = {
    "PYTHONFAULTHANDLER": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MALLOC_ARENA_MAX": "2",
}


def prefixo_do_teto(rlimit_bytes: int = RLIMIT_BYTES) -> list[str]:
    """As linhas que põem o teto do kernel. SEMPRE no topo do corpo.

    🚨 ORDEM É TUDO: pôr isto depois do `import` que aloca deixa o teto
    decorativo — o filho importa shapely/numpy e mede a prancha inteira sem
    limite nenhum. O `except` é obrigatório: no Windows não existe `resource`,
    e sem ele o filho morreria antes de trabalhar.
    """
    return [
        "try:",
        "    import resource; resource.setrlimit("
        "resource.RLIMIT_AS, ({0}, {0}))".format(int(rlimit_bytes)),
        "except Exception:",
        "    pass",
    ]


def rodar(corpo: list[str], argv: list[str], timeout_s: float,
          rlimit_bytes: int = RLIMIT_BYTES, rotulo: str = "filho") -> dict:
    """Roda `corpo` num filho protegido e devolve o JSON que ele imprimir.

    🔑 Devolve SEMPRE um dict. Toda forma de morte (OOM, aborto em código C,
    timeout, fork que falha, JSON quebrado) vira `{"skip": ..., "err": ...}` —
    quem chama nunca é derrubado, e a recusa fica REGISTRADA. Silêncio e
    recusa não podem ter a mesma cara.

    🪤 Os argumentos vão por ARGV, nunca embutidos no fonte: um caminho com
    aspa simples fecharia a string e o filho morreria de `SyntaxError` — que
    este runner arquivaria como "morreu", indistinguível de estouro de
    memória. Defeito disfarçado do defeito que a função existe pra conter.
    """
    linhas = prefixo_do_teto(rlimit_bytes) + list(corpo)
    cmd = [sys.executable, "-c", chr(10).join(linhas)] + [str(a) for a in argv]
    try:
        pr = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=timeout_s,
                            env={**os.environ, **ENV_DO_FILHO})
    except subprocess.TimeoutExpired:
        return {"skip": "%s estourou o tempo" % rotulo, "timeout_s": timeout_s}
    except Exception as e:
        return {"skip": "%s nao rodou" % rotulo,
                "err": "%s: %s" % (type(e).__name__, str(e)[:100])}
    if pr.returncode != 0:
        return {"skip": "%s morreu" % rotulo, "rc": pr.returncode,
                "err": ((pr.stderr or "").strip()[-400:] or "(sem stderr)")}
    # 🪤 A ÚLTIMA LINHA, não o buffer inteiro: bibliotecas e o registro de
    # cache do `llm_retry` imprimem ANTES do JSON. Ler tudo faz a medição boa
    # virar "JSON quebrado" — perda silenciosa no instrumento de medida.
    saida = (pr.stdout or "").strip()
    try:
        return json.loads(saida.splitlines()[-1]) if saida else {}
    except (ValueError, TypeError, IndexError) as e:
        return {"skip": "%s devolveu JSON quebrado" % rotulo,
                "err": "%s" % type(e).__name__}
