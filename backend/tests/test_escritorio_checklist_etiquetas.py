"""26/09/2026 — Pedro: "o Trello é a referência". Checklist e etiquetas livres no cartão da tarefa.

Banco (seção 24 de escritorio_piloto_dtz_banco.sql) e tela (escritorio.html). O que se cobra:
  • a tela NÃO depende das tabelas novas (TEM_CHK): sem elas, o cartão segue como antes;
  • a cor da etiqueta vai pra um style: só #RRGGBB passa (no banco E na tela);
  • etiqueta do projeto é da admin (criar/editar/apagar = 'dono'); marcar é da equipe;
  • item e marcação ficam presos à tarefa e ao projeto pela chave estrangeira composta;
  • o item não muda de tarefa/autor depois de criado (gatilho).
O ensaio de verdade (transação desfeita, 26/09) está descrito no próprio SQL.
"""
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")


def _ler(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


SQL = _ler(os.path.join("backend", "migrations_pendentes", "escritorio_piloto_dtz_banco.sql"))
SEC = SQL[SQL.index("-- ── 24. (26/09) CHECKLIST e ETIQUETAS"):]
H = _ler("escritorio.html")


def _funcao(cabeca):
    i = H.index(cabeca)
    return H[i:H.index("\n}\n", i)]


def test_banco_prende_item_e_marcacao_a_tarefa_e_ao_projeto():
    fk_tarefa = r"foreign key \(tarefa_id, projeto_id\)\s+references public\.escritorio_tarefas\(id, projeto_id\)\s+on delete cascade"
    assert len(re.findall(fk_tarefa, SEC)) == 2, "checklist e marcação de etiqueta presos à tarefa DO MESMO projeto"
    assert re.search(r"foreign key \(etiqueta_id, projeto_id\)\s+references public\.escritorio_etiquetas\(id, projeto_id\)\s+on delete cascade", SEC)


def test_banco_so_aceita_cor_hexadecimal():
    assert "cor         text not null check (cor ~ '^#[0-9A-Fa-f]{6}$')" in SEC


def test_etiqueta_e_da_admin_e_marcar_e_da_equipe():
    for acao in ("criar", "editar", "apagar"):
        m = re.search(r"create policy escritorio_etiquetas_%s .*?;" % acao, SEC, re.S)
        assert m and "escritorio_papel(projeto_id) = 'dono'" in m.group(0), acao
    m = re.search(r"create policy escritorio_tarefa_etiquetas_marcar .*?;", SEC, re.S)
    assert m and "escritorio_papel(projeto_id) is not null" in m.group(0)


def test_rls_ligada_e_anon_sem_acesso():
    for t in ("escritorio_checklist", "escritorio_etiquetas", "escritorio_tarefa_etiquetas"):
        assert re.search(r"alter table public\.%s\s+enable row level security;" % t, SEC), t
    assert "revoke all on public.escritorio_checklist, public.escritorio_etiquetas, public.escritorio_tarefa_etiquetas from anon;" in SEC


def test_item_nao_muda_de_tarefa_nem_de_autor():
    f = SEC[SEC.index("create or replace function public.escritorio_checklist_guarda()"):]
    f = f[:f.index("end $$;")]
    assert "new.tarefa_id <> old.tarefa_id or new.projeto_id <> old.projeto_id" in f
    assert "new.criado_por := (select auth.uid());" in f


def test_tela_nao_depende_das_tabelas_novas():
    c = _funcao("async function carregarProjeto(id) {")
    assert "TEM_CHK = !ck.error && !et.error && !te.error;" in c
    # a leitura das tabelas novas NÃO entra no laço que derruba a tela ("for (const r of [m, t, tp, a, papel]) if (r.error) throw")
    assert "for (const r of [m, t, tp, a, papel]) if (r.error) throw r.error;" in c
    a = _funcao("async function abrirCartao(id) {")
    assert "${TEM_CHK ? `<div id=\"ct-etq\">" in a and "${TEM_CHK ? `<div id=\"ct-chk\">" in a


def test_cor_da_etiqueta_passa_pelo_filtro_antes_do_style():
    assert "const corOk = (c) => (/^#[0-9A-Fa-f]{6}$/.test(String(c || '')) ? c : '#64748B');" in H
    for trecho in ("style=\"background:${corOk(e.cor)}\"", "style=\"--ec:${corOk(e.cor)}\"", "cor: corOk(ETQ_COR)"):
        assert trecho in H, trecho
    # nome da etiqueta e texto do item passam pelo esc()
    assert "${esc(e.nome)}" in H and "${esc(c.texto)}" in H


def test_so_a_admin_ve_o_botao_de_nova_etiqueta():
    b = _funcao("function blocoEtiquetas(tid) {")
    assert "${souAdmin() ? `<button type=\"button\" class=\"chip\" onclick=\"formEtiqueta(" in b

# controle positivo (26/09): trocar "= 'dono'" por "is not null" na política de criar etiqueta reprovou
# test_etiqueta_e_da_admin_e_marcar_e_da_equipe; tirar o corOk() do chip reprovou o da cor.
