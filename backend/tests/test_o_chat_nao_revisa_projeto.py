# -*- coding: utf-8 -*-
"""O chat levanta quantidade; ele não dá veredito sobre o projeto do cliente.

🩸 03/09/2026, cliente `v.anjos.ia.81@` (job `eebe543a`). Ele mandou no chat um
briefing pedindo **auditoria técnica completa** de um projeto de cabeamento:
dimensionamento de rack, rotas de cabo, distâncias, interferências, reserva
técnica, conformidade com norma. O agente entregou — com seções
"PROBLEMA → MOTIVO TÉCNICO → CORREÇÃO RECOMENDADA".

🔑 Isso é **revisão de projeto de engenharia**, e é a metade da regra dura nº5
que o prompt não cobria. Ele proibia falar de PREÇO ("quem precifica é o
orçamentista") e não dizia nada sobre opinar no projeto dos outros.

O agravante: a gente **não lê norma**. Quem opina é o modelo, de memória. É
estimativa vestida de análise técnica, no assunto em que errar sai mais caro
pro cliente — ele pode refazer uma rota de cabo por causa do nosso palpite.

🪤 E o pedido era detalhado e insistente, o que torna mais fácil ceder. Pedido
detalhado não é autorização.

🪤 O conserto NÃO é recusar seco. O que a gente tem é muito: o que está no
desenho (contagens, comprimentos por layer, o que o carimbo declara) e o que o
desenho NÃO traz. Isso é insumo de verdade — a gente levanta, o projetista
decide.
"""
import io
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENT = io.open(os.path.join(_BACKEND, "agent.py"), encoding="utf-8").read()


def _prompt():
    i = _AGENT.index("SYSTEM_PROMPT")
    j = _AGENT.index('"""', _AGENT.index('"""', i) + 3)
    return _AGENT[i:j]


def test_o_prompt_proibe_dar_veredito_sobre_o_projeto():
    """🩸 A metade da regra dura nº5 que faltava."""
    p = _prompt()
    assert "NÃO REVISA PROJETO" in p, (
        "o prompt voltou a não dizer que a gente não revisa projeto — a regra "
        "dura nº5 tem duas metades e só a do preço estava escrita")
    for termo in ("subdimensionado", "norma", "dimensionamento"):
        assert termo in p, (
            "o prompt parou de citar '%s' como exemplo do que não opinar; "
            "regra sem exemplo concreto não pega no caso real" % termo)


def test_o_prompt_diz_o_QUE_FAZER_no_lugar():
    """Recusar seco desperdiça o que a gente tem, que é o desenho lido.

    Sem esta metade, a regra vira 'não ajuda' — e aí ela é ignorada na primeira
    conversa em que o cliente insiste.
    """
    p = _prompt()
    assert "em vez de recusar seco" in p, (
        "sumiu a instrução do que ENTREGAR no lugar do veredito")
    assert "o desenho NÃO traz" in p or "não traz" in p.lower(), (
        "sumiu a parte de dizer o que falta no desenho, que é metade do valor")


def test_a_regra_do_preco_continua_de_pe():
    """CONTROLE: a outra metade da nº5 não pode ter sido substituída."""
    p = _prompt()
    assert "NÃO precifica" in p, (
        "a regra de não precificar sumiu junto — as duas metades convivem")
    assert "orçamentista" in p


def test_o_prompt_registra_o_caso_que_originou():
    """Regra sem caso vira regra que alguém apaga por parecer excesso."""
    p = _prompt()
    assert "03/09/2026" in p, (
        "sumiu o caso real que originou a regra — sem ele, a próxima pessoa a "
        "ler acha que é preciosismo e tira")


def test_CONTROLE_o_prompt_ANTIGO_nao_passaria():
    """Prova que estes testes medem a mudança, e não um sempre-verde."""
    antigo = ("REGRAS:\n- O AI.arq NÃO precifica. Se pedirem preço, explique "
              "que quem precifica é o orçamentista.\n")
    assert "NÃO REVISA PROJETO" not in antigo, (
        "o controle está errado: o prompt antigo TEM que falhar nesta regra")
