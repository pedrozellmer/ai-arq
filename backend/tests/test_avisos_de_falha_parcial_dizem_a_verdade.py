# -*- coding: utf-8 -*-
"""Falha PARCIAL: o conselho tem que seguir o MOTIVO de cada prancha.

🩸 03/09/2026, achado pela revisão adversarial. Quando só ALGUMAS pranchas
caem, o cliente lê um aviso montado em `partial_failure` — e essa era **a única
tela que os quatro consertos de copy do dia não alcançavam**.

Prancha recusada por TAMANHO entra em `dxf_errors`, nunca em `dwg_failed` (é o
próprio comentário do ramo de recusa que garante isso). Então `_dwg_sem_irmao`
ficava vazio e o cliente caía no `else`:

    "Reprocessar é grátis e pode completar."

Para uma prancha recusada por tamanho isso é **falso** — reprocessar dá
exatamente o mesmo. É o erro do caso Thalison (29/07, reenviou 2× e desistiu),
entrando pela outra porta.

🔑 O conselho agora é montado por MOTIVO: tamanho pede PURGE, DWG que não abre
pede DXF, e o resto — que pode ter sido soluço da IA — pede reprocessar.

═══════════════════════════════════════════════════════════════════════════

E o teto do emagrecedor (`dxf_slim._LIMITE_DURO`) dizia "espelha
_MAX_DXF_BYTES" e estava **100 MB defasado**: 150 contra 250, desde 26/08. Um
DXF de 400 MB cujo filtro textual entregaria 200 MB não era resgatado
(200 > 150), embora 200 MB passe folgado pelo teto real de 250 MB.
Comentário que promete espelhar e não espelha é pior que número solto: desliga
a suspeita de quem lê.
"""
import io
import os
import sys
import textwrap
import types

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dwg_extractor                                       # noqa: E402
import dxf_slim                                            # noqa: E402

from _corpo import fonte                                   # noqa: E402
import main                                                # noqa: E402

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

_GATILHO = "grande demais pro nosso limite de memória"


def _bloco_do_aviso():
    """O trecho real que monta o conselho da falha parcial."""
    i = _FONTE.index("        if partial_failure:")
    j = _FONTE.index("_aviso_cob = (", i)
    return _FONTE[i:j]


_INI_IRMAO = "        def _stem_norm(p):"
_FIM_IRMAO = "        _pdf_stems = {_stem_norm(p) for p in (pdf_paths or [])}"
_INI_CONSELHO = "        _dwg_com_irmao = [n for n in (dwg_failed or []) if _stem_norm(n) in _pdf_stems]"
_FIM_CONSELHO = "            project_data.warnings = (getattr(project_data, 'warnings', None) or []) + [_aviso_cob]"


def _trecho(inicio, fim, arquivo="main.py"):
    """O trecho REAL de produção, do `inicio` até o fim do `fim`, pronto pra rodar.

    🪤 Recorte por ÂNCORA e não por número de linha: a linha muda a cada commit,
    a âncora só muda quando o código muda. E as duas âncoras têm que ser únicas —
    senão o teste roda um pedaço que ninguém escolheu.
    """
    src = fonte(arquivo)
    assert src.count(inicio) == 1, "âncora de início não é única: %r" % inicio[:60]
    a = src.index(inicio)
    assert src.count(fim, a) >= 1, "âncora de fim não achada: %r" % fim[:60]
    return textwrap.dedent(src[a:src.index(fim, a) + len(fim)])


def _conselho(sheet_errors=(), dxf_errors=(), dwg_failed=(), pdf_paths=()):
    """RODA o código de produção que monta o aviso de falha parcial e devolve
    os avisos que o cliente leria — inclusive o `_stem_norm`/`_pdf_stems` de
    verdade, que é onde mora a regra do 'DWG com irmão em PDF'."""
    pd = types.SimpleNamespace(warnings=[])
    ns = {"os": os, "sheet_errors": list(sheet_errors), "dxf_errors": list(dxf_errors),
          "dwg_failed": list(dwg_failed), "pdf_paths": list(pdf_paths),
          "_nome_prancha_bonito": main._nome_prancha_bonito, "project_data": pd}
    codigo = _trecho(_INI_IRMAO, _FIM_IRMAO) + "\n" + _trecho(_INI_CONSELHO, _FIM_CONSELHO)
    exec(compile(codigo, "conselho-parcial", "exec"), ns)
    return pd.warnings


