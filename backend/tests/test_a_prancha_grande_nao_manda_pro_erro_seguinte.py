# -*- coding: utf-8 -*-
"""A recusa por TAMANHO não pode mandar o cliente pra uma SEGUNDA falha.

🩸 03/09/2026, RAFAEL LIMA (job 28f140ef). Primeiro projeto dele, vindo do
canal novo (ChatGPT). O DWG de 11,68 MB virou 376 MB de DXF e a gente recusou
— recusa CERTA: o teto do processo filho é 2,5 GB e a extração pediria ~3,6 GB.
O defeito não foi recusar. Foi o que a recusa MANDOU ele fazer:

  (1) "suba em DXF em vez de DWG — a conversão do DWG é o que multiplica o
      tamanho". DXF é TEXTO e DWG é binário comprimido. O DXF que ele
      exportasse teria os mesmos ~376 MB: era mandar pra falhar de novo, com
      a nossa assinatura embaixo.
  (2) "mande uma prancha por vez" — ele mandou UMA (files_count = 1).

🔑 Conselho que não serve pro caso é PIOR que conselho nenhum: parece ajuda e
queima a segunda tentativa do cliente.

🪤 O mesmo conselho é CERTO noutro lugar: DWG que não abre (objeto AEC/MEP)
resolve exportando em DXF. Este guarda só olha a copy de TAMANHO — a 1ª versão
dele acusava a copy certa e teria me empurrado a piorar o produto.

🪤 A frase do cliente não existe inteira no fonte: ela é montada por literais
grudados (`f"... pro nosso "` + `f"limite de memória ..."`). Procurar no fonte
cru devolve zero e deixa passar conselho errado que atravesse a quebra de
linha. Por isso cola os literais adjacentes antes de procurar.
"""
import io
import os
import re

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

_B = chr(92)
_NL = _B + "n"

# Cola literais adjacentes: `"..." <quebra> f"..."` vira um texto só.
_COLA = re.compile('"' + _B + 's*' + _NL + _B + 's*f?"')

# Onde a copy de TAMANHO começa. Vale pras 3 mensagens por prancha e pra final.
_ANCORA = "grande demais pro nosso limite"

# Quanto de texto depois da âncora ainda é a mesma mensagem.
_JANELA = 500


def _copy_que_o_cliente_le(src):
    """Só as strings, sem comentário, com os literais colados.

    Comentários fora: eles CITAM o conselho proibido pra explicar por que ele
    saiu, e um guarda que os lesse acusaria a própria documentação. Já caí
    nessa cinco vezes em 02/09.
    """
    linhas = [l for l in src.splitlines() if not l.strip().startswith("#")]
    return _COLA.sub("", chr(10).join(linhas))


def _conselhos_errados(src):
    """Conselhos de DXF dentro da copy de tamanho. Fora dela, não é da conta."""
    txt = _copy_que_o_cliente_le(src)
    achados = []
    for m in re.finditer(re.escape(_ANCORA), txt):
        janela = txt[m.start():m.start() + _JANELA]
        for m2 in re.finditer("[^" + _NL + "]*(?:suba|sobe|exporte|reexporte)"
                              "[^" + _NL + "]*em DXF[^" + _NL + "]*",
                              janela, re.I):
            trecho = m2.group(0).strip()
            # Dizer que DXF NÃO resolve é o conserto — não pode ser acusado.
            if not re.search("n[ãa]o (resolve|adianta|ajuda)", trecho, re.I):
                achados.append(trecho)
    return achados


def test_a_recusa_por_tamanho_nao_manda_reexportar_em_dxf():
    """DXF é texto puro: reexportar dá o mesmo tamanho e a mesma falha."""
    ruins = _conselhos_errados(_FONTE)
    assert not ruins, (
        "a copy de prancha grande ainda manda o cliente reexportar em DXF, "
        "o que dá exatamente a mesma falha:" + _NL + "  "
        + (_NL + "  ").join(ruins))


