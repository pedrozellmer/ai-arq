# -*- coding: utf-8 -*-
"""financeiro.html entra no site pelas regras da casa — e fala a língua do backend.

05/09/2026, terceiro pedaço do Financeiro da obra (tabela → rotas → TELA). Quatro
leitores levantaram o que uma página nova precisa; este arquivo cobra cada regra
com o FATO na mão:
  • shell: /tailwind.min.css (build ESTÁTICO; o CDN da maquete violaria a CSP),
    supabase-js do jsdelivr com integrity, aiarq-utils.js, menu-lateral.js, sem o
    <aside> estático da maquete (o componente desiste se já existe #aiarq-side),
    noindex, aceita ?job_id= e ?job=;
  • Tailwind: TODA classe usada existe no build OU é definida no <style> da
    página (reference_tailwind_build_estatico: classe nova é inerte, sem erro);
  • contrato: origens quantitativo/comparativo/livre (não os quant/comp da
    maquete), PATCH/DELETE com método explícito, pago manda pago_em, valor
    apagado em linha paga manda status junto, valor vazio é null (nunca 0);
  • sem colisões: nenhuma `function toast(` (toast.js define window.toast);
  • menu-lateral.js tem Financeiro entre Cronograma e Memorial; view_financeiro
    está na allowlist do /api/track; /quotes devolve `items` (o modal precisa).
🧪 Controle: o detector de classe reprova uma classe plantada que não existe.
"""
import io
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

from _corpo import fonte, sem_comentarios  # noqa: E402

HTML = fonte("financeiro.html")
MENU = fonte("menu-lateral.js")
MAIN = sem_comentarios(fonte("main.py"))
CSS = io.open(os.path.join(_RAIZ, "tailwind.min.css"), encoding="utf-8").read()
BARRA = chr(92)


def _js(html=HTML):
    return "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))


def _style(html=HTML):
    return "\n".join(re.findall(r"<style>(.*?)</style>", html, re.S))


# ── o shell ────────────────────────────────────────────────────────────────
def test_usa_o_build_estatico_e_nao_o_cdn_da_maquete():
    assert '<link rel="stylesheet" href="/tailwind.min.css">' in HTML
    assert "cdn.tailwindcss.com" not in HTML, "o Play CDN não está na CSP (script-src) — a página sairia sem estilo"


def test_scripts_da_casa_na_ordem_e_com_a_tag_exata_do_supabase():
    tag = ('<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.112.3/dist/umd/supabase.js" '
           'integrity="sha384-qafw21c/iciq0VXsi9FzkfoQv5I/V0iqE4lSNcKXPnW9/UTJLnv5CcN4FHxVLnKg" '
           'crossorigin="anonymous"></script>')
    assert tag in HTML, "o guarda de páginas (pre-push) procura esta tag literal pra dublar o supabase"
    i1 = HTML.find(tag)
    i2 = HTML.find('<script src="aiarq-utils.js"></script>')
    i3 = HTML.find('<script src="menu-lateral.js"></script>')
    i4 = HTML.find("const API_BASE = window.API_BASE;")
    assert 0 < i1 < i2 < i3 < i4, "ordem: supabase → aiarq-utils → menu-lateral → script da página"


def test_nao_copia_o_menu_estatico_da_maquete():
    assert 'id="aiarq-side"' not in HTML and 'id="aiarq-scrim"' not in HTML and 'id="aiarq-burger"' not in HTML, (
        "menu-lateral.js desiste se já existe #aiarq-side — o menu fake ficaria com href='#'")
    assert "function abrirMenu" not in HTML and "function fecharMenu" not in HTML


def test_pagina_logada_noindex_e_aceita_os_dois_nomes_de_job():
    assert '<meta name="robots" content="noindex,follow">' in HTML
    assert "params.get('job_id') || params.get('job')" in HTML
    assert "login.html?redirect=financeiro.html?job_id=" in HTML


def test_nao_define_o_que_faz_o_menu_interceptar_ou_virar_painel():
    assert "mostrarVista" not in HTML
    assert "tab-content" not in HTML
    assert "checkAdminAccess" not in HTML


# ── Tailwind: toda classe usada existe no build ou no <style> da página ───
def _classes_usadas(html):
    usadas = set()
    for m in re.finditer(r'class=\\?"([^"\\]*)\\?"', html):
        for t in m.group(1).split():
            if "${" in t or t.startswith("$") or "'" in t or "}" in t:
                continue
            usadas.add(t)
    return usadas


