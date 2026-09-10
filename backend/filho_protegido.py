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
    # 🩸 10/09/2026: liga a FOTO POR ETAPA (ver `imprimir_foto`). Sem ela, o
    # filho que estoura o tempo ou morre não diz em que etapa estava.
    "FILHO_IMPRIME_FOTO": "1",
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


#: Como a falta de memória chega ao Python. 🩸 10/09/2026: dentro do GEOS
#: (shapely) ela NÃO vira MemoryError — o GEOS captura o `std::bad_alloc` do C++
#: e o shapely levanta `GEOSException` com o texto do sistema: "bad allocation"
#: no Windows (MSVC), "std::bad_alloc" no Linux (libstdc++).
_MARCAS_DE_FALTA_DE_MEMORIA = ("MemoryError", "bad_alloc", "bad allocation")


def e_falta_de_memoria(erro) -> bool:
    """A exceção (ou o texto `Tipo: mensagem` de um `err_*`) é falta de memória?

    🩸 10/09/2026 — a revisão adversarial do próprio conserto achou, por três
    lentes independentes: eu tinha posto `except MemoryError: raise` em volta
    das chamadas do shapely em `pdfvec_rooms`, e o guarda simulava um
    MemoryError de Python. Sob teto de memória real o GEOS levanta
    `GEOSException('bad allocation')`: o raise nunca disparava, o par de salas
    continuava pulado calado (dedupe manteve 24 salas em vez de 12; sala de
    ponte de 12,45 m² aceita) e o classificador, que só procurava o texto
    "MemoryError", nem sabia que tinha faltado memória.
    🔑 Uma decisão, dois consumidores: os handlers da geometria (recebem a
    exceção) e o classificador da saída do filho (recebe o texto gravado).
    Só reconhece — não decide o que fazer com a prancha.
    """
    if isinstance(erro, MemoryError):
        return True
    if erro is None:
        return False
    texto = erro if isinstance(erro, str) else "%s: %s" % (type(erro).__name__, erro)
    return any(m in texto for m in _MARCAS_DE_FALTA_DE_MEMORIA)


#: Marca que separa a FOTO de uma etapa do JSON final da medição.
MARCA_DA_FOTO = "_foto_da_etapa"

#: Foto maior que isto não sai: é telemetria, não compete com o JSON final.
TETO_DA_FOTO = 3500


def imprimir_foto(campos) -> None:
    """Imprime, com flush, uma linha curta dizendo até onde o filho chegou.

    🩸 10/09/2026 — reprocesso interno do job 7ddbccc1: a medição estourou os
    75 s pela terceira vez, e a sombra, com 170 s, também. Nenhuma das duas
    disse EM QUE ETAPA o relógio venceu: o filho só imprime o JSON no fim, e
    quem morre no meio não imprime nada. Sem isso, qualquer conserto de tempo
    é chute.

    🔑 Só telemetria. Nada do que sai aqui vira medição na planilha.
    🪤 Três cuidados, cada um um furo que a revisão adversarial achou:
    - o env é conferido ANTES de montar qualquer coisa, e tudo mora num
      try/except: foto nunca derruba a medição, nem com MemoryError;
    - flush explícito: processo que aborta (SIGABRT) não esvazia o buffer;
    - a marca vai dentro da linha, pro pai nunca confundir foto com o JSON
      final.
    """
    try:
        if os.environ.get("FILHO_IMPRIME_FOTO") != "1":
            return
        dados = dict(campos or {})
        dados[MARCA_DA_FOTO] = 1
        linha = json.dumps(dados, ensure_ascii=True, separators=(",", ":"),
                           default=str)
        if len(linha) > TETO_DA_FOTO:
            return
        sys.stdout.write(linha + chr(10))
        sys.stdout.flush()
    except Exception:
        pass


def ultima_foto(saida) -> dict:
    """A última foto COMPLETA num stdout de filho — ou {} se não houver.

    🪤 No Linux o `TimeoutExpired.stdout` chega em BYTES mesmo com
    `text=True` (ou None, se nada foi lido); no Windows chega em str. Guarda
    que só testasse str passaria aqui e quebraria em produção.
    🪤 A última linha pode vir cortada no meio (o kill chega durante a
    escrita): vale a última linha INTEIRA que tenha a marca.
    """
    try:
        if saida is None:
            return {}
        if isinstance(saida, (bytes, bytearray)):
            saida = bytes(saida).decode("utf-8", "replace")
        for linha in reversed(str(saida).splitlines()):
            linha = linha.strip()
            if not (linha.startswith("{") and linha.endswith("}")):
                continue
            try:
                d = json.loads(linha)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get(MARCA_DA_FOTO):
                d.pop(MARCA_DA_FOTO, None)
                return d
    except Exception:
        return {}
    return {}


def foto_em_texto(foto) -> str:
    """A foto numa etiqueta curta pro log.

    🪤 "lida", não "concluída": no Linux uma foto escrita na janela final do
    relógio pode ainda estar no pipe quando o pai desiste. A etapa EM CURSO
    na hora da morte é a seguinte à que aparece aqui — e é desconhecida.
    """
    if not isinstance(foto, dict) or not foto.get("etapa"):
        return " [nenhuma etapa lida]"
    partes = ["ultima_etapa_lida=%s" % str(foto.get("etapa"))[:20]]
    if foto.get("t") is not None:
        partes.append("t=%ss" % foto.get("t"))
    if foto.get("vmpeak_mb"):
        partes.append("vmpeak=%sMB" % foto.get("vmpeak_mb"))
    return " [" + " ".join(partes) + "]"


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
    except subprocess.TimeoutExpired as e:
        r = {"skip": "%s estourou o tempo" % rotulo, "timeout_s": timeout_s}
        # 🩸 10/09/2026: até onde chegou. Aninhada, NUNCA no topo: quem não
        # conhece a foto a ignora, e a sombra não conta morte como medição.
        foto = ultima_foto(getattr(e, "stdout", None))
        if foto:
            r["foto"] = foto
        return r
    except Exception as e:
        return {"skip": "%s nao rodou" % rotulo,
                "err": "%s: %s" % (type(e).__name__, str(e)[:100])}
    if pr.returncode != 0:
        r = {"skip": "%s morreu" % rotulo, "rc": pr.returncode,
             "err": ((pr.stderr or "").strip()[-400:] or "(sem stderr)")}
        foto_da_morte = ultima_foto(pr.stdout)
        if foto_da_morte:
            r["foto"] = foto_da_morte
        return r
    # 🪤 A ÚLTIMA LINHA, não o buffer inteiro: bibliotecas e o registro de
    # cache do `llm_retry` imprimem ANTES do JSON. Ler tudo faz a medição boa
    # virar "JSON quebrado" — perda silenciosa no instrumento de medida.
    saida = (pr.stdout or "").strip()
    try:
        final = json.loads(saida.splitlines()[-1]) if saida else {}
    except (ValueError, TypeError, IndexError) as e:
        r = {"skip": "%s devolveu JSON quebrado" % rotulo,
             "err": "%s" % type(e).__name__}
        foto_do_quebrado = ultima_foto(saida)
        if foto_do_quebrado:
            r["foto"] = foto_do_quebrado
        return r
    # 🪤 rc=0 com uma FOTO na última linha: o filho saiu sem imprimir o JSON
    # final. Não é medição completa — nunca devolver a foto como se fosse.
    if isinstance(final, dict) and final.get(MARCA_DA_FOTO):
        return {"skip": "%s não terminou" % rotulo, "foto": ultima_foto(saida)}
    return final
