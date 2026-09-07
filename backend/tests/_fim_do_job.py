# -*- coding: utf-8 -*-
"""O FIM do `process_job` rodando de verdade — da recontagem até o e-mail.

🚨 06/09/2026. Três guardas críticos desta casa liam o FONTE pra afirmar coisas
sobre o e-mail que o cliente recebe, e os três passaram com o defeito aberto:

  · `setattr(_it, "confidence", "estimado")` depois da última recontagem — o
    e-mail volta a dizer dois números de medidos, e o juiz que só procura
    `ast.Assign` com alvo `.confidence` não vê nada;
  · `elif _n_med == 0 and len(all_items) > 0 and False:` — o terceiro e-mail
    vira código morto, a regex do guarda casa igual, e quem não mediu NADA
    volta a receber "sua planilha está pronta".

O jeito de não ser enganado é o mesmo dos dois casos: **executar**. Este módulo
recorta a fatia real do `process_job` — do `_recontar_aviso_planob()` final até
o `_send_email_smtp` da planilha pronta — e roda com rede, banco, planilha e
SMTP injetados. O que se confere é o E-MAIL montado.

🪤 Recorte por ÂNCORA dentro do intervalo que o AST diz ser a função. Nunca por
tamanho fixo (25/08: janela fixa mede o vizinho ou mede meio guarda), e não dá
pra usar `corpo_de` aqui — nesta função ele para dentro de uma f-string de
várias linhas e denuncia isso sozinho.

🪤 O bloco do e-mail fala com o banco por `urllib.request.urlopen` DIRETO, sem
passar por `_supa_rest_service`. Quem patchar só o helper não intercepta nada e
vê tudo vazio parecendo vazio de verdade.
"""
import ast
import io
import json
import os
import sys
import tempfile
import textwrap
import urllib.request

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_ANCORA_FIM = 'print(f"[email] planilha-pronta nao enviada (nao-fatal): {_ee}")'
_NIVEL_DO_CORPO = 8          # indentação das instruções do process_job


def fatia_do_fim_do_process_job():
    """Da recontagem final ao e-mail — o pedaço real, pronto pra executar.

    🪤 O começo NÃO é uma string fixa. Se fosse, quem pusesse a recontagem sob
    um `if False:` quebraria a âncora e o guarda reprovaria dizendo "o recorte
    mudou" em vez de "o cliente lê dois números" — mensagem errada pro defeito
    certo, que é meio caminho pra alguém "consertar" o teste. Aqui a gente acha
    a ÚLTIMA chamada da recontagem e sobe até a instrução que a contém.
    """
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    linhas = src.splitlines(True)
    achados = [n for n in ast.walk(ast.parse(src))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "process_job"]
    assert len(achados) == 1, "process_job sumiu ou virou duas definições"
    do_corpo = linhas[achados[0].lineno - 1:achados[0].end_lineno]
    corpo = "".join(do_corpo)
    chamadas = [k for k, l in enumerate(do_corpo)
                if "_recontar_aviso_planob()" in l
                and not l.lstrip().startswith(("def ", "#"))]
    assert chamadas, "a recontagem do aviso do plano B não é chamada em lugar nenhum"
    k = chamadas[-1]
    while k >= 0:
        l = do_corpo[k]
        if l.strip() and not l.lstrip().startswith("#") \
                and (len(l) - len(l.lstrip())) == _NIVEL_DO_CORPO:
            break
        k -= 1
    assert k >= 0, "não achei a instrução que contém a recontagem final"
    i = len("".join(do_corpo[:k]))
    assert corpo.count(_ANCORA_FIM) == 1, (
        "a âncora do fim da fatia deixou de ser única dentro do process_job — "
        "reveja o recorte antes de confiar nos guardas que dependem dele")
    j = corpo.index("\n", corpo.index(_ANCORA_FIM, i)) + 1
    fatia = textwrap.dedent(corpo[i:j])
    # Controles de que o recorte é o pedaço certo, e inteiro.
    for marca in ("_recontar_aviso_planob()", "_build_planilha_pronta_email(",
                  "_build_leu_sem_medir_email(", "_build_sem_medida_email(",
                  "_send_email_smtp("):
        assert marca in fatia, "a fatia não contém %s" % marca
    return fatia


