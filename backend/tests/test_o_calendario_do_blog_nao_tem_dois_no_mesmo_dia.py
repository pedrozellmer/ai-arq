# -*- coding: utf-8 -*-
"""Dois posts no mesmo dia = um deles não existe.

🩸 18/09/2026. O Pedro perguntou se dava pra escrever um post sobre IA e
engenharia pra trazer gente. Fui ver: o post JÁ ESTAVA ESCRITO e agendado —
`ia-conta-melhor-do-que-mede-planta`, pra 18/10. Só que **o dia 18/10 tinha
DOIS posts**, e o blog publica um por domingo desde abril. Um ia encobrir o
outro: trabalho pronto, pesquisado e com fontes, que ninguém leria.

🔑 O defeito é silencioso por natureza — nada quebra, nada fica vermelho, o
site sobe normal. Só falta um post na vida real. A listagem ordena por data e
mostra os dois juntos; o de baixo some do topo no mesmo dia em que nasce.

🪤 Este guarda NÃO exige domingo pra tudo: `dwg-ou-pdf-quantitativo...` saiu
numa quarta de julho e já está publicado — post antigo não é erro (regra da
casa). A régua do dia da semana vale só pro que ainda VAI ao ar.
"""
import collections
import datetime
import io
import json
import os

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_POSTS = os.path.join(_RAIZ, "blog", "posts.json")


def _posts():
    d = json.load(io.open(_POSTS, encoding="utf-8"))
    return d if isinstance(d, list) else d.get("posts", d)


def _data(p):
    return datetime.date.fromisoformat(str(p["publish_date"]))


def test_NENHUMA_data_de_publicacao_se_repete():
    """O guarda central. Duas datas iguais fazem um post nascer escondido."""
    contagem = collections.Counter(str(p["publish_date"]) for p in _posts())
    repetidas = {d: n for d, n in contagem.items() if n > 1}
    assert not repetidas, (
        "posts dividindo o mesmo dia — um vai encobrir o outro: %s"
        % {d: [p["slug"] for p in _posts() if str(p["publish_date"]) == d]
           for d in repetidas})


def test_todo_post_AINDA_NAO_publicado_cai_no_dia_da_semana_da_casa():
    """A cadência é um post por domingo. Um post que caia numa terça sai fora
    do ritmo que o leitor (e o buscador) já aprenderam.

    🪤 Só vale pro FUTURO: o que já foi ao ar em outro dia é história, não
    defeito — mexer na data de post publicado quebraria link e sitemap."""
    hoje = datetime.date.today()
    fora = [(p["slug"], p["publish_date"]) for p in _posts()
            if _data(p) > hoje and _data(p).weekday() != 6]
    assert not fora, f"post futuro fora do domingo: {fora}"


def test_CONTROLE_a_casa_publica_mesmo_aos_domingos():
    """Controle positivo: se um dia a cadência mudar de propósito, este teste
    cai primeiro e avisa que o guarda acima virou régua errada — em vez de o
    guarda reprovar a mudança legítima sem explicar por quê."""
    domingos = sum(1 for p in _posts() if _data(p).weekday() == 6)
    assert domingos >= len(_posts()) - 2, (
        "a maioria dos posts deixou de ser no domingo — se a cadência mudou, "
        "o guarda do dia da semana precisa ser reescrito, não remendado")


def test_a_fila_futura_nao_tem_BURACO_de_semana():
    """Semana sem post é o outro lado da moeda da colisão: os dois quebram a
    cadência, e o buraco é ainda mais invisível que a sobreposição.

    🪤 Avisa, não reprova o calendário inteiro: pular uma semana pode ser
    decisão (feriado, pausa). O que este guarda impede é o buraco ACIDENTAL —
    aquele que nasce quando alguém move um post e não olha o vizinho."""
    hoje = datetime.date.today()
    futuros = sorted({_data(p) for p in _posts() if _data(p) > hoje})
    saltos = [(a.isoformat(), b.isoformat(), (b - a).days)
              for a, b in zip(futuros, futuros[1:]) if (b - a).days > 7]
    assert not saltos, f"semana sem post na fila: {saltos}"