def _no_build(cls):
    esc_ = re.sub(r"([^A-Za-z0-9_-])", lambda mm: BARRA + mm.group(1), cls)
    sel = "." + esc_
    return any((sel + fim) in CSS for fim in ("{", ":", ",", " ", ">"))


def _no_style_da_pagina(cls, style):
    esc_ = re.sub(r"([^A-Za-z0-9_-])", lambda mm: BARRA + mm.group(1), cls)
    return ("." + esc_) in style or ("." + cls) in style


_GANCHOS_JS = {"corpo", "f-data", "f-fase", "f-quando", "v-data", "v-fase", "n", "lg", "nx",
               "exp", "chev", "rise", "cell", "vazio", "ro", "row", "cat", "in", "money", "acao",
               "ok", "del", "status", "pop", "rd", "on", "lbl", "dot", "src", "cron", "semdata",
               "kpi", "kpi-ico", "kpi-ok", "kpi-alerta", "tabular", "fin", "fin-chip", "fin-toast",
               "cb-list", "cb-grp", "cb-opt", "cb-novo", "cb-wrap", "cb-tog", "clamp2", "truncate1",
               "tbl-wrap", "c-forn", "th-forn", "td-forn", "forn-sub", "chart-txt", "gradient-main",
               "in-lg", "salvando", "erro"}


def test_toda_classe_da_pagina_existe_no_build_ou_no_style_proprio():
    assert _no_build("max-w-6xl") and not _no_build("mb-73"), "detector quebrado (controles)"
    style = _style()
    inertes = sorted(c for c in _classes_usadas(HTML)
                     if c not in _GANCHOS_JS and not c.startswith(("st-", "text-", "bg-", "border-", "hover:", "md:", "sm:"))
                     and not _no_build(c) and not _no_style_da_pagina(c, style))
    # as de cor/variante passam pelo mesmo crivo, sem a lista de ganchos
    inertes += sorted(c for c in _classes_usadas(HTML)
                      if c.startswith(("text-", "bg-", "border-", "hover:", "md:", "sm:"))
                      and not _no_build(c) and not _no_style_da_pagina(c, style)
                      and c not in ("st-semvalor",))
    assert not inertes, f"classes que não pintam (nem no build, nem no <style>): {inertes}"


def test_CONTROLE_classe_plantada_inexistente_e_pega():
    html = HTML.replace('class="tbl-wrap"', 'class="tbl-wrap mb-73"', 1)
    assert "mb-73" in _classes_usadas(html) and not _no_build("mb-73") and not _no_style_da_pagina("mb-73", _style())


def test_as_14_classes_ausentes_do_build_estao_no_style_da_pagina():
    style = _style()
    for c in ("flex-nowrap", "gap-x-3", "grid-cols-[1fr_auto]", "group-open:rotate-90", "md:px-4",
              "normal-case", "pr-8", "rounded-tl-lg", "rounded-tr-lg", "text-[11.5px]", "text-[12.5px]",
              "text-[13px]", "tracking-normal", "w-fit"):
        assert not _no_build(c), f"{c} passou a existir no build — pode sair do <style> da página"
        assert _no_style_da_pagina(c, style), f"{c} não está no build nem no <style> da página"


# ── o contrato com o backend ───────────────────────────────────────────────
def test_fala_a_lingua_do_backend_nas_origens():
    js = _js()
    assert 'SRC_API = {quant:"quantitativo", comp:"comparativo", livre:"livre"}' in js
    assert "origem:SRC_API[ORIGEM]" in js or "origem: SRC_API[ORIGEM]" in js
    assert 'origem:SRC_API[l.src]' in js, "o Desfazer recria pela API — mesma língua"


def test_toda_escrita_tem_metodo_explicito_e_uma_funcao_so_fala_com_a_api():
    js = _js()
    assert "async function api(method, caminho, corpo)" in js
    assert "`${API_BASE}/api/financeiro/${jobId}${caminho}`" in js
    for m in ("'PATCH'", "'DELETE'", "'POST'", "'GET'"):
        assert f"api({m}" in js, f"faltou a chamada {m}"
    assert "/api/financeiro" in HTML, "a catraca de rotas órfãs conta por esta string"


