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

# Teto de entidades pro PREVIEW. Medido em 17/07 com o DXF do Rômulo (CEM Profa
# Isabel Castro Viana): 9.766 entidades → o matplotlib acumulou 2,4 GB e nem
# completou (o process_job inteiro chegou a 4,3 GB). Num servidor de 2 GB isso
# sozinho já derruba o processo (OOM → reinício → job órfão). O preview é só
# enfeite (visualizar-prancha), então acima deste teto a gente PULA o render —
# nunca vale arriscar o servidor e o quantitativo inteiro por uma imagem.
# 3000 pega o caso denso com folga e deixa passar prancha de arquitetura normal
# (centenas a ~2 mil entidades).
MAX_RENDER_ENTITIES = 3000


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

        # GUARDA DE COMPLEXIDADE (17/07): desenho denso demais explode o
        # matplotlib (medido: 9.766 entidades → 2,4 GB e sem terminar). Pula o
        # preview antes de gastar memória — o quantitativo não depende dele.
        # Conta SEMPRE o MODELSPACE, não o target_layout: quando o layout é um
        # paperspace, ele tem só um viewport (poucas entidades) que RENDERIZA o
        # modelspace inteiro por baixo — contar o paperspace mediria o peso
        # errado e deixaria o caso denso passar (foi o que aconteceu no 1º teste).
        try:
            _n_ent = len(doc.modelspace())
        except Exception:
            _n_ent = sum(1 for _ in doc.modelspace())
        if _n_ent > MAX_RENDER_ENTITIES:
            print(f"[dxf_render] preview PULADO: {_n_ent} entidades no modelspace "
                  f"> teto {MAX_RENDER_ENTITIES} (desenho denso, evita OOM)")
            return False

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
    """Wrapper com timeout REAL: roda o render num SUBPROCESSO.

    Era via threading (17/07): quando dava timeout, o t.join só parava de
    ESPERAR — a thread do matplotlib continuava viva alocando memória (não dá
    pra matar thread em Python). Num DXF denso isso virava uma thread zumbi
    comendo RAM até o OOM derrubar o servidor inteiro (caso Rômulo).
    Subprocesso é matável: no timeout, kill() libera a memória DE VERDADE, e
    um estouro isola no filho sem levar o processo principal junto.

    Fallback: se não der pra lançar o subprocesso (ambiente restrito), cai pro
    render in-process — a guarda de entidades em render_dxf_to_png já barra o
    caso denso, então o risco residual é baixo.
    """
    import subprocess
    import sys
    code = (
        "import sys;"
        "from dxf_render import render_dxf_to_png;"
        "sys.exit(0 if render_dxf_to_png(sys.argv[1], sys.argv[2]) else 1)"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code, dxf_path, output_png_path],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            timeout=timeout_s,
            capture_output=True,
        )
        return proc.returncode == 0 and os.path.exists(output_png_path)
    except subprocess.TimeoutExpired:
        # subprocess.run já matou o filho ao estourar o timeout — memória liberada.
        print(f"[dxf_render] Timeout ({timeout_s}s) em {dxf_path} — subprocesso morto, memória liberada")
        return False
    except Exception as e:
        print(f"[dxf_render] subprocesso não lançou ({type(e).__name__}: {e}) — fallback in-process")
        return render_dxf_to_png(dxf_path, output_png_path)
