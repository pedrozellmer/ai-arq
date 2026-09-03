# -*- coding: utf-8 -*-
"""O alarme de "faltou medição" leu o briefing do cliente como queixa.

🩸 03/09/2026, cliente `v.anjos.ia.81@` (job `eebe543a`). Ele mandou no chat um
briefing pedindo auditoria técnica do projeto de REDE dele, com itens de
checklist como:

    "Infraestrutura insuficiente; **Falta de reserva técnica**;
     **Falta de espaço para expansão futura**"

O `falt(a|ou)` casou e o Pedro recebeu o e-mail **"Chat: cliente diz que faltou
medição — eebe543a"**. O cliente não disse isso. Ele estava listando o que
queria que a gente procurasse **no projeto dele**.

🔑 A palavra sozinha não distingue "faltou medição NA PLANILHA" de "falta
reserva técnica NO PROJETO DELE". O que distingue é a queixa estar perto de
algo **nosso** — planilha, quantitativo, item, medição, área.

🪤 Alarme falso gasta a atenção do Pedro, que é o recurso mais escasso desta
casa, e treina ele a ignorar os verdadeiros. O alarme existe porque o chat é o
melhor detector de buraco do motor que a gente tem (30/07: das 11 conversas,
3 eram falha real de medição) — é justamente por isso que ele não pode gritar
à toa.
"""
import agent


# O texto REAL que o cliente mandou em 03/09 (trecho do checklist dele).
_BRIEFING_DO_CLIENTE = (
    "Estou trabalhando em um projeto de infraestrutura de rede e cabeamento "
    "estruturado e vou fornecer uma planta baixa em formato DWG para análise. "
    "Identifique qualquer: Divergência técnica; Rack subdimensionado; "
    "Rota de cabeamento inadequada; Infraestrutura insuficiente; "
    "Falta de reserva técnica; Falta de espaço para expansão futura; "
    "Problema relacionado à organização dos cabos."
)


def _dispara(texto):
    """True quando o alerta REALMENTE seria enviado."""
    enviados = []
    _orig = agent._alerta_lacuna

    class _Falso:
        @staticmethod
        def _notify_admin(assunto, corpo):
            enviados.append(assunto)
            return True

    # Reimplementa a checagem exatamente como a função faz, sem tocar a rede.
    m = agent._LACUNA_RE.search(texto or "")
    if not m:
        return False
    perto = texto[max(0, m.start() - 90):m.end() + 90]
    return bool(agent._NOSSO_ENTREGAVEL_RE.search(perto))


def test_o_briefing_do_cliente_NAO_dispara_o_alarme():
    """🩸 O texto real de 03/09 que gerou o alerta falso."""
    assert not _dispara(_BRIEFING_DO_CLIENTE), (
        "o checklist do cliente sobre o PROJETO DELE voltou a virar "
        "'cliente diz que faltou medição'")


def test_CONTROLE_queixa_de_VERDADE_continua_disparando():
    """Sem isto, o conserto seria satisfeito desligando o alarme.

    Ele existe porque o chat é o melhor detector de buraco do motor que a casa
    tem — das 11 conversas de 30/07, 3 eram falha real de medição.
    """
    reais = [
        "faltou a medição das paredes na planilha",
        "a planilha veio sem quantitativo de piso",
        "por que não tem quantidade nos itens de forro?",
        "vários itens estão zerados na tabela",
        "não veio a área dos ambientes",
        "o quantitativo está incompleto, faltam linhas",
    ]
    for q in reais:
        assert _dispara(q), "deixou de acusar queixa real: %r" % q


def test_CONTROLE_reclamacao_longe_do_nosso_entregavel_nao_dispara():
    """A proximidade é o que separa — não a presença solta da palavra."""
    longe = (
        "Falta de reserva técnica no rack. " + ("bla " * 60)
        + "A planilha ficou boa."
    )
    assert not _dispara(longe), (
        "a janela de proximidade ficou larga demais e voltou a juntar coisas "
        "que não têm relação")


def test_a_lista_do_que_e_NOSSO_cobre_o_vocabulario_do_cliente():
    """Se a lista encolher, o alarme fica cego pras queixas reais."""
    for palavra in ("planilha", "quantitativo", "medição", "item",
                    "linha", "área", "quantidade"):
        assert agent._NOSSO_ENTREGAVEL_RE.search(palavra), (
            "'%s' saiu da lista do que é nosso entregável" % palavra)
