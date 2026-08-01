# -*- coding: utf-8 -*-
"""Medição Vetorial de PDF — SHADOW MODE v1.

Mede a geometria vetorial das pranchas PDF (escala do carimbo via Vision +
view principal + ambientes/paredes via shapely) e LOGA o resultado no
error_log (stage 'pdfvec:shadow', severity 'info') pra comparação offline
com o que o Vision extraiu. NÃO altera nada visível pro usuário.

Validado offline (06-07/07/2026) contra orçamento humano real (Granado 14º
pav): envoltória ±1% entre pranchas independentes, paredes ±2% em 4 pranchas.
Detalhes: memória project_spike_pdf_vetorial_20260706 + docs/ do repo.

Regras de segurança:
- Roda DEPOIS do job estar 'done', em thread daemon — nunca atrasa o cliente.
- Budget duro de tempo total; caps de segmentos nos módulos; try/except em
  cada etapa (resultado parcial ainda é logado).
- PDFVEC_SHADOW=0 no ambiente desliga tudo.
- Escala "INDICADAS"/ausente → pula a página (nunca chuta — regra nº 1).
"""
from __future__ import annotations

import json
import os
import threading
import time

MAX_PAGES = 3          # páginas medidas por job (as primeiras)
BUDGET_S = 180.0       # teto de tempo total do shadow por job
MAX_FILE_MB = 12       # PDF maior que isso não é medido (memória)