def test_marcar_pago_manda_a_data_e_apagar_valor_de_paga_manda_o_status():
    js = _js()
    assert "campos.pago_em=toISO(HOJE)" in js, "o servidor NÃO carimba pago_em — a tela manda"
    assert "campos.status='contratado'" in js, "apagar valor de linha paga exige o status junto"


def test_valor_vazio_e_null_nunca_zero():
    js = _js()
    assert "if (!s) return null;" in js, "parseBRL: vazio é null"
    assert "valor: (r.valor==null ? null : Number(r.valor))" in js


def test_comparativo_so_manda_fornecedor_e_valor_que_a_pessoa_mexeu():
    js = _js()
    assert "if(tocouForn) corpo.fornecedor=" in js and "if(tocouValor) corpo.valor=valor;" in js, (
        "mandar a chave apaga o padrão da cotação no servidor (model_fields_set)")


def test_indisponivel_nao_vira_removido_e_admin_e_somente_leitura():
    js = _js()
    assert "l.estado==='removido'" in js and "l.estado==='mudou'" in js and "l.estado==='ambiguo'" in js
    assert "'indisponivel'" not in js.replace("origem_estado || 'ok'", ""), "indisponivel não ganha badge — fica o aviso geral"
    assert "ITENS_LIDOS = d.itens_lidos !== false" in js and "document.getElementById('aviso-itens').hidden = ITENS_LIDOS" in js
    assert "SOMENTE_LEITURA = !!d.somente_leitura" in js and "function aplicarSomenteLeitura" in js


def test_sem_cronograma_nao_inventa_data():
    js = _js()
    assert "if (!f) return null;" in js, "fase sem data devolve null — a maquete caía em HOJE"
    assert "fase sem data" in HTML


# ── colisões e vizinhos ────────────────────────────────────────────────────
def test_nao_colide_com_o_toast_da_casa():
    js = _js()
    assert "function toast(" not in js, "toast.js define window.toast — a função da maquete morreria"
    assert "function avisar(" in js
    assert 'id="fin-toast"' in HTML and 'id="toast"' not in HTML


def test_menu_lateral_tem_financeiro_entre_cronograma_e_memorial():
    i = MENU.find("rotulo: 'Cronograma'")
    j = MENU.find("rotulo: 'Financeiro'")
    k = MENU.find("rotulo: 'Memorial'")
    assert 0 < i < j < k, "a ordem é a da maquete aprovada"
    assert "url('financeiro.html')" in MENU and "chave: 'financeiro'" in MENU
    assert "financeiro:" in MENU[MENU.find("ICONE"):MENU.find("gruposProjeto")], "ícone do menu"


def test_view_financeiro_esta_na_allowlist_do_track():
    assert '"view_financeiro"' in MAIN
    assert "trackEvent('view_financeiro', { job_id: jobId })" in HTML


def test_a_linha_guarda_a_referencia_da_origem_para_o_desfazer_recriar():
    """05/09 ao vivo: remover uma linha do quantitativo e clicar Desfazer dava 400 —
    `daApi` descartava origem_ref_id, e o POST exige a referência fora da linha livre."""
    js = _js()
    i = js.find("function daApi(r)")
    fim = js.find("\n}", i)
    corpo = js[i:fim]
    assert "origem_ref_id: r.origem_ref_id" in corpo, "a linha em memória tem que carregar a referência da origem"
    assert "origem_ref_pos:" in corpo, "e a posição, pro comparativo"
    j = js.find("function corpoDaLinha(l)")
    assert "c.origem_ref_id=l.origem_ref_id" in js[j:j + 900], "o corpo do Desfazer manda a referência que a linha guardou"


def test_hidden_vence_as_classes_de_display_do_build():
    """05/09 ao vivo: a pill 'Somente leitura' tinha `hidden` e aparecia — `.inline-flex`
    do build vence o `[hidden]` do preflight (mesma camada). A página fecha isso."""
    assert "[hidden]{display:none !important}" in _style()
    assert 'id="pill-leitura" hidden' in HTML


def test_rota_de_cotacoes_devolve_as_linhas_pro_modal():
    i = MAIN.find('@app.get("/api/projects/{job_id}/quotes")')
    assert i > 0
    assert "status,uploaded_at,items" in MAIN[i:i + 1500], "sem `items` o modal não tem linha de cotação pra apontar"
