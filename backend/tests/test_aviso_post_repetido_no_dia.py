# -*- coding: utf-8 -*-
"""Sete dias postando dois por dia, e ninguém soube.

📣 27/08/2026. O Pedro estranhou dois posts no Instagram e foi descobrir
olhando o feed. Puxando o fio, eram **SETE DIAS seguidos**:

    21/08 sex   feed_sex_w33  +  feed_sex_w34    ambos 17:00
    22/08 sáb   feed_sab_w33  +  feed_sab_w34    ambos 11:00
    23/08 dom   feed_dom_w34  +  feed_dom_w32    ambos 20:00
    24/08 seg   feed_seg_w35  +  feed_seg_w33    ambos 19:00
    25/08 ter   feed_ter_w33  +  feed_ter_w35    ambos 19:00
    26/08 qua   airnaldo_w33  +  airnaldo_w35    ambos 19:00   ← DOIS AIrnaldo
    27/08 qui   feed_qui_w35  +  feed_qui_w33    ambos 19:00

🔑 **A causa:** duas levas de conteúdo agendadas para as MESMAS datas — uma
criada em 15/07 (slots w29–w33), outra em 03/08 (w33–w36). A leva velha tinha
`slot_key` com número de semana que não batia com a data: `w33` marcado para
21–27/08, que é semana 35.

🪤 **Por que nada reclamou:** a unicidade era por `slot_key`, e os dois nomes
são diferentes (`feed_qui_w33` ≠ `feed_qui_w35`). **Ninguém conferia por DATA.**

🚫 **NÃO bloqueia, de propósito.** Perguntei ao Pedro se a regra de um post por
dia era firme e ele respondeu: *"não vejo problema em 2 por dia também"*. Então
o problema nunca foi publicar dois — foi ele **descobrir depois, pelo feed**.
Este código avisa e deixa publicar; a decisão continua dele.

📌 A duplicação acabou sozinha em 27/08 (a leva de 15/07 se esgotou no w33), e
de 28/08 em diante volta a um por dia. Mas nada impedia o repeat — agora pelo
menos aparece.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FONTE = io.open(os.path.join(_BACKEND, "instagram_webhook.py"), encoding="utf-8").read()


def _sem_comentarios(txt):
    """🪤 Quinta vez que eu preciso disto no mesmo dia: teste que lê comentário
    como código reprova (ou aprova) pelo motivo errado."""
    saida = []
    for l in txt.split(chr(10)):
        t = l.strip()
        if t.startswith("#"):
            continue
        saida.append(l)
    return chr(10).join(saida)


def _bloco_do_aviso():
    i = _FONTE.find("scheduled_post_repetido_no_dia")
    assert i > 0, "o aviso de post repetido no dia sumiu"
    j = _FONTE.rfind("try:", 0, i)
    return _FONTE[j:i + 400]


def test_o_aviso_existe():
    assert "scheduled_post_repetido_no_dia" in _FONTE, (
        "sem este aviso, dois posts no mesmo dia voltam a ser descobertos pelo "
        "feed — que foi como o Pedro descobriu 7 dias depois")


def test_NAO_bloqueia_a_publicacao():
    """🚫 Decisão do Pedro: dois por dia é aceitável. Um bloqueio aqui seria eu
    decidindo o conteúdo dele."""
    b = _sem_comentarios(_bloco_do_aviso())
    for proibido in ("return", "raise", "continue", '"status": "failed"', "skip"):
        assert proibido not in b, (
            "o aviso virou BLOQUEIO (%r) — o Pedro disse que dois por dia está "
            "ok; o problema era não saber" % proibido)


def test_conta_por_DATA_e_nao_por_slot_key():
    """🔑 O buraco original. `feed_qui_w33` e `feed_qui_w35` são nomes
    diferentes, então unicidade por slot nunca ia pegar."""
    b = _bloco_do_aviso()
    assert "published_at=gte." in b and "published_at=lte." in b, (
        "a checagem não é por data de publicação — volta a ser cega ao caso "
        "que aconteceu")
    assert "slot_key=eq." not in b, (
        "voltou a filtrar por slot_key, que é justamente o que não pega")


def test_so_avisa_quando_ha_MAIS_de_um():
    """Um post por dia é o normal; avisar sempre viraria ruído e o aviso
    perderia o valor — foi o erro do `cotas=-`."""
    b = _bloco_do_aviso()
    assert "> 1" in b, (
        "o aviso dispara mesmo com um post só — vira ruído diário")


def test_a_falha_do_aviso_NAO_derruba_a_publicacao():
    """🪤 O aviso é acessório. Se a consulta ao banco falhar, o post tem que
    sair mesmo assim — publicar é o trabalho, avisar é o extra."""
    b = _bloco_do_aviso()
    assert "except Exception" in b, (
        "a checagem não está protegida — um soluço do banco impediria a "
        "publicação do post")


def test_o_aviso_diz_QUAIS_slots():
    """Saber que houve dois não resolve; saber QUAIS aponta a leva errada —
    foi assim que a colisão w33 × w35 apareceu."""
    b = _bloco_do_aviso()
    assert "slots" in b, "o aviso não registra quais slots colidiram"
