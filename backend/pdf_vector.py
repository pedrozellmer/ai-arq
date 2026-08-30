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

# 🚨 Conserto 3 de 15/08 (feito 30/08): era 3 FIXO e cortava CALADO —
# dois jobs de 43 páginas viraram 3 e o relatório dizia só "medi 3".
# Teto agora é env e o resumo diz "n de m" (o BUDGET_S continua sendo
# o freio de custo real: estourou o tempo, para e REGISTRA).
MAX_PAGES = int(os.environ.get("PDFVEC_MAX_PAGES", "8"))
BUDGET_S = 180.0       # teto de tempo total do shadow por job
MAX_FILE_MB = 12       # PDF maior que isso não é medido (memória)


def _grupos_por_proximidade_pdf(rooms: list, den: float, gap_m: float = 1.0) -> dict:
    """Agrupa cômodos que se tocam — cada grupo ≈ uma VISTA da folha.

    Gêmea de `_grupos_por_proximidade` do dxf_rooms_shadow (31/07/2026), que
    resolveu a área total no DXF: numa prancha convivem planta, cortes,
    fachadas e detalhes, e somar tudo conta o mesmo prédio várias vezes. As
    formas da mesma vista estão coladas; vistas diferentes ficam separadas por
    branco. Buffer + união revela os agrupamentos, e o MAIOR grupo é a planta.

    Aqui a entrada são bboxes de cômodo em PONTOS (detect_rooms), então o gap
    é convertido pra pontos pela escala. Só MEDE — não altera rooms_m2.
    Best-effort: qualquer erro devolve {} e a sombra segue sem isso.
    """
    try:
        from shapely.geometry import box as _box
        from shapely.ops import unary_union
        from shapely.strtree import STRtree
        from pdfvec_rooms import PT_TO_M as _PT_TO_M
        if not rooms or len(rooms) > 4000 or not den:
            return {}
        gap_pt = gap_m / (_PT_TO_M * float(den))
        formas, areas = [], []
        for r in rooms:
            try:
                x0, y0, x1, y1 = r["bbox"]
                formas.append(_box(float(x0), float(y0), float(x1), float(y1)))
                areas.append(float(r["area_m2"]))
            except (KeyError, TypeError, ValueError):
                continue
        if not formas:
            return {}
        uni = unary_union([f.buffer(gap_pt) for f in formas])
        comps = list(getattr(uni, "geoms", [uni]))
        if len(comps) <= 1:
            return {"n_grupos": 1, "grupo_maior_m2": round(sum(areas), 1),
                    "grupo_maior_comodos": len(areas)}
        tree = STRtree(comps)
        soma = [0.0] * len(comps)
        cont = [0] * len(comps)
        for f, a in zip(formas, areas):
            try:
                c = f.representative_point()
                for idx in tree.query(c):
                    if comps[idx].contains(c):
                        soma[idx] += a
                        cont[idx] += 1
                        break
            except Exception:
                continue
        i = max(range(len(comps)), key=lambda k: soma[k])
        return {"n_grupos": len(comps),
                "grupo_maior_m2": round(soma[i], 1),
                "grupo_maior_comodos": cont[i]}
    except Exception:
        return {}


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
        # Maior grupo conectado — mesma regra que resolveu a área total no DXF
        # em 31/07. A soma de TODOS os cômodos conta o prédio várias vezes
        # quando a folha traz planta + cortes + fachadas juntos. Sintoma visto
        # no log: prancha elétrica devolveu 162 "cômodos" e 1.394 m².
        # Aqui só MEDE (segue sombra) — quem decidir promover compara depois.
        _g = _grupos_por_proximidade_pdf(rooms, den)
        if _g:
            out.update(_g)
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
        # 🚨 Sair calado aqui é indistinguível de "a sombra nem rodou". Medido
        # em 12/08 no job do Guilherme (428d2688, 3 PDFs): ZERO evento pdfvec no
        # banco, e não dava pra saber qual das seis saídas mudas tinha disparado.
        # PDF é o caminho mais cego que temos — 38 envios, 27 sem medir nada.
        try:
            log_fn("pdfvec:shadow", json.dumps(
                {"v": 2, "n": 0, "skip": "nenhuma página processada",
                 "recebidas": len(page_units)}, ensure_ascii=False),
                job_id, severity="info")
        except Exception:
            pass
        return
    try:
        # 🪤 A coluna do log corta em 2.000 caracteres. Despejar o dict inteiro
        # (que traz nomes de camada, contagens etc.) fazia justamente os projetos
        # GRANDES — mais páginas, JSON mais longo — serem truncados. E são eles a
        # evidência que interessa: em 30/07 os 3 jobs do cliente Walter, os únicos
        # com CAD do MESMO projeto pra comparar, estavam todos cortados em 2000.
        # Agora grava só o que decide se o leitor vetorial sai da sombra.
        def _resumo(r: dict) -> dict:
            # 🚨 Conserto 2 de 15/08 (feito 30/08): `cotas_derivacao` era
            # CALCULADO e jogado fora aqui — a 3ª fonte falhou 40 vezes e
            # ninguém soube por quê. Keep-list que descarta evidência é o
            # mesmo vício da keep-list de `meta` da auditoria de 27/08.
            keep = ("file", "page", "scale", "scale_src", "n_rooms",
                    "rooms_m2", "n_grupos", "grupo_maior_m2", "grupo_maior_comodos",
                    "envelope_m2", "envelope_m2_150", "envelope_top",
                    "cotas_derivacao", "err_cotas_derive", "err_cotas",
                    "scale_derivada_por_cota", "skip", "err")
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
        _unicas = len({(x[0], x[3]) for x in page_units if len(x) > 3})
        payload = json.dumps({"v": 2, "n": len(results), "de": _unicas,
                              "rooms_m2_total": round(_tot, 1),
                              "pages": [_resumo(r) for r in results]},
                             ensure_ascii=False)
        log_fn("pdfvec:shadow", payload[:2000], job_id, severity="info")
        print(f"[pdfvec] shadow {job_id}: {len(results)} de {_unicas} página(s) medida(s)")
    except Exception as e:
        print(f"[pdfvec] shadow log falhou: {e}")