def _measure_page(pdf_path: str, page_index: int, api_key: str) -> dict:
    """Mede UMA página. Cada etapa é best-effort; devolve o que conseguiu."""
    out: dict = {"file": os.path.basename(pdf_path)[:60], "page": page_index}
    t0 = time.time()

    # 1) ESCALA — fonte primária: viewport embutido no PDF (exato, R$0, resolve
    # "INDICADAS"). Fallback: carimbo via Vision. (Achado #2 do estudo 07/07.)
    den = None
    bbox = None
    alt_viewports: list = []      # demais viewports do /VP (fallback de salas)
    vp_page_area = None
    try:
        from pdfvec_layers import scale_from_viewport
        vp = scale_from_viewport(pdf_path, page_index)
        if vp.get("main_scale"):
            den = vp["main_scale"]
            bbox = vp.get("main_bbox")  # bbox exato da view principal (melhor que clustering)
            out["scale_src"] = "viewport"
            out["scale_snapped"] = vp.get("snapped")
            out["n_viewports"] = len(vp.get("viewports", []))
            alt_viewports = [v for v in vp.get("viewports", [])
                             if v.get("bbox") != bbox]
            pw, ph = vp.get("page_size", (0.0, 0.0))
            vp_page_area = (pw * ph) or None
    except Exception as e:
        out["err_viewport"] = f"{type(e).__name__}: {e}"[:120]

    if not den:  # fallback: carimbo Vision
        try:
            from pdfvec_carimbo import read_carimbo_scale
            car = read_carimbo_scale(pdf_path, page_index)
            out["declared"] = car.get("declared_scales")
            out["indicadas"] = bool(car.get("indicadas"))
            den = car.get("main_scale")
            if den:
                out["scale_src"] = "carimbo"
        except Exception as e:
            out["err_carimbo"] = f"{type(e).__name__}: {e}"[:120]

    if not den:
        # 3ª fonte: DERIVAR a escala das cotas escritas (01/08/2026).
        # Medido nas 30 pranchas da sombra: 47% morriam aqui, mesmo tendo cota
        # desenhada — uma delas trazia 122 cotas. A cota até então só validava
        # uma escala já conhecida; agora ela também descobre.
        # Roda por último e só quando as outras duas falham: não pode regredir
        # nada que hoje funciona.
        try:
            from pdfvec_cotas import derive_scale_from_cotas
            from pdfvec_walls import detect_walls
            # 🪤 Sondagem PERMISSIVA. O filtro de espessura do detect_walls é em
            # METROS, então depende da escala — que é justamente o que não
            # sabemos. Assumir 1:1 não acha parede nenhuma. Solução: sondar com
            # 1:100 e abrir a faixa de espessura (0,02–1,0 m ⇒ ~0,6 a 28 pt),
            # o que cobre parede desenhada de 1:20 a 1:200. Só os COMPRIMENTOS
            # EM PONTOS (span_pt) são usados na votação, e esses não dependem
            # da escala — o palpite de 1:100 só define o que passa no filtro.
            _w = detect_walls(pdf_path, page_index, scale_denominator=100,
                              region_bbox=None, thickness_range_m=(0.02, 1.0))
            _cot = derive_scale_from_cotas(pdf_path, page_index, None,
                                           walls=(_w or {}).get("walls"),
                                           rooms_pt=None)
            out["cotas_derivacao"] = {k: _cot.get(k) for k in
                                      ("votos", "segundo_lugar", "total_pares",
                                       "n_cotas", "confianca")}
            if _cot.get("scale"):
                den = float(_cot["scale"])
                out["scale_src"] = "cotas"
                out["scale_derivada_por_cota"] = True
        except Exception as e:
            out["err_cotas_derive"] = f"{type(e).__name__}: {e}"[:120]

    if not den:
        out["skip"] = "sem escala (viewport, carimbo nem cota)"
        out["secs"] = round(time.time() - t0, 1)
        return out
    out["scale"] = den

    # 2) view principal — se o viewport não deu o bbox, cai pro clustering
    if bbox is None:
        try:
            from pdfvec_views import detect_views
            views = detect_views(pdf_path, page_index)
            out["n_views"] = len(views)
            main = next((v for v in views if v.get("is_main")), None)
            if main:
                bbox = main["bbox"]
        except Exception as e:
            out["err_views"] = f"{type(e).__name__}: {e}"[:120]

    # 3) ambientes (banda de sala) + envoltória (banda alta, ponte proporcional)
    room_den, room_bbox = den, bbox   # viewport que efetivamente mediu salas
    rooms_ok: list = []               # salas finais (consumidas pela validação por cota)
    walls_ok: list = []               # paredes finais (idem)
    try:
        from pdfvec_rooms import PT_TO_M, detect_rooms
        # bridge_gaps_m=1.2: se a geometria pura fechar quase nada, refaz com
        # ponte de vão de porta (até 1,2 m reais, proporcional à escala) e
        # adota só se medir mais. Sala que dependa de ponte demais é
        # descartada lá dentro (regra nº 1).
        rooms, rmeta = detect_rooms(pdf_path, page_index, den, bbox,
                                    bridge_gaps_m=1.2, return_meta=True)
        # fallback multi-viewport: em prancha de DETALHE a viewport principal
        # (maior área) pode ser uma VISTA/elevação — 0 salas ali é honesto,
        # mas a PLANTA mora numa viewport irmã. Cada viewport do /VP traz a
        # própria escala exata (zero chute); tenta as irmãs e fica com a que
        # mais mede. Viewports < 5% da folha (miniatura/keyplan) ficam fora:
        # planta inteira espremida + ponte = "sala" falsa.
        if not rooms and alt_viewports:
            best = None
            tried = 0
            for v in sorted(alt_viewports, key=lambda v: -abs(
                    (v["bbox"][2] - v["bbox"][0]) * (v["bbox"][3] - v["bbox"][1]))):
                vb = v["bbox"]
                va = abs((vb[2] - vb[0]) * (vb[3] - vb[1]))
                if vp_page_area and va < 0.05 * vp_page_area:
                    continue
                if tried >= 5 or time.time() - t0 > 120:
                    break
                tried += 1
                r2, m2 = detect_rooms(pdf_path, page_index, v["scale"],
                                      tuple(vb), bridge_gaps_m=1.2,
                                      return_meta=True)
                tot2 = sum(x["area_m2"] for x in r2)
                if r2 and (best is None or tot2 > best[0]):
                    best = (tot2, r2, m2, v)
            if best:
                _tot, rooms, rmeta, v = best
                room_den, room_bbox = v["scale"], tuple(v["bbox"])
                out["rooms_viewport"] = {"scale": v["scale"],
                                         "bbox": [round(x, 1) for x in v["bbox"]]}
        rooms_ok = rooms
        areas = sorted((r["area_m2"] for r in rooms), reverse=True)
        out["n_rooms"] = len(areas)
        out["rooms_m2"] = round(sum(areas), 1)
        out["top_rooms"] = [round(a, 1) for a in areas[:5]]
        if rooms and rmeta.get("stage") == "ponte_porta":
            out["rooms_stage"] = rmeta["stage"]           # transparência no log
            out["rooms_bridges"] = rmeta.get("n_bridges")
        # envoltória: ponte proporcional à escala (1,2 m reais). Antes era 12pt
        # fixo — batia com 1,2 m só em 1:100; em 1:50 fechava apenas 0,6 m.
        env_gap_pt = 1.2 / (PT_TO_M * den)
        # 🪤 O piso de 400 m² é arbitrário e estava DESCARTANDO setor real: no
        # projeto de teste o setor "área sem intervenção" tem 380,9 m² e ficava
        # de fora — por isso a envoltória não saía em 5 das 7 pranchas. Agora a
        # busca desce a 150 m² e registramos AS DUAS leituras (a de 400, que é o
        # comportamento atual, e a mais baixa) pra decidir o piso com dado real.
        # Mesmo custo: continua UMA passada. 30/07/2026.
        env = detect_rooms(pdf_path, page_index, den, bbox,
                           min_m2=150, max_m2=5000, bridge_gaps_pt=env_gap_pt)
        _env_areas = sorted((r["area_m2"] for r in env), reverse=True)
        out["envelope_m2"] = round(max((a for a in _env_areas if a >= 400), default=0), 1) or None
        out["envelope_m2_150"] = round(_env_areas[0], 1) if _env_areas else None
        out["envelope_top"] = [round(a, 1) for a in _env_areas[:4]]
    except Exception as e:
        out["err_rooms"] = f"{type(e).__name__}: {e}"[:120]

    # 4) paredes/divisórias (medição por pares de paralelas na sopa) — na
    # MESMA viewport/escala que mediu as salas (numa prancha de detalhe, medir
    # parede da elevação seria ruído)
    try:
        from pdfvec_walls import detect_walls
        w = detect_walls(pdf_path, page_index, room_den, room_bbox)
        walls_ok = w.get("walls", [])
        out["walls_m"] = round(w.get("total_length_m", 0.0), 1)
        out["n_walls"] = len(walls_ok)
    except Exception as e:
        out["err_walls"] = f"{type(e).__name__}: {e}"[:120]

    # 4.5) VALIDAÇÃO POR COTA (pdfvec_cotas): cruza as cotas ESCRITAS na view
    # medida com paredes/arestas de sala MEDIDAS. >= 2 cotas independentes
    # batendo em ±2% => escala validada por duas fontes. É só EVIDÊNCIA — a
    # promoção pra planilha é decisão de outra etapa. Multi-escala (2+
    # viewports com escalas distintas): a validação usa apenas tokens dentro
    # do bbox da view medida, então "escala_validada" vale SÓ pra ela —
    # "cotas_escopo" marca isso no log.
    try:
        from pdfvec_cotas import validate_scale
        cot = validate_scale(pdf_path, page_index, room_den, room_bbox,
                             walls=walls_ok, rooms=rooms_ok)
        out["cotas_encontradas"] = cot["n_cotas"]
        out["cotas_batem"] = cot["n_matches"]
        out["escala_validada"] = bool(cot["validada"])
        if cot["n_matches"]:
            out["cotas_exemplos"] = cot["exemplos"]
        distinct = {room_den, den} | {v.get("scale") for v in alt_viewports}
        if len({s for s in distinct if s}) > 1:
            out["cotas_escopo"] = "view_principal"
    except Exception as e:
        out["err_cotas"] = f"{type(e).__name__}: {e}"[:120]

    # 5) POR LAYER (descoberta 07/07: OCG preserva os layers do CAD no PDF) —
    # parede só do layer de alvenaria/divisória (sem contaminação) + inventário
    # de símbolos (IND-*/LUM-*). Determinístico, sem IA. Coleta pra calibrar.
    try:
        from pdfvec_layers import summarize_layers
        out["layers"] = summarize_layers(pdf_path, page_index, room_den, room_bbox)
    except Exception as e:
        out["err_layers"] = f"{type(e).__name__}: {e}"[:120]

    out["secs"] = round(time.time() - t0, 1)
    return out


