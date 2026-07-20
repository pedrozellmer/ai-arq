# -*- coding: utf-8 -*-
"""Rede de regressão do QW1 (20/07): a trava do JobsStore mata a escrita-fantasma
(lost-update) que ressuscitava job de 'error' pra 'queued'/'processing' — a raiz
do job órfão que fez o Pedro reiniciar o Render 2x em 19/07.

Roda direto: `python tests/test_jobs_lock.py` (sem pytest — padrão da casa).
Deps: só stdlib + o próprio main. Prova DUPLA:
  (a) COM a trava real → 0 escritas perdidas (o fix funciona);
  (b) SEM a trava (nullcontext) → >0 perdidas (o bug existe e a trava é que resolve).
"""
import os
import sys
import tempfile
import threading
import contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_KEY", "x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")

import main  # noqa: E402
from models import ProcessingStatus  # noqa: E402


def _stress(n_jobs=12, iters=60):
    """Cada thread martela SÓ o seu job com update_field. Como update_field
    salva o dict INTEIRO, sem trava a thread B (com snapshot velho) sobrescreve
    o job da thread A — lost-update. Retorna a lista de jobs cujo valor final
    ficou defasado (< iters)."""
    d = tempfile.mkdtemp()
    main.JOBS_FILE = os.path.join(d, "_jobs.json")
    main._save_jobs({})
    for i in range(n_jobs):
        main.jobs[f"j{i}"] = ProcessingStatus(
            job_id=f"j{i}", status="queued", progress=0, current_step="seed")

    barrier = threading.Barrier(n_jobs)

    def worker(i):
        barrier.wait()  # todos largam juntos → concorrência máxima
        for k in range(iters):
            main.jobs.update_field(f"j{i}", progress=k + 1, current_step=f"s{k}")

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n_jobs)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    perdidos = []
    for i in range(n_jobs):
        try:
            prog = main.jobs[f"j{i}"].progress
        except KeyError:
            # Sem a trava o job pode SUMIR inteiro do JSON (pior que defasado) —
            # conta como perdido em vez de deixar o KeyError abortar o teste e
            # pular os cenários (b)/(c) que validam a produção. (achado revisão 20/07)
            prog = None
        if prog != iters:
            perdidos.append((f"j{i}", prog))
    return perdidos


def _phantom_error_test():
    """O cenário EXATO do órfão: uma thread marca 'error'; outra, com snapshot
    velho, salva o dict inteiro com o mesmo job em 'processing'. Com a trava, o
    read-modify-write é atômico e o 'error' final NÃO é ressuscitado pra
    'processing' por uma escrita baseada em leitura anterior à marcação."""
    d = tempfile.mkdtemp()
    main.JOBS_FILE = os.path.join(d, "_jobs.json")
    main._save_jobs({})
    main.jobs["orf"] = ProcessingStatus(job_id="orf", status="processing", progress=50)

    resultados = []
    barrier = threading.Barrier(2)

    def marca_error():
        barrier.wait()
        for _ in range(200):
            main.jobs.update_field("orf", status="error", error_message="falhou")

    def martela_processing():
        barrier.wait()
        for _ in range(200):
            main.jobs.update_field("orf", progress=99)  # NÃO mexe em status

    a = threading.Thread(target=marca_error)
    b = threading.Thread(target=martela_processing)
    a.start(); b.start(); a.join(); b.join()
    # Depois que 'error' foi setado, nenhuma escrita de OUTRO campo pode ter
    # apagado o status='error' (update_field faz merge, não overwrite).
    final = main.jobs["orf"]
    return final.status


def main_run():
    falhas = 0

    print("== (a) COM a trava real: stress de concorrência ==")
    perdidos = _stress()
    if perdidos:
        print(f"  ✗ FALHOU — {len(perdidos)} escrita(s) perdida(s): {perdidos[:5]}")
        falhas += 1
    else:
        print("  ok  0 escritas perdidas (trava serializa o read-modify-write)")

    print("== (a') fix vale: SEM a trava o bug aparece ==")
    _lock_real = main._JOBS_LOCK
    try:
        main._JOBS_LOCK = contextlib.nullcontext()  # no-op reentrante
        perdidos_sem = _stress()
    finally:
        main._JOBS_LOCK = _lock_real
    if perdidos_sem:
        print(f"  ok  sem trava → {len(perdidos_sem)} perdida(s) (prova que a trava é o que resolve)")
    else:
        # Não falha o build (concorrência é não-determinística), mas avisa.
        print("  ~   sem trava não perdeu desta vez (race não-determinística; ok)")

    print("== (b) status 'error' não é ressuscitado por escrita concorrente ==")
    st = _phantom_error_test()
    if st == "error":
        print("  ok  status final = 'error' (órfão morto na raiz)")
    else:
        print(f"  ✗ FALHOU — status final = '{st}' (esperado 'error')")
        falhas += 1

    print("== (c) escrita atômica: _jobs.json nunca fica corrompido ==")
    d = tempfile.mkdtemp()
    main.JOBS_FILE = os.path.join(d, "_jobs.json")
    main._save_jobs({"a": {"job_id": "a", "status": "done"}})
    import json
    with open(main.JOBS_FILE) as f:
        loaded = json.load(f)
    tmp_sobrou = [n for n in os.listdir(d) if n.endswith(".tmp")]
    if loaded.get("a", {}).get("status") == "done" and not tmp_sobrou:
        print("  ok  arquivo íntegro e sem .tmp órfão")
    else:
        print(f"  ✗ FALHOU — loaded={loaded} tmp={tmp_sobrou}")
        falhas += 1

    print("\n" + "=" * 46)
    print(f"RESULTADO: {'TODOS OK' if falhas == 0 else str(falhas) + ' FALHA(S)'}")
    return falhas


if __name__ == "__main__":
    sys.exit(1 if main_run() else 0)
