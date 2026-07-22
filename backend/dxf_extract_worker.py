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
    p = dxf_path
    try:
        from dxf_slim import emagrecer_dxf_se_preciso
        s = emagrecer_dxf_se_preciso(p)
        if s:
            p = s
    except Exception as e:  # noqa: BLE001
        print(f"[worker dxf-slim] pulando ({e})", file=sys.stderr)

    from dwg_extractor import extract_from_file
    ext = extract_from_file(p, unit_factor_override=unit_factor)
    structured = ext.to_structured_prompt()

    with open(out_path, "wb") as f:
        pickle.dump((ext, structured, p), f, protocol=pickle.HIGHEST_PROTOCOL)


if __name__ == "__main__":
    main()
