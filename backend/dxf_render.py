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

# Teto de entidades pro PREVIEW.
#
# Origem (17/07): o DXF do Rômulo (CEM Profa Isabel Castro Viana) com 9.766
# entidades fez o matplotlib acumular 2,4 GB sem completar, e o process_job
# inteiro chegou a 4,3 GB — num servidor de 2 GB, OOM → reinício → job órfão.
# O teto virou 3000 pra proteger o SERVIDOR.
#
# Revisto em 14/08/2026 — o teto estava calibrado contra o inimigo errado.
# Medido pela porta da produção (subprocesso), pico de RSS por psutil:
#
#   entidades | segundos | pico RSS | % do RLIMIT de 1.536 MB
#      3.000  |    3,0   |  131 MB  |   9%    <- teto antigo
#     12.000  |   31,4   |  255 MB  |  17%    <- teto novo
#     20.000  |   31,0   |  362 MB  |  24%
#     40.000  |   66,2   |  627 MB  |  41%    <- só aqui passa dos 60s
#
# Quem aperta é o TEMPO, não a memória: nem 40.000 entidades usam metade do
# RLIMIT_AS de 1,5 GB que o subprocesso ganhou em 22/07. Esse RLIMIT + o
# timeout de 60s já fazem o que o teto de 3000 tentava fazer sozinho em 17/07,
# e fazem melhor — o filho morre sozinho, sem levar o servidor junto.
#
# 12.000 é conservador de propósito: roda em ~31s, metade do timeout, deixando
# 2× de folga. Acima do teto o preview daquela prancha é pulado; acima de
# ~35.000 ele bateria no timeout, seria MATADO e ficaria REGISTRADO — falha
# cosmética, contida e visível.
#
# 🪤 A medição usou geometria SINTÉTICA (linha, texto, círculo, hachura SOLID
# simples). Prancha real com hachura de contorno complexo, bloco aninhado e
# fonte SHX custa mais por entidade — daí a folga de 2×, e daí o teto se apoiar
# no timeout em vez de tentar substituí-lo.
#
# 🪤 Duas medições ANTERIORES desta mesma tabela estavam erradas e foram
# descartadas: uma somava o boot do matplotlib ao tempo do render (4× a mais),
# e a outra media RAM com tracemalloc — que só enxerga alocação do Python e
# ignora os buffers do Agg, que são em C.
MAX_RENDER_ENTITIES = int(os.getenv("MAX_RENDER_ENTITIES", "12000"))


