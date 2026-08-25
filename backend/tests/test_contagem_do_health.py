# -*- coding: utf-8 -*-
"""As contagens do /api/health têm que ser lidas do banco, não de um except.

🚨 25/08/2026. Enquanto conferia o deploy, o `/api/health` respondeu
`"total_users": 0` — com **85 perfis** no banco. A contagem pedia
`profiles?select=id` e a tabela **não tem coluna `id`** (a chave é `user_id`).
Provado com curl na anon key, no dia:

    GET /rest/v1/profiles?select=id      → HTTP 400
       {"code":"42703","message":"column profiles.id does not exist"}
    GET /rest/v1/profiles?select=user_id → HTTP 200

O 400 caía num `except Exception: pass` e o zero ia pro ar como se fosse
medição. `total_projects` funcionava (projects TEM `id`), então o payload
parecia saudável — um número certo ao lado de um número morto.

🪤 O detalhe que faz este caso valer um guarda: três linhas acima existe um
comentário `FIX 2026-05-14` que descreve exatamente o sintoma
"total_users=0 sempre". Consertaram OUTRA causa (write-back de `locals()`),
não conferiram a SAÍDA, e o número seguiu zero por 3 meses com um comentário
dizendo que estava resolvido. Conserto que não é conferido na saída não é
conserto — é um comentário.

🚨 Por isso falha agora vira `null` e não `0`: zero é um número e se lê como
medição; `null` diz "não consegui contar".
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import corpo_de, so_o_que_roda  # noqa: E402

# Coluna que existe de verdade em cada tabela (conferido no
# information_schema em 25/08/2026).
CHAVE = {"projects": "id", "profiles": "user_id"}


def test_cada_tabela_e_contada_pela_coluna_que_ELA_tem():
    """🚨 O bug: `profiles?select=id` devolve 400 porque a coluna não existe."""
    corpo = so_o_que_roda("health")
    assert "_count_table('profiles', 'user_id')" in corpo, (
        "a contagem de profiles voltou a pedir uma coluna que a tabela não tem "
        "— o PostgREST devolve 400 e o número vai a zero")
    assert "_count_table('projects', 'id')" in corpo


def test_falha_de_contagem_nao_vira_zero():
    """Zero é um número e se lê como medição. Não consegui contar é `null`."""
    corpo = so_o_que_roda("health")
    assert "total_users = None" in corpo, (
        "a contagem voltou a nascer em 0 — falha silenciosa vira 'nenhum "
        "usuário' na cara de quem lê o painel")
    assert "total_projects = None" in corpo


def test_a_falha_da_contagem_deixa_rastro():
    """🪤 `except Exception: pass` foi o que escondeu isto por 3 meses."""
    corpo = corpo_de("health")
    i = corpo.index("def _count_table")
    trecho = corpo[i:]
    assert "except Exception: pass" not in trecho, (
        "voltou o except mudo — foi ele que engoliu o HTTP 400 do profiles")
    assert trecho.count("[health] contagem de") >= 2, (
        "as duas contagens precisam gritar quando falham")


@pytest.mark.parametrize("tabela,coluna", sorted(CHAVE.items()))
def test_controle_a_coluna_declarada_bate_com_o_codigo(tabela, coluna):
    """🧪 Se alguém trocar a coluna no código sem trocar aqui, os dois lados
    divergem em silêncio — e este arquivo vira decoração."""
    assert "_count_table('%s', '%s')" % (tabela, coluna) in so_o_que_roda("health")


def test_controle_positivo_o_guarda_PEGA_o_codigo_antigo():
    """🧪 O código exato que estava no ar até hoje de manhã."""
    antigo = """    total_projects = 0
    total_users = 0
    try:
        def _count_table(table):
            url = f"{SUPABASE_URL}/rest/v1/{table}?select=id"
        try: total_users = _count_table('profiles')
        except Exception: pass
"""
    assert "total_users = None" not in antigo
    assert "_count_table('profiles', 'user_id')" not in antigo
    assert "except Exception: pass" in antigo
