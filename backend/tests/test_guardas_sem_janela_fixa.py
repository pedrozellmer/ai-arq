# -*- coding: utf-8 -*-
"""Guarda dos guardas: nenhum teste pode recortar funcao por TAMANHO FIXO.

🚨 25/08/2026. A auditoria do dia achou 11 testes com `src[i:i + N]`; medindo de
verdade, sao 17 com a janela ERRADA. Duas formas de errar, as duas produzindo
VERDE FALSO:

  • janela MAIOR que a funcao -> le o codigo VIZINHO e passa por causa do texto
    dele. Foi assim que eu apaguei o aviso de falha da rede da REGRA DURA Nº1 e
    o guarda continuou verde: estava lendo o `warnings` do bloco seguinte.
  • janela MENOR -> mede um pedaco e nao ve o que diz guardar.

No MESMO dia eu errei essa janela tres vezes seguidas. Nao e descuido pontual: e
o recorte a mao sendo a ferramenta errada. `tests/_corpo.py` faz isso uma vez,
achando o fim REAL da funcao (a proxima definicao na coluna zero).

Este arquivo impede que a pratica volte.
"""
import io
import os
import re

_TESTES = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_TESTES)

# 🚨 So e defeito quando a janela recorta uma FUNCAO. Olhar o entorno de uma
# ancora ("acha este onclick e le 300 chars ao redor") e legitimo e continua
# permitido — o guarda que nao separa os dois vira ruido e acaba desligado.
_RX_ANCORA_DEF = re.compile(
    r"index\(\s*[\"']((?:async )?def \w+)[\"']\s*\)[\s\S]{0,200}?\[\s*i\s*:\s*i\s*\+\s*\d+\s*\]")

# Arquivos que podem usar janela fixa por um motivo que NAO e recortar funcao
# (ex.: olhar o contexto ao redor de uma ocorrencia). Cada um com o porque.
_PERMITIDOS = {
    # olha o entorno de um onclick no HTML, nao uma funcao Python
    "test_botoes_reprocessar.py": "recorta trecho de HTML ao redor de um onclick",
    "test_tailwind_classes_vivas.py": "recorta o entorno de um onclick no HTML",
    "test_planilha_especificacao.py": "recorta trecho de spreadsheet.py por ancora",
    "test_planilha_origem_medicao.py": "recorta trecho de spreadsheet.py por ancora",
    "test_guardas_sem_janela_fixa.py": "e este arquivo",
}


def _arquivos():
    for f in sorted(os.listdir(_TESTES)):
        if f.startswith("test_") and f.endswith(".py"):
            yield f


def test_o_extrator_compartilhado_existe():
    assert os.path.exists(os.path.join(_TESTES, "_corpo.py"))
    from _corpo import corpo_de, so_o_que_roda          # noqa: F401


def test_o_extrator_acha_o_FIM_real_da_funcao():
    """Controle positivo: o corpo tem que parar antes da proxima definicao."""
    import sys
    sys.path.insert(0, _TESTES)
    from _corpo import corpo_de
    c = corpo_de("_hoje_br")
    assert "def _hoje_br(" in c
    assert "def _agora_br_fn(" not in c, "vazou pra funcao anterior"
    assert c.count(chr(10) + "def ") == 0, "vazou pra funcao seguinte"


def test_o_extrator_reclama_de_funcao_inexistente():
    """Guarda que aponta pra funcao que sumiu tem que FALHAR, nao passar."""
    import sys
    sys.path.insert(0, _TESTES)
    from _corpo import corpo_de
    try:
        corpo_de("_funcao_que_nao_existe_batatafrita")
    except AssertionError:
        return
    raise AssertionError("o extrator aceitou funcao inexistente")


def test_nenhum_guarda_novo_recorta_por_tamanho_fixo():
    """🚨 O guarda de verdade. Recortar FUNCAO por N caracteres mede o vizinho
    ou um pedaco — nos dois casos, verde falso.

    🪤 A 1a versao deste guarda acusava QUALQUER `src[i:i+N]`, inclusive o
    recorte legitimo em torno de uma ancora. Guarda que nao separa os dois vira
    ruido, e ruido acaba desligado."""
    ruins = []
    for f in _arquivos():
        if f in _PERMITIDOS:
            continue
        src = io.open(os.path.join(_TESTES, f), encoding="utf-8").read()
        n = len(_RX_ANCORA_DEF.findall(src))
        if n:
            ruins.append("%s (%dx)" % (f, n))
    assert not ruins, (
        "estes guardas recortam funcao por tamanho fixo: %s.\n"
        "Use `from _corpo import corpo_de` — ele acha o fim REAL da funcao. "
        "Janela fixa maior que a funcao le o vizinho e passa verde por engano; "
        "menor, nao ve o que diz guardar." % ruins)


def test_a_lista_de_excecoes_nao_incha():
    """Se a lista virar o arquivo inteiro, o guarda deixou de guardar."""
    assert len(_PERMITIDOS) <= 6
    for f in _PERMITIDOS:
        if f == "test_guardas_sem_janela_fixa.py":
            continue
        assert os.path.exists(os.path.join(_TESTES, f)), (
            "%s esta na lista de excecoes e nao existe mais" % f)


def test_o_extrator_acha_funcao_ANINHADA():
    """🪤 A 1a versao do extrator so achava definicao na coluna ZERO, e dois
    guardas quebraram na conversao: `_peso_aviso` mora dentro do montador de
    e-mail, com 8 espacos de indentacao.

    E o mais revelador: antes da conversao esses dois PASSAVAM — a janela fixa
    de 700 chars lia a funcao de FORA e dava verde. Eram exatamente o defeito
    que este arquivo existe pra impedir."""
    import sys
    sys.path.insert(0, _TESTES)
    from _corpo import corpo_de
    c = corpo_de("_peso_aviso")
    assert "def _peso_aviso" in c
    assert "return 0" in c and "return 9" in c
    assert "_avisos.sort" not in c, "vazou pro codigo que CHAMA a funcao"


def test_o_extrator_para_na_dedentacao():
    """Controle: o corpo termina na 1a linha com indentacao <= a do def."""
    import sys
    sys.path.insert(0, _TESTES)
    from _corpo import corpo_de
    c = corpo_de("_hoje_br")
    assert c.rstrip().endswith("return _agora_br_fn().date()"), c[-120:]
