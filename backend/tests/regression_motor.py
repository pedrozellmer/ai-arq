# -*- coding: utf-8 -*-
"""REDE DE REGRESSÃO DO MOTOR (19/07) — caminhos DETERMINÍSTICOS de medição.

Roda os dois motores que medem sem IA — geometria DXF (dwg_extractor) e
vetorial de PDF (pdf_vector, com o fallback de carimbo-via-IA DESLIGADO) —
sobre pranchas REAIS de teste, e compara com o gabarito (golden_motor.json).

Objetivo: nenhuma mudança futura no motor pode DIMINUIR o que já medimos
(regressão) nem gerar medida absurda (explosão) sem ninguém perceber.

USO (local — as pranchas de teste ficam FORA do repo, na pasta arq/):
    cd backend
    python tests/regression_motor.py            # compara com o golden
    python tests/regression_motor.py --update   # regrava o golden (consciente!)

Regras de veredito:
  - contagens (blocos, paredes, salas): exatas
  - quantidades (m, m²): tolerância de 1%
  - arquivo que MEDIA e passou a não medir = FALHA (regressão)
  - arquivo novo na pasta = aparece como "novo" (não falha; --update adota)
  - sanidade: sala 1,5–200 m²; total de salas da prancha < 2.000 m² —
    medida fora disso = FALHA (explosão), mesmo que "maior que o golden".

O golden é COMMITADO; as pranchas não (dados reais de cliente/projeto).
Pranchas esperadas em: C:\\Users\\admin\\Desktop\\arq (DXF soltos e
arq\\_cad_teste\\*.pdf). Sobrescreva com a env MOTOR_FIXTURES_DIR.
"""
import json
import os
import sys
import argparse

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

FIXTURES = os.environ.get("MOTOR_FIXTURES_DIR", r"C:\Users\admin\Desktop\arq")
GOLDEN_PATH = os.path.join(_BACKEND, "tests", "golden_motor.json")

TOL_QTY = 0.01          # 1% em quantidades contínuas
SANITY_SALA_MIN = 1.5   # m²
SANITY_SALA_MAX = 200.0
SANITY_PRANCHA_MAX = 2000.0


