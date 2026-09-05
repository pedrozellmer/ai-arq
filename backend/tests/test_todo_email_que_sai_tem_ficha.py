# -*- coding: utf-8 -*-
"""Todo e-mail que SAI pro cliente tem ficha na Central de E-mails — e etiqueta.

🔬 05/09/2026. O Pedro abriu a aba E-mails do admin no celular e viu cinco
cartões "fora do catálogo": `email` (112), `leitura_nova` (8),
`boas_vindas_cadastro` (6), `sem_medida` (3), `leitura_combinada` (1).
Medido em email_sent_log: quatro eram e-mails legítimos que NASCERAM depois do
catálogo (variantes de 14/08, 23/08, 24/08, 26/08) e nunca ganharam ficha; o
quinto era um BALDE — newsletter (101), complemento (9) e reprocesso (2) saíam
sem `log_kind` e caíam no default "email".

Regra daqui em diante (coberta por NOME, não por contagem):
  1. todo `log_kind` que o motor usa tem ficha em `_EMAIL_CATALOG`;
  2. nenhuma chamada de `_send_email_smtp` pra CLIENTE sai sem `log_kind` — as
     internas (NOTIFY_EMAIL / ADMIN_EMAIL) não entram no log e ficam de fora;
  3. ficha com preview renderiza pelo MESMO builder do envio; ficha sem preview
     diz o motivo (`_SemPreview`) em vez de "tipo desconhecido".
🧪 Controles positivos: os guardas reprovam chamada sem etiqueta e ficha faltando.
"""
import ast
import os
import re
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

_SRC = sem_comentarios(fonte("main.py"))
_CHAVES = {c["key"] for c in main._EMAIL_CATALOG}
_INTERNOS = {"NOTIFY_EMAIL", "ADMIN_EMAIL"}


def _kinds_usados(src):
    """Etiquetas que o fonte passa em `log_kind=`. Pega o literal logo depois de
    `log_kind=` E o do `else` (ternário `"a" if x else "b"`), e ignora o default
    do próprio `def _send_email_smtp` e fallbacks dentro de `.get(...)`."""
    usados = set()
    for linha in src.splitlines():
        if "log_kind=" in linha and "def _send_email_smtp" not in linha:
            usados.update(re.findall(r'(?:log_kind=|else )"([a-z_]+)"', linha))
    return usados


def _chamadas_sem_etiqueta(src):
    """[(função, linha)] de cada `_send_email_smtp(...)` sem `log_kind=` cujo
    destinatário não é um nome interno (NOTIFY_EMAIL / ADMIN_EMAIL)."""
    arv = ast.parse(src)
    ruins = []
    for fn in arv.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for no in ast.walk(fn):
            if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                    and no.func.id == "_send_email_smtp"):
                continue
            if any(k.arg == "log_kind" for k in no.keywords):
                continue
            alvo = no.args[0] if no.args else None
            if isinstance(alvo, ast.Name) and alvo.id in _INTERNOS:
                continue
            ruins.append((fn.name, no.lineno))
    return ruins


# ── 1. toda etiqueta tem ficha ─────────────────────────────────────────────
def test_todo_log_kind_que_o_motor_usa_tem_ficha():
    usados = _kinds_usados(_SRC) | set(main._NUDGE_LOG_KIND.values())
    sem_ficha = sorted(usados - _CHAVES)
    assert not sem_ficha, f"e-mail sai com etiqueta SEM ficha na Central: {sem_ficha}"


def test_os_fora_do_catalogo_de_05_09_tem_ficha():
    for k in ("sem_medida", "boas_vindas_cadastro", "leitura_nova", "leitura_combinada",
              "newsletter", "complemento_pronto", "reprocesso_pronto"):
        assert k in _CHAVES, k


# ── 2. nenhum e-mail pro cliente sai sem etiqueta ──────────────────────────
def test_nenhum_email_pro_cliente_sai_sem_etiqueta():
    # `email_preview` é a única exceção: rota de debug com destinatário FIXO
    # interno (conferido no teste abaixo) — o e-mail nem entra no log.
    ruins = [r for r in _chamadas_sem_etiqueta(_SRC) if r[0] != "email_preview"]
    assert not ruins, f"_send_email_smtp sem log_kind — cai no balde 'email': {ruins}"


def test_a_excecao_email_preview_manda_so_pro_dono():
    i = _SRC.find("async def email_preview(")
    assert i > 0, "a rota de debug mudou de nome — revisar a exceção do guarda"
    assert "to = NOTIFY_EMAIL" in _SRC[i:i + 600], (
        "a exceção do guarda só vale se o destinatário for FIXO e interno")


