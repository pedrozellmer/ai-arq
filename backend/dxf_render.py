# -*- coding: utf-8 -*-
"""Render de DXF/DWG para PNG.

Fluxo:
  DWG → DXF (via ODA File Converter, já existente em dwg_extractor.py)
       → PNG (via ezdxf.addons.drawing + matplotlib) — ESTE módulo.

Uso do PNG:
- Preview de prancha na revisão inline (visualizar-prancha.html detecta
  extensão e renderiza <img> ao invés de <iframe>).
- Thumbnail opcional futuro.

Limitações conhecidas:
- DXFs com hachuras SOLID muito grandes podem demorar (>10s). Timeout de
  60s abaixo.
- SHX fonts do AutoCAD não são 100% compatíveis; texto pode ser renderizado
  com fallback. Pra preview é aceitável.
- Cores usam o ACI (AutoCAD Color Index) mapeado por ezdxf default.
"""
import os
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # backend sem GUI (Render server)
import matplotlib.pyplot as plt

import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend


def render_dxf_to_png(
    dxf_path: str,
    output_png_path: str,
    *,
    dpi: int = 150,
    max_layouts: int = 1,
    fig_size_inches: tuple[float, float] = (14, 10),
) -> bool:
    """Renderiza o primeiro layout (ou modelspace) de um DXF para PNG.

    Args:
        dxf_path: caminho do arquivo DXF.
        output_png_path: destino do PNG gerado.
        dpi: resolução em dots por polegada (150 = bom equilíbrio tamanho×nitidez).
        max_layouts: quantos layouts renderizar (V1 só o primeiro).
        fig_size_inches: tamanho base da figura matplotlib.

    Returns:
        True se OK; False se falhou.
    """
    if not os.path.exists(dxf_path):
        return False

    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        print(f"[dxf_render] Erro ao abrir {dxf_path}: {e}")
        return False

    # Tenta renderizar layouts. Se não houver layouts paper, usa modelspace.
    try:
        # Pega o paperspace com conteúdo ou cai pro modelspace
        layouts = list(doc.layouts)
        target_layout = None

        # Prioridade: primeiro paperspace com entidades, senão modelspace
        for lo in layouts:
            if lo.name.lower() == "model":
                continue
            try:
                count = len(list(lo))
                if count > 0:
                    target_layout = lo
                    break
            except Exception:
                continue

        if target_layout is None:
            target_layout = doc.modelspace()

        # Setup figure
        fig, ax = plt.subplots(figsize=fig_size_inches)
        ax.set_axis_off()
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        # Render com ezdxf
        ctx = RenderContext(doc)
        out_backend = MatplotlibBackend(ax)
        Frontend(ctx, out_backend).draw_layout(target_layout, finalize=True)

        # Salvar PNG
        os.makedirs(os.path.dirname(output_png_path), exist_ok=True)
        fig.savefig(output_png_path, dpi=dpi, bbox_inches="tight",
                    pad_inches=0.2, facecolor="white")
        plt.close(fig)
        print(f"[dxf_render] OK: {os.path.basename(dxf_path)} → "
              f"{os.path.basename(output_png_path)} ({os.path.getsize(output_png_path)} bytes)")
        return True

    except Exception as e:
        print(f"[dxf_render] Erro ao renderizar {dxf_path}: "
              f"{type(e).__name__}: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return False


def render_dxf_to_png_safe(dxf_path: str, output_png_path: str,
                            timeout_s: int = 60) -> bool:
    """Wrapper com timeout pra evitar travar em DXFs monstros.

    Usa threading porque signal.alarm não funciona em Windows nem em threads
    não-main (backend rodando em ThreadPoolExecutor).
    """
    import threading
    result = {"ok": False}

    def _target():
        result["ok"] = render_dxf_to_png(dxf_path, output_png_path)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_s)

    if t.is_alive():
        print(f"[dxf_render] Timeout ({timeout_s}s) em {dxf_path}")
        return False
    return result["ok"]
