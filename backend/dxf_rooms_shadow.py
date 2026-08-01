# -*- coding: utf-8 -*-
"""SOMBRA: montagem de cômodos a partir da geometria do DXF (30/07/2026).

POR QUE EXISTE
--------------
A área total do projeto sai HOJE unicamente da IA lendo o quadro de áreas da
prancha — não há cálculo geométrico por trás. Medido em 30/07 nos 87 projetos
concluídos: **63% terminam sem área total** (47% dos com CAD, 76% dos só-PDF).

A causa é que o motor de CAD só reconhece ambiente desenhado como POLÍGONO
FECHADO — e quase nenhum desenho é feito assim. Nas 7 pranchas de teste ele
achou de 0 a 61 polígonos, enquanto o leitor vetorial de PDF, que MONTA as
faces a partir dos traços, achou de 26 a 115.

O spike de 30/07 alimentou a mesma montagem de faces com a geometria do DXF:

    prancha        cômodos   soma        vs. total declarado (1.728,4 m²)
    Arquitetura      126     1.712,3 m²      99%
    Piso              92     1.601,8 m²      93%
    Forro            110     1.073,9 m²      62%

Contra 33–43% do caminho do PDF. Faz sentido: no DXF a geometria é exata.

POR QUE É SOMBRA E NÃO MEDIÇÃO
------------------------------
Regra dura nº1. Três motivos, honestos:
  1. É UM projeto, três pranchas. 99% pode ser desenho bem feito, não mérito.
  2. A referência é ambígua: contra a "área de layout" (1.285,9 m²) daria 133%.
     Sem saber qual é a resposta certa, não dá pra cravar número na planilha.
  3. Custo: a prancha de forro tem 5.470 segmentos. Já tivemos 2 estouros de
     memória em julho — carga nova entra medida, nunca no escuro.

Então isto aqui CALCULA e REGISTRA, e não entrega nada ao cliente. Quando
houver evidência de vários projetos reais, vira medição — com prova.

🪤 Desligar: DXFROOMS_SHADOW=0 no Render.
"""

from __future__ import annotations

import json
import os
import threading
import time

# Tetos de segurança — a sombra NUNCA pode atrapalhar o cliente nem o servidor.
BUDGET_S = float(os.environ.get("DXFROOMS_BUDGET_S", "90"))   # tempo total
MAX_FILES = int(os.environ.get("DXFROOMS_MAX_FILES", "4"))    # pranchas por job
MAX_SEGS = int(os.environ.get("DXFROOMS_MAX_SEGS", "40000"))  # desiste acima disso
SNAP_M = 0.01     # 1 cm — cola pontas que quase se encontram
BRIDGE_M = 0.02   # 2 cm — sela resíduo de arredondamento, não vão de porta
MIN_ROOM_M2 = 1.5
MAX_ROOM_M2 = 500.0


def _segmentos(dxf_path: str, fator: float, teto: int) -> list:
    """Extrai segmentos de LINE/LWPOLYLINE já convertidos pra METROS."""
    import ezdxf
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    segs = []
    for e in msp:
        if len(segs) > teto:
            return segs  # o chamador detecta o estouro pelo tamanho
        t = e.dxftype()
        try:
            if t == "LINE":
                a, b = e.dxf.start, e.dxf.end
                segs.append(((a.x * fator, a.y * fator), (b.x * fator, b.y * fator)))
            elif t == "LWPOLYLINE":
                pts = [(p[0] * fator, p[1] * fator) for p in e.get_points("xy")]
                if getattr(e, "closed", False) and len(pts) > 2:
                    pts.append(pts[0])
                for i in range(len(pts) - 1):
                    segs.append((pts[i], pts[i + 1]))
        except Exception:
            continue
    return segs


def _grupos_por_proximidade(faces: list, gap_m: float = 1.0) -> dict:
    """Agrupa faces que se tocam/quase se tocam — cada grupo ≈ uma VISTA da folha.

    Numa prancha de arquitetura convivem planta, cortes, fachadas e detalhes,
    todos no mesmo espaço do DXF. Somar tudo conta o mesmo prédio várias vezes.
    Faces da mesma vista estão coladas; vistas diferentes ficam separadas por
    espaço em branco. Um "buffer + união" revela esses agrupamentos.

    Só MEDE (não filtra nada): devolve quantos grupos existem e o perfil do
    maior. Best-effort — qualquer erro devolve {} e a sombra segue sem isso.
    """
    try:
        from shapely.ops import unary_union
        from shapely.strtree import STRtree
        if not faces or len(faces) > 4000:
            return {}
        uni = unary_union([f.buffer(gap_m) for f in faces])
        comps = list(getattr(uni, "geoms", [uni]))
        if len(comps) <= 1:
            return {"n_grupos": len(comps)}
        tree = STRtree(comps)
        soma = [0.0] * len(comps)
        cont = [0] * len(comps)
        maior = [0.0] * len(comps)
        for f in faces:
            try:
                c = f.representative_point()
                for idx in tree.query(c):
                    if comps[idx].contains(c):
                        soma[idx] += f.area
                        cont[idx] += 1
                        maior[idx] = max(maior[idx], f.area)
                        break
            except Exception:
                continue
        i = max(range(len(comps)), key=lambda k: soma[k])
        return {
            "n_grupos": len(comps),
            "grupo_maior_m2": round(soma[i], 1),
            "grupo_maior_faces": cont[i],
            "grupo_maior_face_max": round(maior[i], 1),
        }
    except Exception:
        return {}


