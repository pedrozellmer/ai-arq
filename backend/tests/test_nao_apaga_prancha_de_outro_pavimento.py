# -*- coding: utf-8 -*-
"""O motor não apaga a medição de uma prancha porque outra tem o mesmo serviço.

🩸 06/09/2026 — o achado mais grave da auditoria total, e o único em que o
produto AFIRMA uma certeza que não tem (todos os outros são o produto calando
uma incerteza). É a regra dura nº1 pelo avesso.

O QUE ACONTECIA: quando o mesmo serviço aparecia em pranchas diferentes, a
passada 6 declarava "duplicação cross-prancha", elegia UMA leitura e APAGAVA as
outras. O guarda que protegia isso (`_pode_fundir`) compara bitola, classe de
aço, fck e dimensão — não tem categoria de PAVIMENTO. Térreo e pavimento
superior têm a mesma descrição e a mesma disciplina, então viravam a mesma
linha. E o desempate premiava o selo CONFIRMADO acima da quantidade: a leitura
parcial branca vencia a medição maior e saía carimbada como medida do CAD.

O CASO (Flavio Hermolin, job d5e073cf), lido no banco de produção:
    "Alvenaria de vedação — levantamento de parede" · 255,06 ml · CONFIRMADO
    Versões descartadas: 819,06 m², 810,36 m², 50,37 m², 73,05 m², 15,48 ml
Metro LINEAR venceu metro QUADRADO. E as pranchas eram DEMOLIR-CONSTRUIR,
LAYOUT e LEVANTAMENTO — fases diferentes da mesma obra, não duplicatas.

TAMANHO: 1.245 itens em 80 projetos, 159 com selo de medido.

O CLIENTE JÁ TINHA DITO. Marcelo Affonso, 24/08: "são de pavimentos
diferentes... teria como separar a quantidade de paredes para cada um dos três
pavimentos?" — e o chat respondeu mandando separar os arquivos por pavimento.
O Jessé fez isso, com 8 DWG, e deduplicou do mesmo jeito.

🔑 A DECISÃO: manter as linhas, não somar. Somar exige saber se são trechos
distintos ou a mesma coisa desenhada duas vezes, e disso o motor não tem prova.
Duplicar é erro que o arquiteto VÊ e corrige; apagar é erro que ele não tem
como ver. Entre os dois, fica o visível.
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _passada6(src, so_codigo=False):
    """O corpo da passada que fazia winner/losers.

    🪤 `so_codigo=True` tira os comentários. Os comentários desta passada
    CONTAM a história do defeito — citam "winner/losers" e "Versões
    descartadas" de propósito, pra quem ler entender o que havia ali. Sem esta
    limpeza, o guarda acusa a própria documentação do conserto: foi o que
    aconteceu na primeira versão dele, e é a quinta vez no mesmo dia que um
    comentário meu planta o defeito que ele explica.
    """
    i = src.index("buckets_p6: dict[tuple, list] = {}")
    corpo = src[i:src.index("\ndef ", i)]
    if so_codigo:
        corpo = re.sub(r"^\s*#.*$", "", corpo, flags=re.M)
    return corpo


# ─────────────────────────────────────────────────────────────────────────────
#  O descarte acabou
# ─────────────────────────────────────────────────────────────────────────────

def test_a_passada_6_NAO_elege_vencedor_nem_descarta():
    """🚨 O invariante central: nenhuma leitura de prancha é apagada."""
    corpo = _passada6(_fonte(), so_codigo=True)
    assert "losers" not in corpo, (
        "o winner/losers voltou — alguma prancha está sendo apagada de novo")
    assert not re.search(r"winner\s*=\s*max\(group", corpo), (
        "a eleição de vencedor voltou à passada 6")


def test_o_texto_que_o_cliente_le_MUDOU_de_descarte_para_aviso():
    """Antes a observação dizia 'Versões descartadas: …' — ou seja, contava pro
    cliente o que a gente tinha jogado fora. Agora ela avisa e devolve a
    decisão pra ele."""
    corpo = _passada6(_fonte(), so_codigo=True)
    assert "Versões descartadas" not in corpo, (
        "a planilha voltou a informar descarte — se está informando, está "
        "descartando")
    assert "aparece em" in corpo and "pranchas do" in corpo, (
        "o aviso que substitui o descarte sumiu")
    # e tem que dizer o que FAZER com a informação
    assert "somam" in corpo or "soma" in corpo, (
        "o aviso não explica ao arquiteto que ele precisa decidir se soma")


def test_o_selo_de_medido_NAO_e_rebaixado():
    """🔑 Cada linha FOI medida na prancha dela. Rebaixar tudo pra estimado
    jogaria fora medição legítima — a regra nº1 protege contra AFIRMAR o que
    não se mediu, não manda esquecer o que se mediu."""
    trecho = _passada6(_fonte(), so_codigo=True)
    assert 'Confidence("estimado")' not in trecho, (
        "a passada passou a rebaixar o selo — perde medição de verdade")


# ─────────────────────────────────────────────────────────────────────────────
#  A trava de grandeza
# ─────────────────────────────────────────────────────────────────────────────

def test_grandezas_diferentes_nunca_disputam():
    """O caso do Flavio: 255 ml contra 819 m². Comprimento e área não são a
    mesma medida, e nem deveriam entrar no mesmo grupo."""
    corpo = _passada6(_fonte())
    assert "_UNIT_PRIORITY.get(u, 50) for u in _uns" in corpo, (
        "a trava de grandeza sumiu — metro linear volta a disputar com metro "
        "quadrado")


def test_CONTROLE_a_trava_separa_ml_de_m2():
    """Roda a aritmética da trava com as unidades reais do caso."""
    _UNIT_PRIORITY = {
        "m²": 100, "m2": 100, "m³": 100, "m3": 100,
        "m": 80, "ml": 80, "kg": 60, "un": 40, "cj": 35,
        "mês": 30, "dia": 25, "vb": 10, "%": 5,
    }
    # o caso do Flavio: ml x m²
    dims = {_UNIT_PRIORITY.get(u, 50) for u in {"ml", "m²"}}
    assert len(dims) > 1, "a trava não separaria ml de m² — o caso do Flavio passaria"
    # e o caso legítimo: duas leituras da MESMA grandeza continuam agrupando
    dims_iguais = {_UNIT_PRIORITY.get(u, 50) for u in {"m²", "m2"}}
    assert len(dims_iguais) == 1, (
        "a trava passou a separar m² de m2 — são a mesma grandeza escrita de "
        "dois jeitos, e separá-las quebraria agrupamento legítimo")


def test_CONTROLE_ml_e_m_continuam_juntos():
    """Metro e metro linear são a MESMA grandeza — a trava não pode separá-los,
    senão vira ruído em vez de proteção."""
    _UNIT_PRIORITY = {"m": 80, "ml": 80, "m²": 100}
    assert len({_UNIT_PRIORITY.get(u, 50) for u in {"m", "ml"}}) == 1


# ─────────────────────────────────────────────────────────────────────────────
#  Os guardas que já existiam continuam de pé
# ─────────────────────────────────────────────────────────────────────────────

def test_o_guarda_do_ACO_de_17_08_continua_intocado():
    """🪤 A passada 6 já tinha matado o aço da Eduarda: 6 bitolas viravam 1
    linha, 3.028 kg viravam 508 kg. O guarda de atributo que consertou aquilo
    não pode ter sido perdido no conserto de hoje."""
    corpo = _passada6(_fonte())
    assert "_pode_fundir(" in corpo, (
        "o guarda de atributo (bitola/classe/fck) sumiu — o aço da Eduarda "
        "volta a ser apagado")


def test_a_trava_de_prancha_unica_continua():
    """Item repetido na MESMA prancha não é caso desta passada."""
    corpo = _passada6(_fonte())
    assert "len(ref_sheets) < 2" in corpo


def test_CONTROLE_o_recorte_acha_a_passada_certa():
    """Prova que os testes acima leem a passada 6, e não outro trecho."""
    corpo = _passada6(_fonte())
    assert "buckets_p6" in corpo and "pass6" in corpo
    assert len(corpo) > 1500, "o recorte ficou curto demais pra ser a passada"