def render_dxf_to_png(
    dxf_path: str,
    output_png_path: str,
    *,
    dpi: int = 110,
    max_layouts: int = 1,
    fig_size_inches: tuple[float, float] = (14, 10),
) -> bool:
    """Renderiza o primeiro layout (ou modelspace) de um DXF para PNG.

    Args:
        dxf_path: caminho do arquivo DXF.
        output_png_path: destino do PNG gerado.
        dpi: resolução em dots por polegada. Baixado de 150→110 em 23/07 pra
            cortar banda: o preview é só enfeite (o arquivo real fica no botão
            "Baixar"), e 110dpi × (14,10) ≈ 1540×1100px segue bem legível, com
            ~46% menos bytes por PNG — economia na subida pro Storage E em cada
            "Ver prancha" (Storage→Render→browser). Ver docs/PESQUISA banda Render.
        max_layouts: quantos layouts renderizar (V1 só o primeiro).
        fig_size_inches: tamanho base da figura matplotlib.

    Returns:
        True se OK; False se falhou.
    """
    if not os.path.exists(dxf_path):
        # 🪤 Este era o ÚNICO return False sem uma palavra. Quem chama via
        # subprocesso lê a saída do filho pra saber o motivo — e aqui ele saía
        # mudo, virando "codigo 1, sem mensagem". Arquivo sumido é justamente a
        # falha que a gente mais viu no preview (todo DWG, até 14/08/2026).
        print(f"[dxf_render] arquivo nao existe: {dxf_path}")
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
        # 🪤 O print de SUCESSO não pode derrubar o sucesso. Ele ficava dentro
        # do try e usava "→": num console que não é UTF-8 (cp1252 do Windows,
        # ou container com locale C) o próprio print levanta UnicodeEncodeError,
        # cai no except lá embaixo e a função devolve False — com o PNG já
        # gravado no disco. Achado em 14/08/2026 testando o teto de entidades:
        # o render de 6.000 entidades "falhou" e o PNG estava lá, 1.830 bytes.
        try:
            print(f"[dxf_render] OK: {os.path.basename(dxf_path)} -> "
                  f"{os.path.basename(output_png_path)} "
                  f"({os.path.getsize(output_png_path)} bytes)")
        except Exception:
            pass
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
                            timeout_s: int = 60,
                            motivo_out: Optional[list] = None) -> bool:
    """Wrapper com timeout REAL: roda o render num SUBPROCESSO.

    `motivo_out`: lista opcional onde este wrapper DEPOSITA o motivo da falha.
    🚨 Por que existe (15/08/2026): o filho já imprime a razão exata — "preview
    PULADO: N entidades", "Erro ao abrir", "Erro ao renderizar: <exceção>" — e
    o `capture_output=True` daqui jogava tudo fora. No 1º DWG do Giovani o
    preview falhou em 10s com `sem_dxf=0` (arquivo presente!) e o log só sabia
    dizer "falhou (nao foi tempo)". A causa existia, escrita, a um passo de ser
    gravada — a mesma falha silenciosa que este arquivo inteiro combate.

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
    # Teto de MEMÓRIA no subprocesso do preview (fix OOM 2026-07-22): um DXF denso
    # faz ezdxf.readfile carregar GBs no filho ANTES do guarda de densidade — sem
    # teto, isso estourava os 4GB do container (OOM no FIM do job, depois da planilha
    # pronta). Com RLIMIT_AS, o filho morre ao passar do teto → o preview daquela
    # prancha falha (cosmético), mas o SERVIDOR nunca cai. Só POSIX (no Render é
    # Linux; local, sem 'resource', segue sem o teto e cai no fallback in-process).
    _preexec = None
    try:
        import resource as _res
        _cap_mb = int(os.environ.get("CAD_PREVIEW_MEM_MB", "1536"))  # 1,5 GB padrão
        _CAP = _cap_mb * 1024 * 1024
        def _cap_mem():
            _res.setrlimit(_res.RLIMIT_AS, (_CAP, _CAP))
        _preexec = _cap_mem
    except Exception:
        _preexec = None
    def _anota(txt):
        if motivo_out is not None:
            motivo_out.append(str(txt)[:300])

    try:
        _kw = dict(cwd=os.path.dirname(os.path.abspath(__file__)),
                   timeout=timeout_s, capture_output=True, text=True,
                   errors="replace")
        if _preexec is not None:
            _kw["preexec_fn"] = _preexec
        proc = subprocess.run(
            [sys.executable, "-c", code, dxf_path, output_png_path], **_kw
        )
        _ok = proc.returncode == 0 and os.path.exists(output_png_path)
        if not _ok:
            # A razão VEM do filho — ele já a imprime. Pega a última linha útil
            # de stdout (onde o dxf_render escreve) ou de stderr (onde vai o
            # traceback quando o filho morre feio, ex.: estourou o RLIMIT).
            _saida = (proc.stdout or "").strip().splitlines()
            _erro = (proc.stderr or "").strip().splitlines()
            _linha = (_saida[-1] if _saida else "") or (_erro[-1] if _erro else "")
            if not _linha:
                # Sem uma palavra do filho: o returncode é o que sobra. Negativo
                # em POSIX = morreu por sinal (-9 é OOM-killer / RLIMIT).
                _linha = (f"filho morreu com sinal {-proc.returncode} "
                          f"(provavel estouro de memoria)" if proc.returncode < 0
                          else f"filho saiu com codigo {proc.returncode}, sem mensagem")
            elif proc.returncode == 0:
                _linha = f"render disse OK mas o PNG nao existe — {_linha}"
            _anota(_linha)
        return _ok
    except subprocess.TimeoutExpired:
        # subprocess.run já matou o filho ao estourar o timeout — memória liberada.
        print(f"[dxf_render] Timeout ({timeout_s}s) em {dxf_path} — subprocesso morto, memória liberada")
        _anota(f"timeout de {timeout_s}s — subprocesso morto")
        return False
    except Exception as e:
        print(f"[dxf_render] subprocesso não lançou ({type(e).__name__}: {e}) — fallback in-process")
        _anota(f"subprocesso nao lancou ({type(e).__name__}) — caiu no fallback in-process")
        return render_dxf_to_png(dxf_path, output_png_path)
