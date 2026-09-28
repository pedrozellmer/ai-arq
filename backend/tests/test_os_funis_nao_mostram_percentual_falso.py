# -*- coding: utf-8 -*-
"""Os funis do painel só mostram % entre etapas que se contêm.

🩸 27/09/2026 — auditoria de telemetria, item 3. Três funis do painel dividiam
conjuntos que não se contêm:

  · funil do site (Dashboard): "abriram o cadastro 24 · ~86% da home", mas só 4
    dos 24 tinham passado pela home. A pessoa era o user_id logada e o navegador
    deslogada; quem abre a home deslogado e volta do login pro cadastro virava
    DUAS pessoas. Por navegador (todo evento leva o cid): 28 na home, 26 no
    cadastro, 19 nos dois — 68%.
  · funil da Atividade: "68 abriram o cadastro · 96% da landing", "53
    completaram · 75% da landing" — só 41 e 33 tinham passado pela landing.
  · funil da revisão: a etapa 5 contava LINHA de planilha (57), não projeto
    (26), e saía maior que as etapas 3 e 4.

🔑 % só sobre a INTERSEÇÃO por navegador; conta e projeto do BANCO (todos, sem
cookie) e sem % sobre as linhas de evento; revisão por projeto distinto, raiz,
desde 03/08. A prova do SQL foi o ensaio no banco (bloco desfeito) e a
conferência depois de aplicar; aqui o que se confere do SQL é o arquivo.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
from _jsbancada import funcao_js, motor  # noqa: E402
# a régua de "lê o e-mail do evento?" é a da LGPD — não reimplementar
from test_usage_events_sem_email import _funcoes, _le_email_do_evento, _sem_comentario  # noqa: E402

_BACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIG = os.path.join(_BACK, "migrations_pendentes", "funis_sem_percentual_falso.sql")


def _chama(nome, chamada):
    js = motor("")
    js.evaljs(funcao_js(nome, "admin.html"))
    return js.evaljs(chamada)


def _site(funil, totais=None):
    return _chama("linhasDoFunil", "linhasDoFunil(%s, %s);"
                  % (json.dumps(funil), json.dumps(totais or {})))


def _atividade(d):
    return _chama("htmlFunilDaAtividade", "htmlFunilDaAtividade(%s);" % json.dumps(d))


def _pcts(html):
    return [int(n) for n in re.findall(r"(\d+)%", html or "")]


def _linha(html, rotulo):
    i = html.index(rotulo)
    return html[i:html.index("</div>", i)]


# ══════════════════════════════════════════════════════════════════════════
#  1. Funil do site (Dashboard)
# ══════════════════════════════════════════════════════════════════════════
_MEDIDO_27_09 = {"home": 30, "cadastro": 26, "conta": 20, "projeto": 24,
                 "home_nav": 28, "cadastro_nav": 26, "cadastro_pela_home_nav": 19}


def test_o_percentual_da_home_e_o_da_INTERSECAO_por_navegador():
    html = _site(_MEDIDO_27_09, {"contas": 18, "projetos": 26})
    assert "68%" in _linha(html, "abriram o cadastro"), _linha(html, "abriram o cadastro")
    assert "19 vieram da home" in html
    assert _pcts(html) == [68], "apareceu %% que não é o da interseção: %r" % _pcts(html)


def test_CONTROLE_a_conta_de_antes_dava_93_e_86():
    """O que a tela dividia antes: cadastro ÷ home, conjuntos que não se contêm."""
    assert round(26 / 28 * 100) == 93 and round(24 / 28 * 100) == 86


def test_sem_os_campos_de_navegador_NENHUM_percentual():
    """RPC antiga (sem *_nav): melhor nenhum % que um que mente."""
    html = _site({"home": 30, "cadastro": 26, "conta": 20, "projeto": 24},
                 {"contas": 18, "projetos": 26})
    assert _pcts(html) == [], _pcts(html)
    assert ">30<" in html and ">26<" in html, "sem os campos novos, a tela perdeu os números"


def test_o_que_vem_do_banco_NUNCA_ganha_percentual():
    html = _site(_MEDIDO_27_09, {"contas": 18, "projetos": 26})
    for rot in ("fizeram o cadastro", "subiram projeto"):
        assert "%" not in _linha(html, rot), (rot, _linha(html, rot))
        assert "banco" in _linha(html, rot), "a linha do banco não diz de onde vem"


# ══════════════════════════════════════════════════════════════════════════
#  2. Funil da Atividade
# ══════════════════════════════════════════════════════════════════════════
_ATIV = {"funnel": {"view_landing": 71, "view_cadastro": 68, "signup_done": 53},
         "funnel_cruzado": {"cadastro_pela_landing": 41},
         "by_event": {"signup_created": 30}}


def test_atividade_o_percentual_e_o_da_intersecao():
    html = _atividade(_ATIV)
    assert "41 vieram da landing" in html and "58% da landing" in html, html
    assert _pcts(html) == [58], "apareceu %% fora da interseção: %r" % _pcts(html)


def test_CONTROLE_atividade_a_conta_de_antes_dava_96_e_75():
    assert round(68 / 71 * 100) == 96 and round(53 / 71 * 100) == 75


def test_atividade_a_conta_vem_do_banco_sem_percentual():
    html = _atividade(_ATIV)
    i = html.index("bg-emerald-50")
    card = html[i:html.index("</div>", i)]
    assert ">30<" in card and "criaram conta" in card and "no banco" in card, card
    assert "%" not in card, card


def test_atividade_sem_cruzamento_NENHUM_percentual():
    d = dict(_ATIV)
    d.pop("funnel_cruzado")
    assert _pcts(_atividade(d)) == []


def test_a_rota_da_Atividade_manda_a_intersecao_por_navegador(monkeypatch):
    """Navegador A passou pela landing e pelo cadastro; B só pelo cadastro;
    C só pela landing. A interseção é 1 — e não 2/2 = 100%."""
    def _ev(ev, cid, quando="2026-09-20T10:00:00Z"):
        return {"event": ev, "user_email": "", "user_id": "", "job_id": "",
                "path": "", "meta": {"cid": cid}, "created_at": quando}
    eventos = [_ev("view_landing", "A"), _ev("view_cadastro", "A"),
               _ev("view_cadastro", "B"), _ev("view_landing", "C")]

    def _tudo(path, params=None, **k):
        return (200, list(eventos)) if path == "usage_events" else (200, [])
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: [])
    monkeypatch.setattr(main, "_usage_events_por_nome", lambda dias=365: [])
    d = main.admin_activity(object(), days=30, limit=50)
    assert d["funnel"]["view_landing"] == 2 and d["funnel"]["view_cadastro"] == 2
    assert d["funnel_cruzado"] == {"cadastro_pela_landing": 1}, d["funnel_cruzado"]


# ══════════════════════════════════════════════════════════════════════════
#  3. O SQL (arquivo da migração)
# ══════════════════════════════════════════════════════════════════════════
def test_a_migracao_traz_as_duas_funcoes_com_dono_e_search_path():
    fs = _funcoes(_MIG)
    assert set(fs) == {"admin_funil_do_site", "funil_revisao"}, sorted(fs)
    for nome, (cab, _c) in fs.items():
        assert "SECURITY DEFINER" in cab and "SET search_path TO 'public'" in cab, nome


def test_o_funil_do_site_nao_le_email_do_evento_e_mantem_a_regua_do_dono():
    """LGPD (27/09): quem é a pessoa sai da CONTA, nunca do e-mail do evento. E o
    dono é a régua de hoje — Pedro, 27/09: "mantém a régua de hoje"."""
    corpo = _funcoes(_MIG)["admin_funil_do_site"][1]
    assert _le_email_do_evento(corpo) == [], _le_email_do_evento(corpo)
    assert "split_part((public.emails_da_casa())[1], '@', 1)" in corpo
    txt = open(_MIG, encoding="utf-8").read()
    assert not re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", txt), "e-mail escrito no repo público"
    assert not re.search(r"\bdrop\b", _sem_comentario(txt), re.I)


def test_o_cruzamento_do_site_e_por_NAVEGADOR():
    corpo = _sem_comentario(_funcoes(_MIG)["admin_funil_do_site"][1])
    assert "u.meta->>'cid' as nav" in corpo, "o cruzamento deixou de ser por navegador"
    assert re.search(r"'cadastro_pela_home_nav'.*?intersect", corpo, re.S)


def test_o_funil_da_revisao_conta_PROJETO_distinto_raiz_desde_03_08():
    corpo = _sem_comentario(_funcoes(_MIG)["funil_revisao"][1])
    # (o `count(*) filter` do CTE `acoes` conta AÇÕES por projeto — legítimo)
    assert "count(*)::bigint" not in corpo, "voltou a contar linha em vez de projeto"
    assert corpo.count("count(distinct b.job_id)") == 5, "alguma etapa não conta projeto distinto"
    assert "p.parent_job_id is null" in corpo, "reprocesso voltou a contar como projeto"
    assert "timestamptz '2026-08-03 00:00:00-03'" in corpo, "perdeu o piso de 03/08"


def test_CONTROLE_a_regra_do_count_REPROVA_a_etapa_5_de_antes():
    antiga = ("select 'planilha revisada enviada', 5,\n count(*)::bigint, "
              "count(distinct b.user_id)::bigint\n from base b join revision_feedback rf")
    assert "count(*)::bigint" in _sem_comentario(antiga)


def test_a_tela_da_revisao_diz_a_janela():
    adm = open(os.path.join(os.path.dirname(_BACK), "admin.html"), encoding="utf-8").read()
    corpo = funcao_js("loadFunilRevisao", "admin.html", adm)
    assert "desde 03/08" in corpo and "Cada etapa conta projeto" in corpo
