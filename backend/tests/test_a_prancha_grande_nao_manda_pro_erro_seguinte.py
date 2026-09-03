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


# 🩸 A 1ª VERSÃO DESTE GUARDA TINHA TRÊS BURACOS, provados RODANDO (revisão
# adversarial do meu próprio commit, 03/09). Os três deixavam passar copy que
# manda o cliente pra segunda falha, com o controle positivo ainda verde:
#
#   (A) absolvia pela LINHA, não pela ORAÇÃO. Um "não resolve" sobre outro
#       assunto na mesma linha libertava o conselho errado ao lado:
#       "…reprocessar não resolve; exporte em DXF e mande de novo" → passava.
#   (B) a janela só olhava DEPOIS da âncora. Conselho ANTES escapava:
#       "Exporte em DXF e reenvie: essa prancha é grande demais…" → passava.
#   (C) a lista de verbos era só suba|sobe|exporte|reexporte. "Manda ela em DXF
#       que a gente lê" → passava.
#
# 🔑 Guarda estreito demais é pior que guarda nenhum: ele dá a sensação de
# cobertura. Os três casos acima viraram controle lá embaixo.
_VERBOS = "(?:sub[ai]|sobe|export|reexport|mand|salv|convert|ger[ae])"


def _oracoes(texto):
    """Quebra em orações — a absolvição vale por oração, não pela linha."""
    return [o for o in re.split("[;.]", texto) if o.strip()]


def _conselhos_errados(src):
    """Conselhos de DXF dentro da copy de tamanho. Fora dela, não é da conta."""
    txt = _copy_que_o_cliente_le(src)
    achados = []
    for m in re.finditer(re.escape(_ANCORA), txt):
        # janela nos DOIS sentidos: o conselho pode vir antes da âncora
        janela = txt[max(0, m.start() - _JANELA):m.start() + _JANELA]
        for o in _oracoes(janela):
            if not re.search("em DXF", o, re.I):
                continue
            if not re.search(_VERBOS, o, re.I):
                continue
            # Dizer que DXF NÃO resolve é o conserto — não pode ser acusado.
            if re.search("n[ãa]o (resolve|adianta|ajuda)", o, re.I):
                continue
            achados.append(o.strip())
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


def test_CONTROLE_os_TRES_BURACOS_provados_na_revisao_adversarial():
    """Os três casos que a 1ª versão deste guarda deixava passar.

    Cada um foi provado RODANDO contra o guarda velho, com o controle positivo
    dele ainda verde — que é exatamente o jeito de um guarda mentir.
    """
    A = ('    msg = ("essa prancha é grande demais pro nosso limite de memória "' + chr(10) +
         '           "de hoje — reprocessar não resolve; exporte em DXF e mande de novo")' + chr(10))
    B = ('    msg = ("Exporte em DXF e reenvie: essa prancha é grande demais pro "' + chr(10) +
         '           "nosso limite de memória de hoje")' + chr(10))
    C = ('    msg = ("essa prancha é grande demais pro nosso limite de memória — "' + chr(10) +
         '           "o arquivo não tem defeito. Manda ela em DXF que a gente lê")' + chr(10))
    for nome, copy in (("A/absolvição pela linha", A),
                       ("B/conselho ANTES da âncora", B),
                       ("C/verbo fora da lista", C)):
        assert _conselhos_errados(copy), (
            "buraco %s voltou: o guarda não acusa essa copy" % nome)


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
    busca = 'if "%s" in str(_e))' % frase
    assert _FONTE.count(busca) == 1, (
        "mudou a frase que o process_job procura pra identificar recusa por "
        "tamanho")
    # 🪤 A 1ª versão contava `>= 3` sobre o texto inteiro — e o texto inteiro
    # tem QUATRO ocorrências: as 3 mensagens MAIS o literal da própria busca,
    # que não é copy de cliente nenhum. Apagando a frase de UMA das mensagens a
    # conta caía pra 3 e o teste seguia VERDE, com só 2 mensagens carregando o
    # gatilho. Tira a linha da busca e trava em `== 3`.
    colado = _copy_que_o_cliente_le(_FONTE.replace(busca, ""))
    quantas = colado.count(frase)
    assert quantas == 3, (
        "%d mensagem(ns) por prancha carregam a frase-gatilho, e têm que ser 3; "
        "a que perdeu vai jogar o cliente na mensagem genérica de 'problema "
        "técnico nosso'" % quantas)


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


def test_o_preheader_do_email_segue_o_ramo():
    """A linha da caixa de entrada é a PRIMEIRA coisa que o cliente lê.

    🩸 Ela dizia "exporte em DXF" nos três ramos — inclusive no de tamanho, onde
    esse é justamente o conselho que não funciona. O texto certo ficava lá
    dentro, depois de um preheader que já tinha mandado pro lugar errado.
    """
    assert "preheader=pre_txt," in _FONTE, (
        "o preheader do e-mail de falha voltou a ser fixo — ele precisa seguir "
        "o ramo do diagnóstico, igual à legenda da arte")
    assert _FONTE.count("pre_txt = ") >= 3, (
        "faltou preheader em algum ramo: um ramo sem pre_txt levanta NameError "
        "no envio do e-mail de falha")