def _run(page_units: list, job_id: str, api_key: str, log_fn) -> None:
    # respiro pro fluxo pós-done (email/DB) terminar antes do trabalho pesado
    time.sleep(8)
    deadline = time.time() + BUDGET_S
    results: list[dict] = []
    seen: set[tuple] = set()
    for unit in page_units:
        try:
            pdf_path, filename, _st, page_index = unit[0], unit[1], unit[2], unit[3]
        except Exception:
            continue
        k = (pdf_path, page_index)
        if k in seen:
            continue
        seen.add(k)
        if len(results) >= MAX_PAGES:
            break
        if time.time() > deadline:
            results.append({"file": filename[:60], "page": page_index, "skip": "budget de tempo"})
            break
        try:
            if os.path.getsize(pdf_path) > MAX_FILE_MB * 1024 * 1024:
                results.append({"file": filename[:60], "page": page_index, "skip": "arquivo grande"})
                continue
        except OSError:
            results.append({"file": filename[:60], "page": page_index, "skip": "arquivo sumiu"})
            continue
        try:
            results.append(_measure_page(pdf_path, page_index, api_key))
        except Exception as e:  # nunca derrubar o processo por causa do shadow
            results.append({"file": filename[:60], "page": page_index,
                            "err": f"{type(e).__name__}: {e}"[:120]})

    if not results:
        return
    try:
        # 🪤 A coluna do log corta em 2.000 caracteres. Despejar o dict inteiro
        # (que traz nomes de camada, contagens etc.) fazia justamente os projetos
        # GRANDES — mais páginas, JSON mais longo — serem truncados. E são eles a
        # evidência que interessa: em 30/07 os 3 jobs do cliente Walter, os únicos
        # com CAD do MESMO projeto pra comparar, estavam todos cortados em 2000.
        # Agora grava só o que decide se o leitor vetorial sai da sombra.
        def _resumo(r: dict) -> dict:
            keep = ("file", "page", "scale", "scale_src", "n_rooms",
                    "rooms_m2", "envelope_m2", "envelope_m2_150", "envelope_top",
                    "skip", "err")
            d = {k: r[k] for k in keep if r.get(k) is not None}
            if isinstance(d.get("file"), str):
                d["file"] = d["file"][:34]
            return d

        _tot = 0.0
        for r in results:
            try:
                _tot += float(r.get("rooms_m2") or 0)
            except (TypeError, ValueError):
                pass
        payload = json.dumps({"v": 2, "n": len(results),
                              "rooms_m2_total": round(_tot, 1),
                              "pages": [_resumo(r) for r in results]},
                             ensure_ascii=False)
        log_fn("pdfvec:shadow", payload[:2000], job_id, severity="info")
        print(f"[pdfvec] shadow {job_id}: {len(results)} página(s) medida(s)")
    except Exception as e:
        print(f"[pdfvec] shadow log falhou: {e}")


def shadow_measure_async(page_units: list, job_id: str, api_key: str, log_fn) -> None:
    """Dispara o shadow em thread daemon. page_units = lista de tuplas
    (pdf_path, filename, sheet_type, page_index, ...) do process_job."""
    if os.environ.get("PDFVEC_SHADOW", "1") == "0":
        return
    if not page_units:
        return
    t = threading.Thread(target=_run, args=(list(page_units), job_id, api_key, log_fn),
                         daemon=True, name=f"pdfvec-shadow-{job_id}")
    t.start()