def _recontagem_real():
    """A `_recontar_aviso_planob` REAL (é aninhada dentro do process_job)."""
    from _corpo import corpo_de
    return textwrap.dedent(corpo_de("_recontar_aviso_planob"))


class ProjetoFake(object):
    """O mínimo de `project_data` que a fatia toca."""

    def __init__(self, warnings=None, total_area=None, layout_area=None):
        self.warnings = list(warnings or [])
        self.total_area = total_area
        self.layout_area = layout_area


def _resposta_fake(payload):
    class _R(object):
        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    return _R()


def roda_ate_o_email(itens, cab_planob=None, medidos_antes=None, avisos=None,
                     project_type="", n_pdf=0, n_cad=1,
                     email="cliente-nn@example.com",
                     nome_projeto="projeto de teste", job_id="job-teste",
                     antes_do_email=None, is_complement=False,
                     partial_failure=False, partial_errors=None,
                     dwg_failed=None):
    """Executa a fatia real e devolve o diário do que o cliente receberia.

    `cab_planob` — planta o aviso do plano B como o motor o escreve, lá em cima
    (~linha 11344), e deixa a recontagem final reescrevê-lo.
    `medidos_antes` — a contagem que o aviso trazia ANTES dos rebaixamentos.
    🔑 Por padrão vem DESATUALIZADA de propósito (um a mais que a contagem
    real): assim a recontagem final tem trabalho a fazer, e sumir com ela — ou
    pô-la sob um `if False:` — deixa os dois números do e-mail em desacordo.
    `antes_do_email` — ganchos extras no namespace (pra espionar itens).

    🔑 06/09 — `is_complement`, `partial_failure`, `partial_errors` e
    `dwg_failed` deixaram de ser constantes escondidas aqui dentro. Enquanto
    eram, TODO guarda que usa este harness media um cenário só (só CAD,
    arquitetura, sem falha parcial) — e um rebaixamento de selo que só
    acontecesse em job com PDF, complemento ou falha parcial ficava invisível.
    """
    import main

    proj = ProjetoFake(warnings=list(avisos or []))
    aviso_idx = None
    if cab_planob is not None:
        _n_real = sum(1 for i in itens
                      if getattr(i, "confidence", None) == "confirmado")
        _n_antes = _n_real + 1 if medidos_antes is None else medidos_antes
        proj.warnings.append(
            cab_planob + ("As medições saíram (%d item(ns) medido(s) do CAD), "
                          "mas vale conferir 2-3 medidas-chave contra o projeto "
                          "antes de fechar orçamento." % _n_antes))
        aviso_idx = len(proj.warnings) - 1

    diario = {"emails": [], "logs": [], "planilhas": [], "subiu": None}
    work_dir = tempfile.mkdtemp(prefix="fim_do_job_")
    caminhos = ([os.path.join(work_dir, "p%d.pdf" % k) for k in range(n_pdf)]
                + [os.path.join(work_dir, "c%d.dxf" % k) for k in range(n_cad)])

    class _Jobs(object):
        def update_field(self, *a, **k):
            return None

    def _gen(project_data, all_items, path, typology=None):
        diario["planilhas"].append(path)
        io.open(path, "w", encoding="utf-8").write("planilha")

    def _envia(destino, assunto, html, log_kind=None, **k):
        diario["emails"].append({"para": destino, "assunto": assunto,
                                 "html": html, "kind": log_kind})
        return True

    ns = {
        "__name__": "fim_do_job_ns", "os": os, "datetime": main.datetime,
        "_json": json,
        # ── estado do job ────────────────────────────────────────────────
        "job_id": job_id, "work_dir": work_dir, "typology": None,
        "cad_paths": [], "project_data": proj, "all_items": itens,
        "file_paths": caminhos,
        "dxf_paths": [p for p in caminhos if p.endswith(".dxf")],
        "project_type": project_type, "is_complement": is_complement,
        "partial_failure": partial_failure,
        "partial_errors": list(partial_errors or []), "_saida": "",
        "dwg_failed": list(dwg_failed or []),
        "_aec_failed": False, "_dwg_sem_irmao": [],
        "_aviso_lw_idx": aviso_idx, "_aviso_lw_cab": cab_planob or "",
        "jobs": _Jobs(),
        # ── credenciais de mentira (a rede está patchada) ────────────────
        "SUPABASE_URL": "https://exemplo.invalid",
        "SUPABASE_KEY": "anon-de-mentira",
        "SUPABASE_SERVICE_ROLE_KEY": "service-de-mentira",
        # ── o que fala com rede/banco/disco: injetado ────────────────────
        "generate_spreadsheet": _gen,
        "_carimbar_spec": lambda *a, **k: None,
        "_carimbar_planilha": lambda *a, **k: None,
        "_carimbar_regua_de_cobranca": lambda *a, **k: None,
        "_supa_rest_service": lambda m, p, **k: (200, [{"parent_job_id": None}]),
        "_fundir_revisoes_do_cliente": lambda its, pai: (its, {}),
        "_persist_items_to_supabase": lambda j, its: len(its),
        "_comparar_com_versao_anterior": lambda *a, **k: {},
        "_supabase_update": lambda *a, **k: True,
        "_avisos_com": lambda j, avisos_: list(avisos_),
        "_supabase_storage_upload": lambda p, n: diario.__setitem__("subiu", p) or True,
        "_ckpt_limpar": lambda *a, **k: None,
        "_resolve_client_name": lambda mail, hint="": (hint or "cliente-nn"),
        "_email_auto_ja_enviado": lambda *a, **k: False,
        "_email_auto_registrar": lambda *a, **k: None,
        "_send_email_smtp": _envia,
        "_log_error": lambda *a, **k: diario["logs"].append(
            " ".join(str(x) for x in a)),
        # ── as vozes do e-mail: as REAIS, é o que se está medindo ────────
        "_build_reading_diagnostic": main._build_reading_diagnostic,
        "_next_steps_html": main._next_steps_html,
        "_origem_das_quantidades": main._origem_das_quantidades,
        "_build_sem_medida_email": main._build_sem_medida_email,
        "_build_leu_sem_medir_email": main._build_leu_sem_medir_email,
        "_build_planilha_pronta_email": main._build_planilha_pronta_email,
        "_email_wrap": main._email_wrap,
        "_greeting_line": main._greeting_line,
        "voz_do_email_de_reprocesso": main.voz_do_email_de_reprocesso,
    }
    ns.update(antes_do_email or {})
    exec(compile(_recontagem_real(), "recontagem", "exec"), ns)

    _urlopen_real = urllib.request.urlopen
    urllib.request.urlopen = lambda req, **k: _resposta_fake([{
        "user_email": email, "user_name": "cliente-nn",
        "project_name": nome_projeto, "reprocess_count": 0}])
    try:
        exec(compile(fatia_do_fim_do_process_job(), "fim_do_job", "exec"), ns)
    finally:
        urllib.request.urlopen = _urlopen_real

    # 🪤 A fatia inteira mora dentro de `try/except` que engolem e seguem. Se o
    # harness estiver quebrado, o teste veria "nenhum e-mail" e chamaria isso de
    # defeito do produto. Denuncia aqui.
    assert diario["emails"], (
        "nenhum e-mail foi montado — o harness quebrou antes de chegar lá. "
        "logs=%r" % (diario["logs"],))
    diario["project_data"] = proj
    diario["ns"] = ns
    return diario


def medidos_no_placar(html):
    """O número que o CABEÇALHO do e-mail afirma ('✓ N medido(s)')."""
    import re
    m = re.search(r"&#10003;\s*(\d+)\s*medido\(s\)", html)
    return int(m.group(1)) if m else None


def medidos_no_aviso(html):
    """O número que o AVISO do plano B afirma, dentro do mesmo e-mail."""
    import re
    m = re.search(r"medi[çc][õo]es sa[íi]ram \((\d+) item", html)
    return int(m.group(1)) if m else None
