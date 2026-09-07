# -*- coding: utf-8 -*-
"""O e-mail do reprocesso não pode dizer "medimos" quando não mediu.

🚨 25/08/2026, ao vivo. O cliente anexou os DWG que a gente pediu, e recebeu:

    assunto:   "Rede cnt — medimos com o CAD, planilha atualizada"
    selo:      "✓ Medido"
    corpo:     "medindo pelo CAD que você anexou"
    preheader: "O arquivo CAD que você mandou depois entrou na conta."

**Zero itens foram medidos.** E o aviso, no corpo do MESMO e-mail, dizia:
*"o plano B abriu os desenhos, mas nenhuma quantidade foi medida da
geometria"*. Duas frases, uma verdade — e a que aparece no assunto e no selo é
a falsa.

Duas causas independentes, as duas consertadas aqui:

  1. `_piorou_c = bool(_cmp_c.get("perdeu_medidos"))` ignorava a queda de
     LINHAS. Foram 208 itens → 15, com 0 medido dos dois lados: `perdeu_
     medidos` deu 0 e o e-mail caiu no ramo de boa notícia.
  2. O ramo de boa notícia **nunca conferia se algo foi medido**. Mesmo sem a
     causa 1, um reprocesso normal com 0 medidos anunciaria "✓ Medido".

🔑 É a regra dura nº1 dentro do e-mail: só o que veio da geometria pode ser
chamado de medido. O selo da planilha respeita isso desde sempre; o assunto do
e-mail, não.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import fonte  # noqa: E402


def _so_codigo(texto):
    """Sem comentário: o comentário CITA o defeito pra explicar o conserto."""
    return chr(10).join(l for l in texto.splitlines()
                        if not l.strip().startswith("#"))


def _ramos(corpo):
    """Fatia o if/elif/else em {piorou, mediu, nao_mediu}, duas vezes (corpo
    do e-mail e assunto), concatenando cada ramo."""
    import re as _re
    saida = {"piorou": "", "mediu": "", "nao_mediu": ""}
    for m in _re.finditer(r"if _piorou_c:", corpo):
        i_m = corpo.index("elif _mediu_c:", m.start())
        i_e = corpo.index("else:", i_m)
        fim = corpo.find("if _piorou_c:", i_e)
        fim = fim if fim > 0 else len(corpo)
        saida["piorou"] += corpo[m.start():i_m]
        saida["mediu"] += corpo[i_m:i_e]
        saida["nao_mediu"] += corpo[i_e:fim]
    return saida


def _bloco():
    """O trecho que monta o e-mail de complemento (reprocesso com CAD)."""
    src = fonte("main.py")
    i = src.index("_cmp_c = _comparar_com_versao_anterior")
    return src[i:src.index("[email] complemento-pronto", i)]


# ══════════════════════════════════════════════════════════════════════════
#  Causa 1 — a comparação tem que olhar linhas, não só medidos
# ══════════════════════════════════════════════════════════════════════════
def test_piorou_olha_a_frase_inteira_e_nao_so_medidos(monkeypatch):
    """🩸 25/08, job 6e9649a7: a releitura caiu de 208 itens pra 15, com ZERO
    medidos dos dois lados. `perdeu_medidos` deu 0 e o cliente recebeu e-mail
    de boa notícia. Quem sabe se houve piora é a FRASE, que olha os dois.

    🔑 Este guarda lia o fonte (`_piorou_c = bool(_cmp_c.get("frase"))`).
    Agora EXECUTA a comparação com o cenário exato daquele job.
    """
    import json as _js
    import main
    import urllib.request as _ur

    class _Resp:
        def __init__(self, d): self._b = _js.dumps(d).encode("utf-8")
        def read(self): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    # 🪤 A rota devolve UMA LINHA POR ITEM (`select=versao,confidence`), e a
    # função conta com `len()`. Um dicionário com "n_itens" seria contado como
    # UM item — e o teste passaria a provar outra coisa. Foi o primeiro erro
    # que executar de verdade pegou em mim aqui.
    # A versão anterior daquele job: 208 itens, 0 medidos.
    _antes = [{"versao": 1, "confidence": "estimado"} for _ in range(208)]
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=None: _Resp(_antes))
    cmp_ = main._comparar_com_versao_anterior("6e9649a7", n_medidos=0, n_itens=15)
    assert cmp_, "a comparação não achou a versão anterior — o teste não provou nada"
    assert cmp_.get("perdeu_medidos") in (0, None), (
        "o cenário do teste mudou: aqui `perdeu_medidos` PRECISA ser 0, senão "
        "não estamos provando que a queda de LINHAS é detectada sozinha")
    assert (cmp_.get("frase") or "").strip(), (
        "a queda de 208 itens para 15 não gerou frase de piora — o cliente "
        "recebe e-mail de boa notícia, que foi o incidente de 25/08")
    # e o e-mail, com essa frase, NÃO comemora
    tudo = " || ".join(_vozes(n_medidos=0, n_itens=15, piora=cmp_["frase"]))
    assert not [f for f in _AFIRMA_MEDICAO if f in tudo], tudo[:300]


# ══════════════════════════════════════════════════════════════════════════
#  Causa 2 — nada afirma medição sem conferir
# ══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
#  A DECISÃO, EXECUTADA
# ═══════════════════════════════════════════════════════════════════════════
# 🩸 06/09/2026 — OS DOIS GUARDAS ABAIXO ERAM CEGOS, provado por mutação.
# Um cobrava a string `_mediu_c = _n_med_c > 0`; o outro fatiava o TEXTO dos
# ramos e conferia que as frases de medição moravam no ramo certo. Nenhum dos
# dois perguntava EM QUE CONDIÇÃO aquele ramo roda.
# A mutação que passou verde: `_mediu_c = _n_med_c > 0` -> `... or
# len(all_items) > 0`. A string cobrada continua sendo PREFIXO da linha, as
# frases continuam no ramo certo, e qualquer reprocesso com ZERO medidos passa
# a receber assunto "medimos com o CAD", selo "✓ Medido" e o corpo "medindo
# pelo CAD que você anexou" — o incidente de 25/08 reproduzido inteiro.
# Agora eles CHAMAM `voz_do_email_de_reprocesso` e leem as cinco saídas.

#: Toda frase que AFIRMA medição, nas cinco vozes do e-mail.
_AFIRMA_MEDICAO = ("medimos com o CAD", "medindo pelo <b>CAD</b>",
                   "&#10003; Medido", "medidos do desenho")


def _vozes(n_medidos, n_itens=40, n_geo=0, piora="", origem=""):
    import main
    return main.voz_do_email_de_reprocesso(
        "Casa da Serra", "Casa da Serra", n_itens, n_medidos, n_geo,
        frase_piora=piora, frase_origem=origem)


def test_existe_um_ramo_pra_quando_NAO_mediu():
    """Com ZERO medidos, nenhuma das cinco vozes pode afirmar medição."""
    tudo = " || ".join(_vozes(n_medidos=0, n_itens=40))
    achadas = [f for f in _AFIRMA_MEDICAO if f in tudo]
    assert not achadas, (
        "com ZERO medidos o e-mail afirma medição em %r — é a regra dura nº1 "
        "quebrada dentro do e-mail. Saída: %s" % (achadas, tudo[:400]))
    # 🩸 03/09/2026 — a frase era "Nenhuma quantidade saiu da geometria", e ela
    # é FALSA quando o selo é zero mas a geometria FOI lida (job b5ce23ff:
    # 90,86 m² de hachura e 169,83 m de comprimento de layer). Selo e origem
    # são dois fatos: o e-mail afirma só o selo.
    assert "Nenhum item saiu com o selo" in tudo, tudo[:400]


def test_CONTROLE_com_medicao_de_verdade_o_email_PODE_dizer_que_mediu():
    """O outro lado. Sem isto, um e-mail que nunca afirmasse nada passaria."""
    tudo = " || ".join(_vozes(n_medidos=31, n_itens=40))
    assert any(f in tudo for f in _AFIRMA_MEDICAO), (
        "com 31 itens medidos o e-mail deixou de dizer que mediu — a gente "
        "passou a esconder trabalho que foi feito de verdade")
    assert "31" in tudo, "o número de medidos sumiu do texto"


def test_a_PIORA_vence_a_medicao():
    """🪤 Releitura que piorou não pode virar comemoração nem quando mediu —
    caso cliente-16, 10/08: 47 medidos viraram 28 e o e-mail comemorou."""
    tudo = " || ".join(_vozes(n_medidos=28, piora="a leitura caiu de 47 para 28 medidos"))
    achadas = [f for f in _AFIRMA_MEDICAO if f in tudo]
    assert not achadas, (
        "a releitura PIOROU e o e-mail ainda afirma medição em %r" % achadas)
    assert "Mudou" in tudo and "compare" in tudo.lower()


@pytest.mark.parametrize("n_med,n_itens", [(0, 1), (0, 40), (0, 500)])
def test_nenhuma_quantidade_de_ITENS_destrava_a_afirmacao(n_med, n_itens):
    """🚨 A MUTAÇÃO EXATA que enganava o guarda velho: fazer o ramo de boa
    notícia depender do total de itens em vez do total de MEDIDOS. Aqui ela
    reprova, porque o teste varia o número de itens e olha o texto que sai."""
    tudo = " || ".join(_vozes(n_medidos=n_med, n_itens=n_itens))
    achadas = [f for f in _AFIRMA_MEDICAO if f in tudo]
    assert not achadas, (
        "com %d itens e ZERO medidos o e-mail afirma medição em %r — a "
        "condição do ramo passou a olhar a quantidade de LINHAS, não a de "
        "linhas MEDIDAS" % (n_itens, achadas))


def test_o_preheader_distingue_LEU_o_desenho_de_NAO_LEU():
    """A distinção de 03/09: 'nada ganhou selo' não é 'nada saiu da geometria'.
    Duas vozes sobre o mesmo fato foi como o problema começou."""
    _a, _s, _t, selo_leu, pre_leu = _vozes(n_medidos=0, n_geo=12)
    _a, _s, _t, selo_cego, pre_cego = _vozes(n_medidos=0, n_geo=0)
    assert pre_leu != pre_cego, (
        "o preheader ficou igual nos dois casos — voltou a dizer 'nenhuma "
        "quantidade saiu da geometria' para quem TEVE a geometria lida")
    # quem TEVE geometria lida ouve "saiu do desenho, mas nada ganhou selo";
    # quem nao teve ouve "nada saiu da geometria". Sao fatos diferentes.
    assert "selo de medido" in pre_leu.lower(), pre_leu
    assert "saiu da geometria" in pre_cego.lower(), pre_cego
    assert "sem selo de medido" in selo_leu.lower(), selo_leu
    assert "sem medida do desenho" in selo_cego.lower(), selo_cego


def test_o_selo_de_quem_nao_mediu_e_honesto():
    """O selo é a primeira coisa que o cliente lê. Executa em vez de ler."""
    _a, _s, _t, selo, _p = _vozes(n_medidos=0, n_geo=0)
    assert "Sem medida do desenho" in selo, (
        "o selo do caso 'não mediu' voltou a ser genérico: %r" % selo)


def test_o_preheader_nao_promete_medicao():
    """🪤 O Gmail bloqueia imagem por padrão, então o preheader é uma das
    primeiras linhas que o cliente lê — mente ali e mentiu no e-mail todo.

    🩸 03/09: este teste ancorava na FRASE LITERAL ("nenhuma quantidade saiu
    da") e reprovou um conserto legítimo. O e-mail passou a ter DOIS preheaders
    no ramo de zero-medidos, porque o anterior contradizia o próprio corpo:
    dizia "nenhuma quantidade saiu da geometria" enquanto o corpo, três linhas
    abaixo, dizia "parte das quantidades foi tirada da geometria".

    🔑 O que o guarda tem que cobrar é a INTENÇÃO — nenhum preheader do ramo
    pode afirmar que mediu — e não uma redação específica. Guarda preso à
    redação vira obstáculo ao conserto certo.

    🩸 06/09: e ele AINDA lia o fonte — recortava 900 caracteres a partir de
    `_badge_c` e pescava os preheaders com regex, precisando até colar
    literais adjacentes na mão porque a frase do cliente não existe inteira no
    código. Recorte de tamanho fixo quebra quando o código anda e absolve
    quando o defeito mora fora da janela. Agora EXECUTA os dois casos.
    """
    pres = [_vozes(n_medidos=0, n_geo=0)[4], _vozes(n_medidos=0, n_geo=12)[4]]
    for p in pres:
        assert not re.search(r"medimos|foi medid[oa]|quantidade medida", p, re.I), (
            "preheader afirmando medição num e-mail de ZERO medidos: %s" % p[:140])
    assert len(set(pres)) == 2, (
        "os dois casos de origem devolvem o MESMO preheader — voltou a dizer "
        "'nenhuma quantidade saiu da geometria' para quem TEVE a geometria "
        "lida, que é a contradição de 03/09")
    junto = " ".join(pres)
    assert "nenhuma quantidade saiu da" in junto, (
        "sumiu o preheader do caso em que NADA saiu da geometria")
    assert "parte das quantidades" in junto or "selo de medido" in junto, (
        "sumiu o preheader do caso em que a geometria FOI lida — é ele que "
        "para de contradizer o corpo")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO: o guarda tem que REPROVAR o e-mail de antes
# ══════════════════════════════════════════════════════════════════════════
_EMAIL_ANTIGO = '''
                    _cmp_c = _comparar_com_versao_anterior(job_id, _n_med_c, len(all_items))
                    _piorou_c = bool(_cmp_c.get("perdeu_medidos"))
                    if _piorou_c:
                        _abre_c = "saiu pior"
                    else:
                        _abre_c = "medindo pelo <b>CAD</b> que voce anexou"
                    print("[email] complemento-pronto")
'''


def test_controle_positivo_o_email_de_antes_nao_passaria():
    assert '_piorou_c = bool(_cmp_c.get("frase"))' not in _EMAIL_ANTIGO
    assert "_mediu_c = _n_med_c > 0" not in _EMAIL_ANTIGO
    assert "Nenhum item saiu com o selo" not in _EMAIL_ANTIGO
