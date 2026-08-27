# -*- coding: utf-8 -*-
"""`blocos=0` não distinguia "não tem" de "jogamos fora".

🚨 26/08/2026, caso **André** (job `d5dbe1ed`, 09:46). Prancha ELÉTRICA de
78 MB, convertida pelo libredwg porque o ODA recusou:

    motor:geometria  hachuras=581 poligonos=9 paredes=76824 blocos=0
                     textos=2146 cotas=0 layers=38 attribs=0

Prancha elétrica é **feita de bloco** — luminária, tomada, ponto — e contar
bloco é a única coisa que o motor faz muito bem. Os 47 itens dele saíram sem um
único selo de medição.

🔑 E não é caso isolado: **70 de 134 pranchas (52%) saem com `blocos=0`**. Se
for filtro nosso, é o defeito mais caro do motor; se for o arquivo, é limite
honesto que a gente precisa dizer ao cliente. Com o log dizendo só o total
final, a pergunta não tinha resposta.

🪤 Hipótese que MORREU no teste antes de virar código: "o libredwg explode os
blocos". Medido — libredwg tem 52,2% de pranchas sem bloco e média de 104
blocos; o outro caminho tem 72,2% e média de 1. O plano B preserva MAIS bloco,
não menos.

🎯 O suspeito que sobrou é o filtro `bname.startswith("*") or "$" in bname`.
Bloco ganha `$` no nome exatamente quando o arquivo passa por conversão ou
importação (`A$C6BFD6B53` é o AutoCAD renomeando conflito), e prancha elétrica
é feita de bloco dinâmico. Mas isso é HIPÓTESE — este commit **não muda
comportamento nenhum**, só passa a contar. Trocar o filtro no palpite é como
morreram 5 de 5 ideias em 10/08 ([[feedback_motor_sempre_pode_melhorar]]).
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fonte(nome):
    return io.open(os.path.join(_BACKEND, nome), encoding="utf-8").read()


def test_o_contador_conta_CADA_filtro_separado():
    """Um total só não resolve: são três filtros com causas diferentes, e a
    ação é diferente pra cada um."""
    ext = _fonte("dwg_extractor.py")
    i = ext.find('for insert in msp.query("INSERT"):')
    assert i > 0
    trecho = ext[i:i + 1800]
    for chave in ("anonimo", "utilitario", "anotacao", "ilegivel"):
        assert '_desc["%s"] += 1' % chave in trecho, (
            "o filtro %r descarta INSERT sem contar — continua invisível" % chave)


def test_guarda_AMOSTRA_dos_nomes_descartados():
    """🔑 É o nome que decide a questão. `*U5` é lixo do AutoCAD;
    `A$C6BFD6B53` é item de verdade renomeado na conversão. Sem ver o nome, o
    número sozinho não diz qual dos dois."""
    ext = _fonte("dwg_extractor.py")
    assert "_amostra_anonimo" in ext, "não guarda nenhum nome descartado"
    assert "len(_amostra_anonimo) < 5" in ext, (
        "a amostra não tem teto — log de prancha com 70 mil INSERT viraria "
        "um despejo")


def test_o_contador_CHEGA_no_log_do_motor():
    """🪤 Guarda de CALL SITE. Contar e não gravar é o mesmo que não contar —
    foi assim que o `paredes_m` ficou invisível até hoje de manhã."""
    m = _fonte("main.py")
    assert "_descarte_de_blocos(extraction)" in m, (
        "o contador não é usado no log de geometria")
    i = m.find('f"blocos={len(extraction.blocks or [])} "')
    assert i > 0, "não achei a linha do log de geometria"
    assert "_descarte_de_blocos" in m[i:i + 1400], (
        "o descarte não está no MESMO log do `blocos=` — separado, ninguém "
        "cruza os dois")


def test_o_campo_atravessa_a_estrutura_de_extracao():
    ext = _fonte("dwg_extractor.py")
    assert "blocos_descartados: dict = field(default_factory=dict)" in ext, (
        "o campo sumiu da DXFExtraction")
    assert "blocos_descartados=dict(_desc" in ext, (
        "o campo não é preenchido no retorno — chegaria sempre vazio")


def test_log_LIMPO_quando_nao_houve_descarte():
    """A maioria das pranchas não descarta nada. Se o sufixo aparecesse sempre,
    viraria ruído e o sinal se perderia — foi o erro do `cotas=-`."""
    from main import _descarte_de_blocos as f

    class _Vazio:
        blocos_descartados = {}

    class _Zerado:
        blocos_descartados = {"anonimo": 0, "utilitario": 0, "anotacao": 0,
                              "ilegivel": 0, "amostra_anonimo": []}

    assert f(_Vazio()) == "", "prancha sem descarte suja o log"
    assert f(_Zerado()) == "", "descarte tudo-zero suja o log"
    assert f(object()) == "", "objeto sem o campo não pode explodir o log"


def test_controle_positivo_o_caso_do_ANDRE_apareceria():
    """🧪 O teste que prova que o guarda REPROVA: um descarte real tem que
    virar texto legível, com o nome que decide a questão."""
    from main import _descarte_de_blocos as f

    class _Andre:
        blocos_descartados = {"anonimo": 1843, "utilitario": 0, "anotacao": 12,
                              "ilegivel": 0,
                              "amostra_anonimo": ["A$C6BFD6B53", "*U5"]}

    saida = f(_Andre())
    assert "anonimo=1843" in saida, saida
    assert "anotacao=12" in saida, saida
    assert "utilitario" not in saida, "filtro zerado não devia aparecer: %s" % saida
    assert "A$C6BFD6B53" in saida, "o nome que decide a questão não aparece"


def test_NAO_mudou_o_comportamento_do_filtro():
    """🚨 Este commit é INSTRUMENTO, não conserto. Se o filtro mudar junto, a
    medição já nasce contaminada — não dá pra saber o que era antes."""
    ext = _fonte("dwg_extractor.py")
    assert 'if bname.startswith("*") or "$" in bname:' in ext, (
        "o filtro foi alterado no mesmo commit do contador — agora não dá pra "
        "medir o efeito dele separado da mudança")
