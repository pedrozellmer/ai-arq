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
def test_piorou_olha_a_frase_inteira_e_nao_so_medidos():
    corpo = _so_codigo(_bloco())
    assert '_piorou_c = bool(_cmp_c.get("frase"))' in corpo, (
        "voltou a decidir 'piorou' só por `perdeu_medidos` — a queda de 208 "
        "linhas pra 15 passa batido e o cliente recebe e-mail de boa notícia")
    assert 'perdeu_medidos"))' not in corpo


# ══════════════════════════════════════════════════════════════════════════
#  Causa 2 — nada afirma medição sem conferir
# ══════════════════════════════════════════════════════════════════════════
def test_existe_um_ramo_pra_quando_NAO_mediu():
    corpo = _bloco()
    assert "_mediu_c = _n_med_c > 0" in corpo, (
        "o e-mail voltou a não perguntar se mediu antes de dizer que mediu")
    # 🩸 03/09/2026 — a frase era "Nenhuma quantidade saiu da geometria", e ela
    # é FALSA quando o selo é zero mas a geometria foi lida (job b5ce23ff, do
    # Edvaldo: 90,86 m² de hachura e 169,83 m de comprimento de layer). Selo e
    # origem são dois fatos; o e-mail passa a afirmar só o selo, e a origem vem
    # de `_origem_das_quantidades`, que é quem tem o dado.
    assert "Nenhum item saiu com o selo" in corpo, corpo[:300]
    assert "_frase_origem_c" in corpo, (
        "o e-mail voltou a afirmar procedência sem consultar a origem real")


@pytest.mark.parametrize("frase", [
    "medimos com o CAD",
    "medindo pelo <b>CAD</b>",
    "&#10003; Medido",
])
def test_toda_afirmacao_de_medicao_vive_no_ramo_do_mediu_c(frase):
    """🚨 Cada frase que afirma medição só pode existir no ramo `_mediu_c`.

    🪤 A 1ª versão deste teste tentava localizar a frase por posição relativa
    a `elif`/`else` e reprovou o código já consertado. Fatiar o bloco pelos
    marcadores dos ramos é mais burro e não erra."""
    corpo = _so_codigo(_bloco())
    if frase not in corpo:
        pytest.skip("frase não está mais no código")
    ramos = _ramos(corpo)
    fora = [nome for nome, texto in ramos.items()
            if nome != "mediu" and frase in texto]
    assert not fora, (
        "a frase %r aparece no(s) ramo(s) %s — existe caminho em que o e-mail "
        "diz 'medido' com zero medido" % (frase, fora))
    assert frase in ramos["mediu"]


def test_o_selo_de_quem_nao_mediu_e_honesto():
    corpo = _bloco()
    assert "Sem medida do desenho" in corpo, (
        "o selo do caso 'não mediu' voltou a ser genérico — o selo é a "
        "primeira coisa que o cliente lê")


def test_o_preheader_nao_promete_medicao():
    """🪤 O Gmail bloqueia imagem por padrão, então o preheader é uma das
    primeiras linhas que o cliente lê — mente ali e mentiu no e-mail todo."""
    corpo = _bloco()
    i = corpo.index("_pre_c = (\"O CAD entrou na conta")
    assert "nenhuma quantidade saiu da" in corpo[i:i + 220]


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
