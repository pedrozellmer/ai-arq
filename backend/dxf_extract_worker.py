# -*- coding: utf-8 -*-
"""Worker de extração ISOLADA de UMA prancha DXF (fix confiabilidade 2026-07-22).

Roda a extração de geometria de um único DXF num processo SEPARADO, com teto de
memória (RLIMIT_AS aplicado pelo pai via preexec_fn). Assim, uma prancha densa que
carregaria GBs no ezdxf.readfile e estouraria os 4GB do container mata só ESTE
processo (malloc falha → MemoryError → sai != 0), e o servidor web fica de pé pra
todos os outros clientes. É o mesmo caminho do extrator in-process (emagrecer →
extract_from_file → to_structured_prompt), só que num filho matável.

Uso:  python dxf_extract_worker.py <dxf_path> <out_pickle> [unit_factor|""]
Saída: pickle de (DXFExtraction, structured_text: str, effective_path: str) em <out_pickle>.
Herda o env do pai (DXF_MEASURE_BLOCK_INFRA etc.) por padrão do subprocess.
"""
import sys
import os
import pickle


def main():
    if len(sys.argv) < 3:
        print("uso: dxf_extract_worker.py <dxf_path> <out_pickle> [unit_factor]", file=sys.stderr)
        sys.exit(2)
    dxf_path = sys.argv[1]
    out_path = sys.argv[2]
    unit_factor = None
    if len(sys.argv) > 3:
        raw = (sys.argv[3] or "").strip()
        if raw and raw.lower() != "none":
            try:
                unit_factor = float(raw)
            except ValueError:
                unit_factor = None

    # Mesmo pré-passo do caminho in-process: emagrece o DXF grande (best-effort).
    # 🪤 O RESULTADO TEM QUE SAIR DAQUI POR stderr. Este processo não pode
    # importar a app FastAPI pra chamar `_log_error` (pesado e circular), então
    # ele imprime com o marcador `[dxf-slim...]` e o PAI copia pro `error_log`
    # (ver `_extract_dxf_isolado`). Antes de 18/08/2026 nada era impresso no
    # caminho de sucesso e o `emagrecer_dxf_se_preciso` era chamado sem `log=`:
    # a proteção de memória podia estar falhando em toda prancha e o banco
    # continuava sem uma linha sequer a respeito.
    p = dxf_path
    try:
        from dxf_slim import emagrecer_dxf_se_preciso
        _tam = os.path.getsize(p)
        s = emagrecer_dxf_se_preciso(
            p, log=lambda _st, _msg: print(f"[dxf-slim] {_msg}", file=sys.stderr))
        if s:
            p = s
            print(f"[dxf-slim] {os.path.basename(dxf_path)}: emagreceu "
                  f"{_tam // 1048576} MB -> {os.path.getsize(p) // 1048576} MB",
                  file=sys.stderr)
        else:
            print(f"[dxf-slim] {os.path.basename(dxf_path)}: NAO emagreceu "
                  f"({_tam // 1048576} MB) — segue com o arquivo inteiro",
                  file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[dxf-slim] {os.path.basename(dxf_path)}: passo pulado "
              f"({type(e).__name__}: {e})", file=sys.stderr)

    from dwg_extractor import extract_from_file
    ext = extract_from_file(p, unit_factor_override=unit_factor)
    structured = ext.to_structured_prompt()

    with open(out_path, "wb") as f:
        pickle.dump((ext, structured, p), f, protocol=pickle.HIGHEST_PROTOCOL)


if __name__ == "__main__":
    main()
