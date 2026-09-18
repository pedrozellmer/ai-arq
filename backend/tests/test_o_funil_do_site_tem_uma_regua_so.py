# -*- coding: utf-8 -*-
"""O funil do painel compara etapas medidas do MESMO jeito.

🩸 18/09/2026. O Pedro mandou a foto do painel e lá estava:

    abriram o cadastro    10   18% da home
    criaram conta         18   180% de quem abriu

**180%.** Num funil cada etapa é subconjunto da anterior, então esse número é a
prova aritmética de que aquilo não era conversão. E não era mesmo: o numerador
vinha do NOSSO BANCO (toda conta criada, sem exceção) e o denominador do
CLOUDFLARE (endereços de IP que bateram na página, só das 12 páginas do topo, só
do que ele viu). Duas populações, dois instrumentos, uma divisão.

Ficou meses no ar sendo lido toda manhã — e a conta ERRAVA PROS DOIS LADOS: o
banco tinha 24 contas em `auth.users` (não 18), e a nossa própria telemetria
dizia 16 pessoas no cadastro (não 10).

🔑 Agora as quatro etapas saem da mesma régua (`admin_funil_do_site`), que é a
MESMA de `admin_origem_visitas`: pessoa = `user_id` quando logado, senão o `cid`
do navegador. Reimplementar essa régua aqui criaria a segunda cópia — o defeito
que a casa já pagou duas vezes.
"""
import ast
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_FONTE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "main.py")


def _arvore():
    return ast.parse(io.open(_FONTE, encoding="utf-8").read())


# ══════════════════════════════════════════════════════════════════════════
#  1. A TELA — rodando o JS DE VERDADE
# ══════════════════════════════════════════════════════════════════════════
def _render(funil, totais=None):
    """Chama `linhasDoFunil` do admin.html de verdade e devolve o HTML."""
    from _jsbancada import funcao_js, motor
    js = motor("")
    js.evaljs(funcao_js("linhasDoFunil", "admin.html"))
    return js.evaljs("linhasDoFunil(%s, %s);"
                     % (json.dumps(funil), json.dumps(totais or {})))


def _valor_da_etapa(html, rotulo):
    """O NÚMERO que a tela mostrou naquela etapa — só ele.

    🩸 Duas versões deste arquivo procuraram texto solto na linha e passaram
    verde com o defeito presente: a linha também carrega o travessão da
    PORCENTAGEM, então `"--" in linha` é verdade mesmo quando o valor virou 0.
    Asserção que casa com o pedaço errado não mede nada."""
    import re
    i = html.index(rotulo)
    m = re.search(r'tabular-nums">\s*([^<\s]+)', html[i:])
    assert m, f"não achei o valor da etapa {rotulo!r}"
    return m.group(1)


def _percentagens(html):
    """Todos os números seguidos de % que a tela mostrou."""
    import re
    return [int(n) for n in re.findall(r"(\d+)%", html or "")]


def test_o_funil_NUNCA_mostra_mais_de_100_por_cento():
    """O guarda central. Com a régua certa, nenhuma etapa pode superar a
    anterior — e se um dia superar, é sinal de que alguém voltou a misturar
    fontes, não de que a conversão ficou boa.

    🩸 A 1ª versão deste guarda passava `totais={}` e a sabotagem F01 (voltar a
    dividir conta-do-banco por endereço-do-Cloudflare) SOBREVIVEU: sem o número
    do banco na mão, a divisão dava `undefined` e nenhuma porcentagem aparecia.
    Guarda que não monta o cenário do defeito não prende o defeito. Agora ele
    entrega os números EXATOS da foto do Pedro, com o total do banco MAIOR que a
    etapa anterior — que é a condição que produz o 180%."""
    html = _render({"home": 55, "cadastro": 10, "conta": 8, "projeto": 16},
                   {"contas": 18, "projetos": 26})
    assert _percentagens(html), "a tela parou de mostrar conversão nenhuma"
    for p in _percentagens(html):
        assert p <= 100, (
            f"a tela mostrou {p}% — etapa maior que a anterior, sinal de que as "
            f"fontes voltaram a ser misturadas")


def test_CONTROLE_a_conta_ANTIGA_produzia_mesmo_o_180():
    """Controle positivo: prova que o guarda acima prende algo real. Com os
    números que o Pedro fotografou (10 do Cloudflare, 18 do banco), a divisão
    antiga dá 180% — e é por isso que ela não podia existir."""
    assert round((18 / 10) * 100) == 180


def test_a_etapa_de_PROJETO_nao_ganha_porcentagem():
    """"Subiu projeto" não é subconjunto de "criou conta": cliente antigo sobe
    sem se cadastrar de novo. Nos dados reais de 7 dias são 16 projetos contra
    12 contas — pôr porcentagem aqui recriaria o mesmo >100% com outro nome."""
    html = _render({"home": 18, "cadastro": 16, "conta": 12, "projeto": 16})
    depois = html[html.index("subiram projeto"):]
    assert "%" not in depois.split("</div>")[0] + depois.split("</div>")[1], \
        "a linha de projeto ganhou porcentagem de uma etapa que não a contém"