def medir_um(dxf_path: str, fator: float) -> dict:
    """Mede UMA prancha. Best-effort: devolve o que conseguiu, nunca levanta."""
    out = {"file": os.path.basename(dxf_path)[:34]}
    t0 = time.time()
    try:
        segs = _segmentos(dxf_path, fator, MAX_SEGS)
        if len(segs) > MAX_SEGS:
            out["skip"] = f"segmentos demais ({len(segs)})"
            return out
        if len(segs) < 20:
            out["skip"] = "geometria insuficiente"
            return out
        out["n_segs"] = len(segs)

        from shapely.geometry import LineString
        from pdfvec_rooms import _polygonize_faces, _snap_endpoints

        ls = [LineString([a, b]) for a, b in segs if a != b]
        ls = _snap_endpoints(ls, SNAP_M)
        faces, _pontes = _polygonize_faces(ls, BRIDGE_M)
        areas = [f.area for f in faces if MIN_ROOM_M2 <= f.area <= MAX_ROOM_M2]
        areas.sort(reverse=True)
        out["n_faces"] = len(faces)
        out["n_rooms"] = len(areas)
        out["rooms_m2"] = round(sum(areas), 1)
        out["top"] = [round(a, 1) for a in areas[:5]]
        # 🪤 SOMA DE AMBIENTES ≠ ÁREA TOTAL. O caminho do PDF descarta
        # envoltórias de propósito (_middle_layer) pra achar AMBIENTE — por isso
        # soma ~1/3 do pavimento, e isso está certo. A área TOTAL é outra coisa:
        # é a maior face fechada (a envoltória). Registramos as duas pra decidir
        # com dado qual serve pra quê. 🪤 Meu spike de 30/07 somou ambientes +
        # envoltórias e deu "99% do declarado" — número inflado, não medição.
        todas = sorted((f.area for f in faces), reverse=True)
        out["envelope_m2"] = round(todas[0], 1) if todas else None
        out["envelope_top"] = [round(a, 1) for a in todas[:4]]

        # 🚨 VISTAS NA MESMA FOLHA — hipótese a medir (31/07/2026).
        # Primeiro caso real (Rafael): casa de 75,9 m² e a soma dos "cômodos"
        # deu 601 m² — 8× o tamanho. Quase certamente porque a prancha traz
        # planta + cortes + fachadas + detalhes na MESMA folha, e a montagem de
        # faces soma todas as vistas. O caminho do PDF não sofre disso porque
        # restringe ao viewport; no DXF não existe viewport.
        # Aqui só MEDIMOS: agrupamos as faces por proximidade (componentes
        # conectados) e registramos quantos grupos existem e o maior deles. Se
        # a hipótese estiver certa, o maior grupo ≈ a planta, e a área dele deve
        # bater com a área do projeto — muito melhor que a soma de tudo.
        out.update(_grupos_por_proximidade(faces))
    except Exception as e:
        out["err"] = f"{type(e).__name__}: {e}"[:110]
    out["secs"] = round(time.time() - t0, 1)
    return out


def _run(dxf_units: list, job_id: str, log_fn,
         area_declarada: float | None = None) -> None:
    time.sleep(10)  # deixa o pós-done (e-mail/DB) respirar antes do trabalho pesado
    deadline = time.time() + BUDGET_S
    results = []
    for path, fator in dxf_units[:MAX_FILES]:
        if time.time() > deadline:
            results.append({"file": os.path.basename(path)[:34], "skip": "budget"})
            break
        if not os.path.exists(path):
            continue
        results.append(medir_um(path, fator))
    if not results:
        return
    try:
        tot = 0.0
        for r in results:
            try:
                tot += float(r.get("rooms_m2") or 0)
            except (TypeError, ValueError):
                pass
        # Comparação PRONTA no log (01/08/2026). A regra do maior grupo foi
        # descoberta em 31/07 com UM prédio; pra generalizar precisa de vários,
        # e conferir na mão a cada job não escala. Agora cada execução já grava
        # o veredito: maior grupo ÷ área declarada. Basta ler a coluna depois.
        _melhor = 0.0
        for r in results:
            try:
                _melhor = max(_melhor, float(r.get("grupo_maior_m2") or 0))
            except (TypeError, ValueError):
                pass
        _cmp = {}
        if area_declarada and area_declarada > 0:
            _cmp["area_declarada"] = round(float(area_declarada), 1)
            _cmp["maior_grupo_vs_declarada"] = (
                round(_melhor / float(area_declarada), 3) if _melhor else None)
            _cmp["soma_tudo_vs_declarada"] = (
                round(tot / float(area_declarada), 3) if tot else None)
        payload = json.dumps({"v": 2, "n": len(results),
                              "rooms_m2_total": round(tot, 1),
                              "maior_grupo_m2": round(_melhor, 1) or None,
                              **_cmp,
                              "pages": results}, ensure_ascii=False)
        log_fn("dxfrooms:shadow", payload[:2000], job_id, severity="info")
        print(f"[dxfrooms] shadow {job_id}: {len(results)} prancha(s), total {tot:.1f} m²")
    except Exception as e:
        print(f"[dxfrooms] shadow log falhou: {e}")


def shadow_rooms_async(dxf_units: list, job_id: str, log_fn,
                       area_declarada: float | None = None) -> None:
    """Dispara a sombra em thread daemon. dxf_units = [(caminho_dxf, fator_unidade)].

    Nunca levanta e nunca bloqueia — se qualquer coisa der errado, o cliente
    não percebe porque isto não participa do resultado dele.
    """
    if os.environ.get("DXFROOMS_SHADOW", "1") == "0":
        return
    if not dxf_units:
        return
    try:
        threading.Thread(target=_run,
                         args=(dxf_units, job_id, log_fn, area_declarada),
                         daemon=True).start()
    except Exception as e:
        print(f"[dxfrooms] shadow não iniciado: {e}")