def shadow_measure_async(page_units: list, job_id: str, api_key: str, log_fn) -> None:
    """Dispara o shadow em thread daemon. page_units = lista de tuplas
    (pdf_path, filename, sheet_type, page_index, ...) do process_job."""
    # 🪤 As duas saídas abaixo eram MUDAS. "Desligado por env" e "sem páginas"
    # são diagnósticos OPOSTOS e viravam a mesma ausência no banco — o mesmo
    # vício que fez o preview de prancha ficar 100% quebrado por meses sem
    # ninguém notar. Agora cada uma diz seu nome.
    def _av(motivo, extra=None):
        try:
            log_fn("pdfvec:shadow", json.dumps(
                {"v": 2, "n": 0, "skip": motivo, **(extra or {})},
                ensure_ascii=False), job_id, severity="info")
        except Exception:
            pass

    if os.environ.get("PDFVEC_SHADOW", "1") == "0":
        _av("desligado por PDFVEC_SHADOW=0")
        return
    if not page_units:
        _av("nenhuma página de PDF chegou ao shadow")
        return
    # 🚨 A SÉTIMA SAÍDA MUDA (12/08/2026). Instrumentei seis e o caminho AINDA
    # ficou calado no job do Hospital 2 de julho (70556e26, 1 PDF): nenhum
    # evento pdfvec, com o código já no ar desde as 09:40 (conferido no stage
    # `boot`, v 044eee9e).
    # Motivo: os seis avisos moram DENTRO da thread — e ela é daemon, dorme 8s
    # antes de começar e trabalha por minutos. Se o processo reinicia nesse
    # meio (o Render reinicia sozinho), ela morre sem executar UMA linha de
    # registro, e "não disparou" fica idêntico a "disparou e não achou".
    # Este log sai ANTES, no fluxo síncrono do job: se ele existe e o resultado
    # não, a thread morreu no caminho — que é uma resposta, não um silêncio.
    try:
        log_fn("pdfvec:shadow", json.dumps(
            {"v": 2, "fase": "disparado", "paginas": len(page_units)},
            ensure_ascii=False), job_id, severity="info")
    except Exception:
        pass
    try:
        t = threading.Thread(target=_run, args=(list(page_units), job_id, api_key, log_fn),
                             daemon=True, name=f"pdfvec-shadow-{job_id}")
        t.start()
    except Exception as e:
        _av(f"thread não iniciou: {type(e).__name__}: {e}"[:120])