def test_os_tres_que_caiam_no_balde_agora_levam_a_etiqueta_do_gate():
    # a etiqueta do email_sent_log é a MESMA do gate em email_auto_log —
    # dois logs, um nome; senão a Central e a esteira contam coisas diferentes.
    for kind in ("complemento_pronto", "reprocesso_pronto"):
        assert f'log_kind="{kind}"' in _SRC, kind
        assert f'_email_auto_registrar(_pe, "{kind}"' in _SRC, kind
    i = _SRC.find("def _newsletter_blast(")
    assert i > 0
    assert 'log_kind="newsletter"' in _SRC[i:i + 1500], "a newsletter voltou a sair sem etiqueta"


# ── 3. preview pelo mesmo builder; sem preview diz o motivo ────────────────
@pytest.mark.parametrize("ficha", main._EMAIL_CATALOG, ids=lambda c: c["key"])
def test_toda_ficha_com_preview_renderiza_e_sem_preview_diz_por_que(ficha):
    if ficha.get("sem_preview"):
        with pytest.raises(main._SemPreview) as ex:
            main._render_email_by_type(ficha["key"])
        assert ficha["sem_preview"] in str(ex.value)
        return
    subj, html = main._render_email_by_type(ficha["key"])
    assert subj and len(html) > 1000, f"{ficha['key']} não renderiza no preview"
    assert not re.findall(r'href="[^"]*obrigado\.html\?[^"]*"', html), (
        f"{ficha['key']}: o preview leva link de nota VÁLIDO (regra de 31/08)")


def test_sem_preview_e_uma_KeyError_pra_quem_nao_sabe_distinguir():
    assert issubclass(main._SemPreview, KeyError)


def test_o_texto_de_cada_email_mora_num_lugar_so():
    """Preview e envio pelo MESMO builder: a frase-chave aparece UMA vez no fonte."""
    for frase in ("Li o que você enviou, mas <b>não consegui medir nada do",
                  "refizemos a leitura do seu",
                  "Montamos uma <b>vers&atilde;o combinada</b>"):
        assert _SRC.count(frase) == 1, f"texto duplicado ou sumido: {frase!r} ×{_SRC.count(frase)}"
    # def + chamada no process_job + chamada no preview
    assert _SRC.count("_build_sem_medida_email(") == 3, "o envio ou o preview deixou de usar o builder"


def test_sem_medida_builder_diz_os_numeros_e_leva_a_avaliacao_viva():
    subj, html = main._build_sem_medida_email("Pedro", "Obra X", "job-1", 30, 27, "",
                                              email="cliente@exemplo.com")
    assert subj == "Obra X — não consegui medir esse arquivo"
    assert "27 das 30 linhas" in html and "Sem medida" in html
    assert "obrigado.html" in html, "o envio REAL leva o link de nota vivo (só o preview neutraliza)"
    subj2, _ = main._build_sem_medida_email("Pedro", "", "job-1", 30, 27, "", email="c@e.com")
    assert subj2 == "Não consegui medir esse arquivo"


def test_leitura_nova_e_combinada_mostram_o_que_piorou_no_exemplo():
    for k in ("leitura_nova", "leitura_combinada"):
        _s, html = main._render_email_by_type(k)
        assert "piorou" in html, f"{k}: o exemplo perdeu o quadro de honestidade dos dois lados"


# ── controles positivos ────────────────────────────────────────────────────
def test_CONTROLE_o_guarda_ve_chamada_sem_etiqueta():
    ruim = "def f(email):\n    _send_email_smtp(email, 's', 'h')\n"
    ok1 = "def g():\n    _send_email_smtp(NOTIFY_EMAIL, 's', 'h')\n"
    ok2 = "def h(email):\n    _send_email_smtp(email, 's', 'h', log_kind='x')\n"
    assert _chamadas_sem_etiqueta(ruim) == [("f", 2)]
    assert _chamadas_sem_etiqueta(ok1) == []
    assert _chamadas_sem_etiqueta(ok2) == []


def test_CONTROLE_ficha_faltando_e_vista():
    usados = _kinds_usados('x = _send_email_smtp(e, s, h, log_kind="fantasma" if a else "boas_vindas")\n')
    assert usados == {"fantasma", "boas_vindas"}
    assert "fantasma" not in _CHAVES
    assert _kinds_usados('log_kind=_NUDGE_LOG_KIND.get(kind, "nudge")\n') == set(), (
        "fallback dentro de .get() não é etiqueta em uso")
