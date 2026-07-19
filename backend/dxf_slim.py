# -*- coding: utf-8 -*-
"""Emagrecimento STREAMING de DXF gigante (19/07).

Problema: DWG leve explode em DXF gigante na conversão ODA
(ver caso escola 17/07 — OOM no Render 2GB), e `ezdxf.readfile`
carrega o arquivo INTEIRO na RAM. A defesa era recusar acima de 150 MB.

Solução: acima de um teto de leitura segura, um passe com
`ezdxf.addons.iterdxf` — que lê entidade por entidade, memória O(1) —
copia pra um DXF enxuto SÓ o que o motor mede/lê:

  mantém: LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, ELLIPSE, HATCH,
          TEXT, MTEXT, INSERT, DIMENSION, POINT, SOLID, ATTRIB
  descarta: 3DSOLID, MESH, IMAGE, WIPEOUT, ACAD_PROXY_ENTITY, SPLINE,
            REGION, BODY e afins — lastro que não vira quantitativo.

O header/tables/blocks são copiados como estão (o iterdxf preserva a
estrutura), então INSERTs continuam resolvendo. Se o resultado ainda for
grande demais, o guard de 150 MB do dwg_extractor continua valendo como
backstop — recusa com mensagem clara em vez de derrubar o servidor.
"""
import os
from typing import Optional

# Acima disso o readfile começa a ser arriscado no Render 2GB (o DXF em RAM
# vira ~5-10× o tamanho em disco, e ainda tem o resto do job).
LIMIAR_SLIM_MB = 60

# Tipos que alimentam medição (paredes/áreas/contagens) ou leitura (textos).
_KEEP = {
    "LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE",
    "HATCH", "TEXT", "MTEXT", "INSERT", "DIMENSION", "POINT",
    "SOLID", "ATTRIB",
}


def emagrecer_dxf_se_preciso(path: str, limiar_mb: int = LIMIAR_SLIM_MB) -> Optional[str]:
    """Se o DXF passa do limiar, gera `<nome>.slim.dxf` só com o que o motor
    usa e devolve o caminho novo. Devolve None quando: arquivo já é pequeno,
    o emagrecimento não rendeu (>95% do original) ou qualquer erro — nesses
    casos o chamador segue com o original (comportamento antigo).
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size <= limiar_mb * 1024 * 1024:
        return None

    out = os.path.splitext(path)[0] + ".slim.dxf"
    mantidas = descartadas = 0
    try:
        from ezdxf.addons import iterdxf
        doc = iterdxf.opendxf(path)
        try:
            exporter = doc.export(out)
            try:
                for e in doc.modelspace():
                    if e.dxftype() in _KEEP:
                        exporter.write(e)
                        mantidas += 1
                    else:
                        descartadas += 1
            finally:
                exporter.close()
        finally:
            doc.close()
    except Exception as exc:
        print(f"[dxf-slim] {os.path.basename(path)}: emagrecimento falhou "
              f"({type(exc).__name__}: {exc}) — segue com o original")
        try:
            if os.path.exists(out):
                os.remove(out)
        except OSError:
            pass
        return None

    try:
        novo = os.path.getsize(out)
    except OSError:
        return None
    print(f"[dxf-slim] {os.path.basename(path)}: {size // 1048576} MB → "
          f"{novo // 1048576} MB ({mantidas} entidades mantidas, "
          f"{descartadas} descartadas)")
    if novo >= size * 0.95:
        # não rendeu — evita duplicar disco à toa
        try:
            os.remove(out)
        except OSError:
            pass
        return None
    return out