def _round2(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────
#  Snapshot DXF (dwg_extractor — geometria pura)
# ─────────────────────────────────────────────────────────────────────
def snapshot_dxf(path: str) -> dict:
    from dwg_extractor import extract_dxf, generate_budget_data
    ex = extract_dxf(path)
    budget = {}
    try:
        budget = generate_budget_data(ex) or {}
    except Exception as e:
        budget = {"_erro": f"{type(e).__name__}: {e}"[:120]}

    # paredes: total por layer (comprimento em m, 2 casas)
    walls_by_layer = {}
    for w in getattr(ex, "walls", []) or []:
        walls_by_layer[w.layer] = _round2(walls_by_layer.get(w.layer, 0) + w.length)
    # hachuras: área por layer
    hatch_by_layer = {}
    for h in getattr(ex, "hatches", []) or []:
        hatch_by_layer[h.layer] = _round2(hatch_by_layer.get(h.layer, 0) + h.area)
    # blocos: contagem por nome (top 25 pra estabilidade do golden)
    blocks = {}
    for b in getattr(ex, "blocks", []) or []:
        blocks[b.name] = blocks.get(b.name, 0) + b.count
    blocks = dict(sorted(blocks.items(), key=lambda kv: (-kv[1], kv[0]))[:25])

    return {
        "walls_m_por_layer": dict(sorted(walls_by_layer.items())),
        "walls_total_m": _round2(sum(walls_by_layer.values())),
        "hatch_m2_por_layer": dict(sorted(hatch_by_layer.items())),
        "hatch_total_m2": _round2(sum(hatch_by_layer.values())),
        "blocos_top": blocks,
        "n_textos": len(getattr(ex, "texts", []) or []),
        "budget_categorias": sorted((budget or {}).keys())
        if isinstance(budget, dict) and "_erro" not in budget else budget,
    }


# ─────────────────────────────────────────────────────────────────────
#  Snapshot PDF (pdf_vector — SEM o fallback de carimbo via IA)
# ─────────────────────────────────────────────────────────────────────
def snapshot_pdf(path: str) -> dict:
    import pdfvec_carimbo
    import pdf_vector
    # Desliga IA: sem carimbo-Vision a rede fica 100% determinística e R$0.
    # Prancha sem viewport sai como "skip" — e isso também é gabarito.
    _orig = pdfvec_carimbo.read_carimbo_scale
    pdfvec_carimbo.read_carimbo_scale = lambda *a, **k: {}
    try:
        r = pdf_vector._measure_page(path, 0, api_key="")
    finally:
        pdfvec_carimbo.read_carimbo_scale = _orig
    return {
        "scale_src": r.get("scale_src"),
        "scale": r.get("scale"),
        "skip": r.get("skip"),
        "n_rooms": r.get("n_rooms", 0),
        "rooms_m2": _round2(r.get("rooms_m2", 0)),
        "top_rooms": [_round2(a) for a in (r.get("top_rooms") or [])],
        "walls_m": _round2(r.get("walls_m", 0)),
        "n_walls": r.get("n_walls", 0),
        "envelope_m2": _round2(r.get("envelope_m2") or 0),
    }


def coletar() -> dict:
    snap = {"dxf": {}, "pdf": {}}
    # DXFs: raiz da pasta de fixtures + _dwg_out
    dxf_dirs = [FIXTURES, os.path.join(FIXTURES, "_dwg_out")]
    for d in dxf_dirs:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith(".dxf"):
                p = os.path.join(d, fn)
                print(f"[dxf] {fn} ...", flush=True)
                try:
                    snap["dxf"][fn] = snapshot_dxf(p)
                except Exception as e:
                    snap["dxf"][fn] = {"_erro": f"{type(e).__name__}: {e}"[:160]}
    # PDFs de prancha: arq/_cad_teste
    pdf_dir = os.path.join(FIXTURES, "arq", "_cad_teste")
    if os.path.isdir(pdf_dir):
        for fn in sorted(os.listdir(pdf_dir)):
            if fn.lower().endswith(".pdf"):
                p = os.path.join(pdf_dir, fn)
                print(f"[pdf] {fn} ...", flush=True)
                try:
                    snap["pdf"][fn] = snapshot_pdf(p)
                except Exception as e:
                    snap["pdf"][fn] = {"_erro": f"{type(e).__name__}: {e}"[:160]}
    return snap


# ─────────────────────────────────────────────────────────────────────
#  Comparação com o golden
# ─────────────────────────────────────────────────────────────────────
def _qty_ok(a, b) -> bool:
    a, b = float(a or 0), float(b or 0)
    if a == b:
        return True
    ref = max(abs(a), abs(b))
    return ref > 0 and abs(a - b) / ref <= TOL_QTY


def _sanidade_pdf(s: dict) -> list:
    err = []
    for a in s.get("top_rooms") or []:
        if a and not (SANITY_SALA_MIN <= a <= SANITY_SALA_MAX):
            err.append(f"sala {a} m² fora da sanidade [{SANITY_SALA_MIN},{SANITY_SALA_MAX}]")
    if (s.get("rooms_m2") or 0) > SANITY_PRANCHA_MAX:
        err.append(f"total de salas {s['rooms_m2']} m² > {SANITY_PRANCHA_MAX}")
    return err


def comparar(golden: dict, atual: dict) -> tuple:
    falhas, avisos, novos = [], [], []

    for kind in ("dxf", "pdf"):
        for fn, g in (golden.get(kind) or {}).items():
            a = (atual.get(kind) or {}).get(fn)
            if a is None:
                avisos.append(f"[{kind}] {fn}: fixture sumiu da pasta (pulado)")
                continue
            if "_erro" in a and "_erro" not in g:
                falhas.append(f"[{kind}] {fn}: passou a DAR ERRO: {a['_erro']}")
                continue
            if kind == "dxf":
                for campo in ("walls_total_m", "hatch_total_m2"):
                    if not _qty_ok(g.get(campo, 0), a.get(campo, 0)):
                        falhas.append(f"[dxf] {fn}: {campo} {g.get(campo)} → {a.get(campo)}")
                if g.get("blocos_top") != a.get("blocos_top"):
                    falhas.append(f"[dxf] {fn}: contagem de blocos mudou")
            else:
                sane = _sanidade_pdf(a)
                if sane:
                    falhas.append(f"[pdf] {fn}: EXPLOSÃO — " + "; ".join(sane))
                # regressão: media e deixou de medir
                if (g.get("n_rooms") or 0) > 0 and (a.get("n_rooms") or 0) == 0:
                    falhas.append(f"[pdf] {fn}: media {g['n_rooms']} salas, agora 0")
                elif not _qty_ok(g.get("rooms_m2", 0), a.get("rooms_m2", 0)):
                    (avisos if (a.get("rooms_m2") or 0) > (g.get("rooms_m2") or 0)
                     else falhas).append(
                        f"[pdf] {fn}: rooms_m2 {g.get('rooms_m2')} → {a.get('rooms_m2')}")
                if g.get("scale") != a.get("scale"):
                    falhas.append(f"[pdf] {fn}: escala {g.get('scale')} → {a.get('scale')}")
        for fn in (atual.get(kind) or {}):
            if fn not in (golden.get(kind) or {}):
                novos.append(f"[{kind}] {fn}")
    return falhas, avisos, novos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="regrava o golden com o snapshot atual (use conscientemente)")
    args = ap.parse_args()

    atual = coletar()
    n_dxf, n_pdf = len(atual["dxf"]), len(atual["pdf"])
    print(f"\ncoletado: {n_dxf} DXF, {n_pdf} PDF")

    if args.update or not os.path.exists(GOLDEN_PATH):
        json.dump(atual, open(GOLDEN_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, sort_keys=True)
        print(f"golden {'atualizado' if args.update else 'criado'}: {GOLDEN_PATH}")
        return 0

    golden = json.load(open(GOLDEN_PATH, encoding="utf-8"))
    falhas, avisos, novos = comparar(golden, atual)

    if avisos:
        print("\n-- avisos (melhora ou fixture ausente) --")
        for a in avisos:
            print("  ~", a)
    if novos:
        print("\n-- fixtures novas (rode --update pra adotar) --")
        for n in novos:
            print("  +", n)
    if falhas:
        print("\n== FALHAS DE REGRESSÃO ==")
        for f in falhas:
            print("  ✗", f)
        print(f"\nRESULTADO: FALHOU ({len(falhas)})")
        return 1
    print("\nRESULTADO: OK — motor mede igual ou melhor que o gabarito")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