_GRANDE = ("PRANCHA_A0.dxf: esse desenho é grande demais pro nosso limite de "
           "memória (412 MB)")
_SOLUCO = "PRANCHA_B.pdf: a IA não respondeu essa prancha"


def test_prancha_grande_demais_NAO_recebe_conselho_de_reprocessar():
    """🩸 Caso Thalison pela outra porta: reprocessar prancha recusada por
    TAMANHO dá exatamente o mesmo. O guarda antigo procurava a palavra no fonte
    do bloco — apagar o filtro (`if False and "grande demais…" in str(e)`)
    deixava a palavra lá (ela mora na própria linha do filtro) e o cliente
    voltava a ler 'Reprocessar é grátis e pode completar'."""
    (aviso,) = _conselho(dxf_errors=[_GRANDE])
    assert "PURGE" in aviso, "sumiu o conselho que de fato resolve prancha grande: %r" % aviso
    assert "Reprocessar não resolve" in aviso
    assert "Reprocessar é grátis" not in aviso, (
        "o cliente de prancha grande demais recebeu o conselho FALSO: %r" % aviso)


def test_CONTROLE_o_conselho_de_reprocessar_continua_existindo():
    """Tirar o falso não pode virar 'nunca sugere reprocessar'.

    Falha de prancha pode ter sido soluço da IA, e aí reprocessar É o certo —
    e é grátis.
    """
    bloco = _bloco_do_aviso()
    assert "reprocessar (grátis) pode completar" in bloco or \
           "Reprocessar é grátis e pode completar" in bloco, (
        "sumiu a sugestão de reprocessar, que é certa pras falhas passageiras")


def test_o_conselho_de_DWG_que_nao_abre_continua_de_pe():
    """Caso Thalison (29/07): reprocessar DWG que não converte falha igual."""
    bloco = _bloco_do_aviso()
    assert "salve como DXF" in bloco, (
        "sumiu o conselho pro DWG que não abre — aqui DXF é a saída certa")


def test_os_tres_motivos_sao_distinguidos():
    """Cada motivo tem receita própria; misturar volta a mentir pra alguém."""
    bloco = _bloco_do_aviso()
    for marca in ("_grandes", "_dwg_sem_irmao", "_outras"):
        assert marca in bloco, (
            "o aviso parou de separar o motivo %r — o conselho volta a ser um "
            "só pra falhas diferentes" % marca)


def test_o_teto_do_emagrecedor_espelha_o_do_extrator():
    """🪤 Ele PROMETE espelhar no comentário. Agora o teste cobra a promessa.

    Ficou 100 MB defasado por 8 dias (150 contra 250, desde 26/08) e recusava
    resgate que passaria folgado no teto real.
    """
    assert dxf_slim._LIMITE_DURO == dwg_extractor._MAX_DXF_BYTES, (
        "dxf_slim._LIMITE_DURO (%d MB) e dwg_extractor._MAX_DXF_BYTES (%d MB) "
        "divergiram — o emagrecedor vai recusar resgate que o extrator aceita"
        % (dxf_slim._LIMITE_DURO // 1048576,
           dwg_extractor._MAX_DXF_BYTES // 1048576))


def test_CONTROLE_o_valor_ANTIGO_reprovaria_neste_teste():
    """Sem isto, o teste acima poderia estar comparando duas coisas iguais por
    acaso e não por acordo."""
    antigo = 150 * 1024 * 1024
    assert antigo != dwg_extractor._MAX_DXF_BYTES, (
        "o controle está errado: o valor antigo (150 MB) tem que DIVERGIR do "
        "teto real, senão este teste nunca teria pegado a defasagem")


def test_o_emagrecedor_segue_LEVE():
    """🪤 Ele roda dentro do worker; importar o extrator custa segundos/prancha.

    Foi por isso que a igualdade virou teste em vez de import.
    """
    fonte = io.open(os.path.join(_BACKEND, "dxf_slim.py"), encoding="utf-8").read()
    topo = fonte[:fonte.index("_LIMITE_DURO")]
    assert "import dwg_extractor" not in topo and "from dwg_extractor" not in topo, (
        "dxf_slim passou a importar o extrator no topo — isso pesa em cada "
        "prancha do worker; a igualdade dos tetos é travada por teste")
