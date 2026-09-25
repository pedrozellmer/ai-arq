# -*- coding: utf-8 -*-
"""O Escritório DENTRO do projeto medido (Parte 1, 24/09/2026).

O Pedro abriu um projeto medido no celular e não achou o ERP: o Escritório tinha projetos
próprios e a única porta era um cartão no painel. Agora, no menu lateral de um projeto medido
DA PRÓPRIA CONTA, quem está no piloto ganha o grupo "Escritório" (Equipe · Tarefas · Atas),
que abre o projeto do Escritório ligado a ele — e o cria no 1º clique.

O que estes guardas provam:
  • o grupo só nasce depois de o menu saber que o projeto aberto é DA CONTA e de o banco dizer
    que ela está no piloto — e nasce sem `hidden` (nesta folha ele perde pra classe de display);
  • a página do Escritório abre o ligado ou cria; o clique duplo (23505) abre o que já existe;
  • 🪤 o banco só deixa o DONO do projeto medido ligar: a conta de administração do site LÊ os
    projetos de todos os clientes (política "Admin reads all projects"), então "consigo ver"
    não prova "é meu". Ensaio em transação desfeita (24/09): ligar o meu passou; o mesmo de novo
    deu 23505; o de um cliente (que a admin lê) foi barrado; trocar a ligação pro do cliente,
    barrado; renomear o meu (controle) passou; o servidor passa pela trava.
🧪 Cada guarda foi sabotado (a instrução que ele protege removida/trocada) e reprovou.
"""
import os

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ler(nome):
    return open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _funcao(fonte, cabeca, fim="\n  }\n"):
    corpo = fonte[fonte.index(cabeca):]
    return corpo[:corpo.index(fim)]


def test_o_grupo_so_nasce_pra_projeto_da_conta_e_no_piloto():
    js = _ler("menu-lateral.js")
    corpo = _funcao(js, "function montarEscritorio(uid)")
    assert "window.sbClient.rpc('escritorio_no_piloto')" in corpo
    assert "if (r && !r.error && r.data === true) return true;" in corpo
    # dentro do projeto medido, só o PILOTO (é o dono ligando o projeto dele); membro de equipe é só na conta
    assert "if (FIXADO || !uid || typeof window.sbClient.from !== 'function') return false;" in corpo
    assert "if (!ok) return;" in corpo
    assert "hidden" not in corpo, "nesta folha o hidden perde pra classe de display (cartão do painel, 24/09)"
    assert "var base = 'escritorio.html#/job/' + encodeURIComponent(JOB) + '/';" in corpo
    sel = js[js.index("function atualizarSelo()"):]
    i_nao_e = sel.index("if (nx) nx.textContent = 'Projeto não encontrado';")
    i_monta = sel.index("montarEscritorio();")
    assert i_nao_e < i_monta, "o grupo tem que nascer DEPOIS de saber que o projeto aberto é da conta"


def test_a_porta_do_escritorio_esta_no_menu_da_conta():
    # 🩸 24/09: a única porta era o cartão da aba Início, e o "← Todos os projetos" leva pra Meus projetos
    js = _ler("menu-lateral.js")
    corpo = _funcao(js, "function montarEscritorio(uid)")
    conta = corpo[corpo.index("if (!FIXADO) {"):corpo.index("var base")]
    assert "href=\"escritorio.html\"" in conta and "a[data-tab=\"meus-projetos\"]" in conta
    pu = _funcao(js, "function preencherUsuario()")
    assert "if (!FIXADO) montarEscritorio(u.id);" in pu
    # 🩸 Parte 2: o freela convidado não está no piloto — a porta da conta vale pra quem é de algum projeto
    corpo_m = _funcao(js, "function montarEscritorio(uid)")
    assert ".from('escritorio_membros').select('id', { count: 'exact', head: true })" in corpo_m
    assert ".eq('user_id', uid).eq('status', 'ativo')" in corpo_m


def test_o_escritorio_abre_o_ligado_ou_cria_no_primeiro_clique():
    h = _ler("escritorio.html")
    assert r"const j = /^#\/job\/([A-Za-z0-9_-]{6,80})(?:\/(\w+))?/.exec(location.hash);" in h
    assert "if (r.job) { await abrirPeloJob(r.job, r.view); return; }" in h
    ab = _funcao(h, "async function abrirPeloJob(job, view) {", "\n}\n")
    assert "PROJETOS.find((p) => p.job_id === job && p.dono === EU.id)" in ab
    assert "if (!med || med.user_id !== EU.id) return avisoJob(" in ab
    assert ab.index("if (!NO_PILOTO) return avisoJob(") < ab.index(".insert(")
    assert "if (error.code === '23505') {" in ab            # clique duplo / duas abas: abre o que já existe
    assert "location.replace(" in ab                          # #/job/... não fica no histórico


def test_o_banco_so_deixa_o_dono_do_projeto_medido_ligar():
    sql = _ler(os.path.join("backend", "migrations_pendentes", "escritorio_piloto_dtz_banco.sql"))
    sec = sql[sql.index("-- ── 21."):]
    assert "create unique index escritorio_projetos_um_por_job on public.escritorio_projetos (job_id) where job_id is not null;" in sec
    fn = sec[sec.index("create or replace function public.escritorio_projeto_job_guarda()"):]
    fn = fn[:fn.index("end $$;")]
    assert "p.user_id = new.dono::text" in fn, "conferir VISIBILIDADE não basta: a admin lê projeto de cliente"
    assert "security definer" not in fn.lower(), "em DEFINER o escritorio_eh_servidor() diria 'servidor' pra todos"
    assert "before insert or update of job_id on public.escritorio_projetos" in sec


def test_trazer_projeto_medido_pelo_escritorio_lista_so_os_da_conta():
    # 24/09 — Pedro: "eu vi o escritório, mas como levar um projeto feito pro escritório?"
    h = _ler("escritorio.html")
    tr = _funcao(h, "async function trazerMedido() {", "\n}\n")
    assert ".eq('user_id', EU.id)" in tr, "sem o filtro, a conta de administração listaria projeto de cliente"
    assert "!ligados.has(p.job_id)" in tr and "!p.archived" in tr
    assert "href=\"#/job/${encodeURIComponent(p.job_id)}/capa\"" in tr
    lista = _funcao(h, "function telaLista() {", "\n}\n")
    assert "NO_PILOTO ? '<button class=\"btn\" onclick=\"trazerMedido()\">Trazer projeto medido</button>" in lista
    assert "vem na próxima etapa" not in h[h.index("function telaCapa"):h.index("function telaCapa") + 6000]

