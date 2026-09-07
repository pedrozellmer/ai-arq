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
exatamente o mesmo. É o erro do caso cliente-52 (29/07, reenviou 2× e desistiu),
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

import pytest

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


def _valor_plausivel(nome):
    """Um valor de mentira, com o TIPO que o produtor espera.

    Só existe pra deixar a f-string do produtor renderizar — nenhum teste aqui
    olha o número, e sim a REDAÇÃO que sai."""
    if nome.startswith("_bn") or "nome" in nome or "path" in nome:
        return "PRANCHA_A0.dxf"
    if "tam" in nome or "bytes" in nome:
        return 412 * 1048576
    return 412.0


def _mensagens_REAIS_de_prancha_grande():
    """As frases que o main.py de verdade produz ao recusar prancha por TAMANHO.

    🩸 A LACUNA QUE ISTO FECHA. A versão anterior alimentava o consumidor com um
    literal escrito à mão dentro do próprio teste. São **três** produtores dessa
    frase no `process_job`, e o acoplamento entre eles e o filtro do aviso
    (`"grande demais pro nosso limite de memória" in str(e)`) estava protegido
    só por um comentário "não mudar". Mexer na redação de qualquer um dos três —
    o tipo de mexida que se faz sem medo em copy — reabria o defeito pra todo
    cliente com prancha recusada por tamanho, com o guarda VERDE.

    🔑 Por isso os produtores são achados por um marcador DIFERENTE do que o
    filtro usa: aqui basta a frase dizer "grande demais". Se alguém reescrever o
    resto ("...pro nosso limite de memória"), o produtor continua sendo achado
    por este guarda e o consumidor deixa de reconhecê-lo — que é exatamente a
    regressão a pegar.
    """
    import ast
    fn = [n for n in ast.walk(ast.parse(_FONTE))
          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
          and n.name == "process_job"]
    assert len(fn) == 1, "process_job sumiu ou virou duas definições"
    achadas = []
    for n in ast.walk(fn[0]):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "append" and len(n.args) == 1):
            continue
        alvo = n.func.value
        if not (isinstance(alvo, ast.Name)
                and alvo.id in ("_dxf_grandes_msgs", "dxf_errors")):
            continue
        if not isinstance(n.args[0], (ast.JoinedStr, ast.Constant)):
            continue
        expr = ast.Expression(n.args[0])
        ast.fix_missing_locations(expr)
        ns = {"int": int, "os": os, "len": len, "abs": abs, "round": round}
        for m in ast.walk(n.args[0]):
            if isinstance(m, ast.Name) and m.id not in ns:
                ns[m.id] = _valor_plausivel(m.id)
        texto = eval(compile(expr, "produtor-main.py", "eval"), ns)
        if "grande demais" in texto:
            achadas.append((n.lineno, texto))
    assert len(achadas) >= 3, (
        "esperava os TRÊS produtores da recusa por tamanho no process_job "
        "(DWG grande antes de converter, DXF grande depois de converter, DXF "
        "grande na leitura), achei %d: %s. Se um sumiu, o guarda passou a "
        "cobrir menos do que diz." % (achadas, [l for l, _ in achadas]))
    return achadas


_PRODUTORES = _mensagens_REAIS_de_prancha_grande()

_SOLUCO = "PRANCHA_B.pdf: a IA não respondeu essa prancha"


@pytest.mark.parametrize("linha,msg", _PRODUTORES,
                         ids=[str(l) for l, _ in _PRODUTORES])
def test_prancha_grande_demais_NAO_recebe_conselho_de_reprocessar(linha, msg):
    """🩸 Caso cliente-52 pela outra porta: reprocessar prancha recusada por
    TAMANHO dá exatamente o mesmo. O guarda antigo procurava a palavra no fonte
    do bloco — apagar o filtro (`if False and "grande demais…" in str(e)`)
    deixava a palavra lá (ela mora na própria linha do filtro) e o cliente
    voltava a ler 'Reprocessar é grátis e pode completar'.

    🔑 E a entrada não é mais uma cópia da frase escrita aqui: é a frase que o
    produtor do main.py monta, avaliada dele mesmo. O id do caso é a linha.
    """
    (aviso,) = _conselho(dxf_errors=[msg])
    assert "PURGE" in aviso, (
        "a prancha recusada por tamanho em main.py:%d não recebeu o conselho "
        "que de fato resolve. Produtor: %r → aviso: %r" % (linha, msg, aviso))
    assert "Reprocessar não resolve" in aviso, (
        "main.py:%d → %r" % (linha, aviso))
    assert "Reprocessar é grátis" not in aviso, (
        "o cliente de prancha grande demais (main.py:%d) recebeu o conselho "
        "FALSO: %r" % (linha, aviso))


@pytest.mark.parametrize("linha,msg", _PRODUTORES,
                         ids=[str(l) for l, _ in _PRODUTORES])
def test_prancha_grande_JUNTO_com_soluco_recebe_os_DOIS_conselhos(linha, msg):
    """A prancha grande quase nunca vem sozinha: no mesmo envio tem a que a IA
    não respondeu, e essa SIM se resolve reprocessando. Um motivo não pode
    apagar o outro."""
    (aviso,) = _conselho(dxf_errors=[msg, _SOLUCO])
    assert "PURGE" in aviso, (
        "com uma prancha grande (main.py:%d) e uma de soluço juntas, sumiu o "
        "conselho de PURGE: %r" % (linha, aviso))
    assert "reprocessar (grátis) pode completar" in aviso, (
        "sumiu o conselho de reprocessar, que é o certo pra prancha de soluço: "
        "%r" % aviso)
    assert "2 prancha(s)" in aviso, (
        "a conta de pranchas que não entraram saiu errada: %r" % aviso)


def test_CONTROLE_prancha_de_SOLUCO_sozinha_manda_reprocessar():
    """🧪 O outro lado. Sem este controle, um consumidor que gritasse PURGE pra
    tudo passaria nos dois testes acima — e o cliente cuja prancha só teve
    soluço da IA deixaria de saber que reprocessar resolve, de graça."""
    (aviso,) = _conselho(dxf_errors=[_SOLUCO])
    assert "Reprocessar é grátis e pode completar" in aviso, (
        "prancha de soluço perdeu o conselho certo: %r" % aviso)
    assert "PURGE" not in aviso, (
        "prancha de soluço recebeu conselho de prancha grande: %r" % aviso)
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
    """Caso cliente-52 (29/07): reprocessar DWG que não converte falha igual."""
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