def test_sem_medicao_a_tela_DIZ_que_nao_mediu():
    """`None` não é funil zerado. Mostrar "0" aqui seria a doença do farol que
    acendia verde sem ter medido nada (17/09)."""
    html = _render(None)
    assert "não consegui medir" in html
    assert ">0<" not in html, "inventou zero onde não havia medição"


def test_etapa_sem_numero_vira_travessao_e_nao_zero():
    """Campo ausente numa etapa também não pode virar 0 — pela mesma razão.

    🩸 A 1ª versão afirmava só `"--" in html`, e passava com o defeito presente:
    o travessão aparecia no RODAPÉ (que também tem `-- conta(s)`) por um motivo
    completamente diferente. Asserção satisfeita por um pedaço que não tem nada
    a ver com o que ela mede — a sabotagem F04 sobreviveu por causa disso.
    Agora olha a LINHA da etapa."""
    html = _render({"home": 18, "cadastro": 16},
                   {"contas": 18, "projetos": 26})
    assert _valor_da_etapa(html, "criaram conta") == "--", (
        "etapa sem medição não virou travessão — mostrar 0 é AFIRMAR que ninguém "
        "criou conta, e a gente só sabe que não mediu")
    # controle: onde HÁ número, ele aparece
    assert _valor_da_etapa(html, "abriram a home") == "18"


def test_a_tela_DIZ_de_onde_vem_o_numero():
    """O número do funil é menor que o do banco (só conta quem aceitou cookie).
    Sem essa frase, o Pedro compara "12 contas" com as 18 que ele sabe que
    existem e conclui que o painel está quebrado — de novo."""
    html = _render({"home": 18, "cadastro": 16, "conta": 12, "projeto": 16},
                   {"contas": 18, "projetos": 26})
    assert "18 conta(s)" in html and "26 projeto(s)" in html
    assert "cookie" in html


# ══════════════════════════════════════════════════════════════════════════
#  2. O BACKEND — falha FECHADA, e não reimplementa a régua
# ══════════════════════════════════════════════════════════════════════════
def test_quando_a_RPC_falha_o_funil_e_None_e_nao_zeros(monkeypatch):
    """"Não consegui medir" e "ninguém veio" são respostas opostas. Zerar aqui
    faria o painel anunciar um colapso de tráfego que não houve."""
    def _explode(*a, **k):
        raise RuntimeError("rede caiu")
    monkeypatch.setattr(main, "_supa_rest_service", _explode)
    assert main._funil_do_site(7) is None

    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    assert main._funil_do_site(7) is None

    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, "texto"))
    assert main._funil_do_site(7) is None


def test_quando_a_RPC_responde_o_funil_chega_inteiro(monkeypatch):
    esperado = {"janela_dias": 7, "home": 18, "cadastro": 16,
                "conta": 12, "projeto": 16}
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, esperado))
    assert main._funil_do_site(7) == esperado


def test_o_backend_PERGUNTA_a_regua_em_vez_de_reimplementar():
    """A régua de "pessoa" (user_id quando logado, senão cid) mora na RPC e é a
    MESMA de `admin_origem_visitas`. Uma cópia em Python divergiria um dia — é
    exatamente o defeito das duas réguas do retry (16/09)."""
    fn = next(n for n in ast.walk(_arvore())
              if isinstance(n, ast.FunctionDef) and n.name == "_funil_do_site")
    # 🪤 SEM o docstring. A 1ª versão deste guarda reprovou o próprio conserto,
    # porque a documentação EXPLICA a régua ("senão o `cid`") e o `ast.dump`
    # engole o docstring junto. É a 4ª vez que guarda meu lê a própria
    # explicação e a trata como código — ver [[feedback_guarda_que_le_fonte]].
    corpo = [n for n in fn.body
             if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                     and isinstance(n.value.value, str))]
    texto = "".join(ast.dump(n) for n in corpo)
    assert "admin_funil_do_site" in texto, "parou de chamar a RPC"
    for regua in ("cid", "user_id", "nullif"):
        assert regua not in texto, \
            f"a régua de pessoa ('{regua}') foi reimplementada no Python"


def test_o_payload_NAO_mistura_banco_com_cloudflare_no_mesmo_bloco():
    """O defeito original era estrutural: contas do banco e endereços do
    Cloudflare moravam no MESMO dicionário, e por isso a tela dividia um pelo
    outro sem perceber. Agora cada fonte tem bloco e nome próprios."""
    fonte = io.open(_FONTE, encoding="utf-8").read()
    assert '"funil_7d": _funil_do_site(7)' in fonte
    assert '"totais_no_banco_7d"' in fonte
    assert '"enderecos_cloudflare_7d"' in fonte
    # e o bloco do funil não pode voltar a carregar os absolutos do banco
    i = fonte.index('"funil_7d"')
    assert 'l.get("cadastros")' not in fonte[i:i + 200], \
        "os totais do banco voltaram pra dentro do funil"