def test_CONTROLE_o_guarda_REPROVA_a_copy_que_o_rafael_leu():
    """Sem isto o teste acima passa por não achar nada, não por estar limpo."""
    antiga = (
        '    msg = ("essa prancha é grande demais pro nosso limite de memória "' + chr(10) +
        '           "de hoje — o arquivo não tem defeito. Sobe ela em DXF, ou "' + chr(10) +
        '           "uma prancha por vez, que a gente lê")' + chr(10))
    assert _conselhos_errados(antiga), (
        "o guarda não reprovou a copy que de fato foi entregue ao Rafael — "
        "ele está cego, e o teste de cima é verde falso")


def test_CONTROLE_o_guarda_ACEITA_dizer_que_DXF_nao_resolve():
    """A frase honesta não pode ser acusada, senão o guarda proíbe o conserto."""
    boa = ('    msg = ("essa prancha é grande demais pro nosso limite de "' + chr(10) +
           '           "memória — reexportar em DXF não resolve, DXF é texto puro")' + chr(10))
    assert not _conselhos_errados(boa)


def test_CONTROLE_o_guarda_NAO_se_mete_com_DWG_que_nao_abre():
    """Pra DWG com objeto AEC/MEP, exportar em DXF é o conselho CERTO."""
    certa = ('    fix = ("não conseguimos abrir o seu DWG — o ideal é reenviar "' + chr(10) +
             '           "em DXF ou PDF vetorial, ou salvar numa versão mais antiga")' + chr(10))
    assert not _conselhos_errados(certa), (
        "o guarda invadiu a copy de DWG-não-abre, onde DXF é a saída certa")


def test_uma_prancha_por_vez_so_aparece_com_mais_de_uma():
    """Ele mandou UM arquivo e leu 'mande uma prancha por vez'."""
    i = _FONTE.find('_saidas.append("mande uma prancha por vez")')
    assert i > 0, ("sumiu o conselho de mandar uma prancha por vez — ele é "
                   "certo pra quem manda VÁRIAS, só não pra quem manda uma")
    antes = _FONTE[max(0, i - 400):i]
    assert "if not _um_so:" in antes, (
        "o conselho 'uma prancha por vez' não está mais preso à condição de "
        "haver mais de um arquivo — quem manda UM volta a ler isso")
    assert "len(file_paths) <= 1" in _FONTE, (
        "a condição não olha mais a lista real de arquivos do job")


def test_o_gatilho_continua_casando():
    """A mensagem de dentro e a busca de fora têm que continuar batendo.

    🪤 Acoplamento escondido: o bloco de erro do `process_job` decide qual
    mensagem final mostrar procurando esta frase dentro do erro por prancha.
    Reescrever a mensagem de dentro sem ela faz o cliente cair na mensagem
    genérica de "problema técnico nosso" — sem nenhum teste reclamar.
    """
    frase = "grande demais pro nosso limite de memória"
    assert _FONTE.count('if "%s" in str(_e))' % frase) == 1, (
        "mudou a frase que o process_job procura pra identificar recusa por "
        "tamanho")
    colado = _copy_que_o_cliente_le(_FONTE)
    quantas = colado.count(frase)
    assert quantas >= 3, (
        "só %d mensagem(ns) por prancha ainda carrega(m) a frase-gatilho; "
        "as outras vão cair na mensagem genérica de problema técnico"
        % quantas)


def test_o_email_de_falha_nao_contradiz_o_proprio_texto():
    """A arte do e-mail dizia 'exporte em DXF' nos TRÊS ramos.

    No ramo de tamanho isso contradizia o texto logo abaixo ("exporte só a
    prancha necessária") e repetia o conselho que não funciona.
    """
    assert '_email_img("falha-arquivo.png", alt_img)' in _FONTE, (
        "a legenda da arte voltou a ser fixa — ela precisa seguir o ramo do "
        "diagnóstico")
    assert _FONTE.count("alt_img = ") >= 3, (
        "faltou legenda em algum ramo: um ramo sem alt_img levanta NameError "
        "no envio do e-mail de falha")
