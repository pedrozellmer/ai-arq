# -*- coding: utf-8 -*-
"""27/09/2026 — maquete "andamento e marca" aprovada pelo Pedro ("aprovado, pode construir").

  • ANDAMENTO = etapas concluídas + a parte FEITA da etapa atual (tarefas Aprovado/Concluído; numa etapa de obra, o %
    executado do cronograma de obra — a mesma conta da tela do cronograma, feita no servidor). Pesos por etapa, padrão 1.
  • MARCA do escritório (nome, logo e cor do Meu cadastro de quem administra) no menu, no portal de quem é de fora e
    nos e-mails aos convidados, que saem "Estúdio X via AI.arq", com o contato da admin no lugar do "Um abraço, Pedro".
  • 🔒 o logo só vale do bucket "logos" do nosso Supabase; a cor só #RRGGBB e escurecida até o branco ficar legível.
"""
import email
import io
import os
import sys
from email.header import decode_header, make_header

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import escritorio as esc  # noqa: E402

H = io.open(os.path.join(os.path.dirname(_BACKEND), "escritorio.html"), encoding="utf-8").read()
NL = chr(10)
LOGO = "https://abcdefgh.supabase.co/storage/v1/object/public/logos/logo_u1_123.png"
MARCA = {"nome": "Estúdio Exemplo", "logo_url": "", "cor": "#0F766E", "contato_nome": "Admin Exemplo",
         "contato_email": "contato@exemplo.com"}


def _fn(nome):
    for cab in ("async function " + nome + "(", "function " + nome + "("):
        i = H.find(NL + cab)
        if i >= 0:
            fim = min([j for j in (H.find(NL + "function ", i + 1), H.find(NL + "async function ", i + 1),
                                   H.find(NL + "// ══", i + 1)) if j > 0] or [len(H)])
            return H[i:fim]
    raise AssertionError("função não achada: " + nome)


def _luz(h):
    def c(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (c(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ── a cor legível ──
@pytest.mark.parametrize("cor", ["#FFFF00", "#A5F3FC", "#FFFFFF", "#22D3EE"])
def test_cor_clara_escurece_ate_o_branco_ficar_legivel(cor):
    saida = esc._cor_legivel(cor)
    assert 1.05 / (_luz(saida) + 0.05) >= 4.5, (cor, saida)


def test_controle_cor_escura_fica_como_esta_e_invalida_some():
    assert esc._cor_legivel("#0F766E").lower() == "#0f766e"
    for ruim in ("red", "#12345", "#1234567", "", None, "#GGGGGG", "#0F766E;background:url(x)"):
        assert esc._cor_legivel(ruim) is None, ruim


# ── a marca do projeto ──
class Banco:
    def __init__(self, perfil=None, dono_nome="Admin Exemplo", falha=False):
        self.perfil, self.dono_nome, self.falha = perfil, dono_nome, falha

    def __call__(self, method, path, body=None, params=None, **k):
        if self.falha:
            return 500, None
        if path == "escritorio_projetos":
            return 200, [{"dono": "uid-dona"}]
        if path == "profiles":
            assert params["user_id"] == "eq.uid-dona"
            return 200, [self.perfil] if self.perfil else []
        if path == "escritorio_membros":
            assert params["papel"] == "eq.dono"
            return 200, [{"nome": self.dono_nome, "email": "Admin@Exemplo.com"}]
        raise AssertionError(path)


@pytest.fixture(autouse=True)
def _restaura():
    antes = esc._SERVICO
    yield
    esc._SERVICO = antes


def test_marca_vem_do_meu_cadastro_da_admin():
    esc._SERVICO = Banco({"company": "Estúdio Exemplo", "logo_url": LOGO, "company_brand_color": "#0F766E"})
    m = esc.marca_do_projeto("p1")
    assert m == {"nome": "Estúdio Exemplo", "logo_url": LOGO, "cor": "#0f766e",
                 "contato_nome": "Admin Exemplo", "contato_email": "admin@exemplo.com"}


@pytest.mark.parametrize("logo", ["http://abcdefgh.supabase.co/storage/v1/object/public/logos/a.png",
                                  "https://evil.example/storage/v1/object/public/logos/a.png",
                                  "https://abcdefgh.supabase.co/storage/v1/object/public/outro/a.png",
                                  "https://abcdefgh.supabase.co/storage/v1/object/public/logos/a.png?x=\"><script>",
                                  "javascript:alert(1)"])
def test_logo_de_fora_do_bucket_do_meu_cadastro_nao_entra(logo):
    esc._SERVICO = Banco({"company": "Estúdio", "logo_url": logo, "company_brand_color": ""})
    assert esc.marca_do_projeto("p1")["logo_url"] == ""


def test_sem_empresa_usa_o_nome_da_admin_e_sem_nome_nenhum_nao_tem_marca():
    esc._SERVICO = Banco({"company": "  "})
    assert esc.marca_do_projeto("p1")["nome"] == "Admin Exemplo"
    esc._SERVICO = Banco(None, dono_nome="")
    assert esc.marca_do_projeto("p1") is None


def test_leitura_que_falha_vira_sem_marca_e_nunca_derruba():
    esc._SERVICO = Banco(falha=True)
    assert esc.marca_do_projeto("p1") is None

    def explode(*a, **k):
        raise AssertionError("tabela inesperada")
    esc._SERVICO = explode
    assert esc.marca_do_projeto("p1") is None


# ── a moldura dos e-mails ──
def test_email_com_a_marca_sai_em_nome_do_escritorio():
    import main
    html = main._email_wrap("Nova emissão", "<p>corpo</p>", cta_text="Ver", cta_url="https://ai.arq.br/x",
                            reason="motivo", marca={**MARCA, "nome": "Estúdio <b>Exemplo</b>"})
    assert "Estúdio &lt;b&gt;Exemplo&lt;/b&gt;" in html and "<b>Exemplo</b>" not in html
    assert "Um abraço" not in html and "Falar no WhatsApp" not in html and "email-logo.png" not in html
    assert "Fale com <b style=\"color:#0F172A;\">Admin Exemplo</b>" in html and "contato@exemplo.com" in html
    assert "Não responda este e-mail" in html and "Enviado pelo AI.arq" in html
    assert "background:#0F766E;color:#ffffff" in html                     # o botão na cor do escritório
    assert "é só responder este e-mail" not in html                        # "não responda" e "responda" não convivem


def test_controle_sem_marca_o_email_de_sempre():
    import main
    html = main._email_wrap("T", "<p>c</p>", cta_text="Ver", cta_url="https://ai.arq.br/x", reason="motivo")
    assert "Um abraço" in html and "email-logo.png" in html and "Para remover seus dados, é só responder este e-mail." in html
    assert "Enviado pelo AI.arq" not in html and "background:#4F46E5;color:#ffffff" in html


def test_cor_da_marca_invalida_nao_entra_no_estilo():
    import main
    html = main._email_wrap("T", "c", cta_text="Ver", cta_url="https://x", reason="r",
                            marca={**MARCA, "cor": "red;background:url(https://evil)"})
    assert "evil" not in html and "background:#4F46E5;color:#ffffff" in html


def test_logo_da_marca_vai_no_topo_escapado():
    import main
    html = main._email_wrap("T", "c", reason="r", marca={**MARCA, "logo_url": LOGO})
    assert f'<img src="{LOGO}"' in html and 'alt="Estúdio Exemplo"' in html


def test_logo_e_contato_estranhos_saem_escapados():
    """A marca que chega já vem conferida (marca_do_projeto), mas a moldura não confia: escapa o que vai no HTML."""
    import main
    html = main._email_wrap("T", "c", reason="r", marca={
        **MARCA, "logo_url": 'https://x.test/a.png" onerror="alert(1)',
        "contato_nome": "<b>Ana</b>", "contato_email": "a@exemplo.com<script>"})
    assert 'onerror="alert(1)' not in html and "a.png&quot; onerror=&quot;alert(1)" in html
    assert "<b>Ana</b>" not in html and "&lt;b&gt;Ana&lt;/b&gt;" in html
    assert "<script>" not in html and "a@exemplo.com&lt;script&gt;" in html


# ── o remetente "Estúdio X via AI.arq" ──
class _SMTPFalso:
    mensagens = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, *a):
        pass

    def sendmail(self, de, para, msg):
        _SMTPFalso.mensagens.append(msg)


@pytest.fixture
def porta(monkeypatch):
    import smtplib
    import main
    del _SMTPFalso.mensagens[:]
    monkeypatch.setattr(smtplib, "SMTP", _SMTPFalso)
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
    monkeypatch.setattr(main, "_email_suprimido", lambda *a, **k: "")
    monkeypatch.setattr(main, "_email_eh_interno", lambda *a, **k: False)
    monkeypatch.setattr(main, "_marcar_links_do_email", lambda html, kind: html)
    for var, valor in (("SMTP_HOST", "smtp.exemplo.test"), ("SMTP_USER", "u@exemplo.com"),
                       ("SMTP_PASSWORD", "p"), ("SMTP_PORT", "587"), ("SMTP_FROM_NAME", "AI.arq")):
        monkeypatch.setenv(var, valor)
    return main


def _remetente(msg):
    m = email.message_from_string(msg)
    return str(make_header(decode_header(m["From"]))), m


def test_email_do_convidado_sai_via_ai_arq_e_o_nome_nao_injeta_cabecalho(porta):
    assert porta._send_email_smtp("cliente@exemplo.com", "Assunto", "<p>x</p>", nome_remetente="Estúdio Exemplo")
    de, _ = _remetente(_SMTPFalso.mensagens[-1])
    assert de.startswith("Estúdio Exemplo via AI.arq <")
    # nome com quebra de linha: sai (o e-mail não pode falhar calado por causa do nome) e não vira cabeçalho
    assert porta._send_email_smtp("cliente@exemplo.com", "Assunto", "<p>x</p>",
                                  nome_remetente="Estúdio" + chr(13) + chr(10) + "Bcc: vitima@exemplo.com")
    assert len(_SMTPFalso.mensagens) == 2
    de, m = _remetente(_SMTPFalso.mensagens[-1])
    assert m["Bcc"] is None and "vitima" not in (m["To"] or "") and "via AI.arq" in de
    # o nome sai sem o caractere de controle (nem codificado dentro do cabeçalho)
    assert de.startswith("EstúdioBcc: vitima@exemplo.com via AI.arq <") and chr(13) not in de and chr(10) not in de


def test_controle_sem_nome_o_remetente_de_sempre(porta):
    porta._send_email_smtp("cliente@exemplo.com", "Assunto", "<p>x</p>")
    de, _ = _remetente(_SMTPFalso.mensagens[-1])
    assert de.replace('"', '').startswith("AI.arq <") and "via" not in de      # o formataddr põe aspas em "AI.arq"


# ── os e-mails do Escritório usam a marca ──
def test_convite_com_marca_nao_repete_o_contato_no_corpo():
    import main
    _, html, _ = esc.email_do_convite("Admin Exemplo", "admin@exemplo.com", "Casa", "https://ai.arq.br/c",
                                      moldura=main._email_wrap, marca=MARCA)
    assert html.count("Dúvida sobre o projeto") == 1 and "Estúdio Exemplo" in html and "Um abraço" not in html
    _, html2, _ = esc.email_do_convite("Admin Exemplo", "admin@exemplo.com", "Casa", "https://ai.arq.br/c",
                                       moldura=main._email_wrap)
    assert "Dúvida sobre o projeto? Fale com Admin Exemplo em admin@exemplo.com." in html2    # controle: sem marca


# ── o cronograma do cliente devolve o % executado da obra (a conta da tela do cronograma) ──
def test_cronograma_do_cliente_traz_o_avanco_da_obra():
    import main
    from cronograma import calcular_ppc
    cron = {"fases": [{"label": "Fundação", "inicio": "2026-10-01", "fim": "2026-10-20", "dur_dias": 19, "pct_executado": 40},
                      {"label": "Alvenaria", "inicio": "2026-10-20", "fim": "2026-11-20", "dur_dias": 31, "pct_executado": 0}],
            "resumo": {"data_inicio": "2026-10-01", "data_fim": "2026-11-20", "duracao_meses": 2}}
    r = main._cronograma_pro_cliente(cron)
    assert r["resumo"]["avanco_pct"] == calcular_ppc(cron["fases"])["avanco_real_pct"] == 15.2


# ── a tela: o andamento ──
def test_andamento_conta_so_as_etapas_antes_da_atual_mais_a_parte_feita_dela():
    c = _fn("calcAndamento")
    for linha in ("const W = et.reduce((a, e) => a + pesoDa(pesos, e), 0);",
                  "const obra = ehEtapaDeObra(et[iA]) && obraPct != null;",
                  "const frac = obra ? obraPct / 100 : (total ? feitas / total : 0);",
                  "const pAntes = W ? et.slice(0, iA).reduce((a, e) => a + pesoDa(pesos, e), 0) / W * 100 : 0;",
                  "const pAtual = W ? pesoDa(pesos, et[iA]) * Math.max(0, Math.min(1, frac)) / W * 100 : 0;",
                  "return { pct: Math.round(pAntes + pAtual), pAntes, pAtual, obra, obraPct,"):
        assert linha in c, linha
    assert "calcAndamento(et, iA, pesos, feitas, total, OBRA.projeto === p.id ? OBRA.pct : null)" in _fn("andamentoAtual")
    p = _fn("pesoDa")
    assert "Number.isFinite(v) && v >= 0 ? Math.min(v, 20) : 1" in p          # sem peso = 1; negativo não vale


def test_tarefa_feita_e_aprovado_ou_concluido_e_o_cliente_so_recebe_numeros():
    a = _fn("andamentoAtual")
    assert "feitas = ts.filter((t) => !aberta(t)).length" in a
    assert ("  } else if (AND_EXT) {" + NL
            + "    total = AND_EXT.tarefas_etapa || 0; feitas = AND_EXT.feitas_etapa || 0; pesos = AND_EXT.etapa_pesos || {};") in a
    c = _fn("carregarProjeto")
    assert "papel.data === 'cliente' ? await sb.rpc('escritorio_andamento', { p_projeto: id }) : null" in c
    assert "sb.rpc('escritorio_marca', { p_projeto: id })" in c


def test_a_obra_vem_do_cronograma_de_obra_pelo_servidor():
    o = _fn("pedirObra")
    assert "apiEsc(`projetos/${p.id}/cronograma`)" in o and "resumo.avanco_pct" in o
    assert "if (!PROJ || PROJ.id !== p.id || OBRA.projeto !== p.id" in o      # resposta velha não pinta outro projeto
    assert "if (souEquipe() && !p.job_id) return;" in o


def test_pesos_so_a_admin_e_grava_so_o_que_nao_e_1():
    e = _fn("editarPesos")
    assert e.strip().split(NL)[1].strip() == "if (!souAdmin()) return;"
    assert "if (v[i] !== 1) obj[e] = v[i];" in e and ".update({ etapa_pesos: obj })" in e
    assert "if (!v.some((x) => x > 0)) return toast(" in e
    assert "${souAdmin() ? '<button type=\"button\" class=\"lnk\" onclick=\"editarPesos()\">Peso das etapas</button>' : ''}" in H


def test_tarefas_no_quadro_e_a_capa_usa_o_andamento_novo():
    r = _fn("resumoAndamento")
    assert "Tarefas no quadro" in r and "Tarefas por coluna" not in H
    assert "const a = andamentoAtual();" in r and "barraAndamento(a)" in r and "comoAndamento()" in r


# ── a tela: a marca ──
def test_logo_so_do_bucket_do_meu_cadastro_e_cor_legivel_na_tela():
    assert "const LOGO_OK = /^https:[/][/][a-z0-9]+[.]supabase[.]co[/]storage[/]v1[/]object[/]public[/]logos[/][A-Za-z0-9._-]{1,200}$/;" in H
    m = _fn("marcaLimpa")
    assert "LOGO_OK.test(String(x.logo_url || ''))" in m and "const cor = corLegivel(x.cor);" in m
    c = _fn("corLegivel")
    assert "for (let i = 0; i < 12 && 1.05 / (luzRel(c) + 0.05) < 4.5; i++) c = c.map((v) => v * 0.85);" in c
    assert "if (!/^#[0-9A-Fa-f]{6}$/.test(String(h || ''))) return null;" in c


def test_a_cor_do_escritorio_so_nas_telas_de_quem_e_de_fora():
    assert "const corDaFaixa = (ic) => (PROJ && PAPEL && !souEquipe() && MARCA && MARCA.cor ? [MARCA.cor, MARCA.clara] : [COR[ic][0], COR[ic][1]]);" in H
    r = _fn("renderMoldura")
    assert "selo.textContent = mk && !souEquipe() ? 'via AI.arq' : 'Piloto';" in r
    assert "const mk = PROJ && VIEW !== 'lista' ? MARCA : null" in r


# ── a tela RODANDO (dukpy): as contas da página publicada, não o texto delas ──
# 🔑 O bloco dos ajudantes (da marca ao andamento) roda inteiro no motor JS; o que se cobra é o NÚMERO que a tela
# mostra. Um guarda de texto não vê `Math.round(pAntes)` no lugar de `Math.round(pAntes + pAtual)` escrito de outro jeito.
def _tela(expr):
    import json
    import dukpy
    ini, fim = H.index("const LOGO_OK"), H.index("function pillPrazo")
    bloco = H[ini:fim]
    assert "function calcAndamento(" in bloco and "function marcaLimpa(" in bloco and len(bloco) < 20000
    modelo = H[H.index("const MODELO_DTZ = ["):]
    modelo = modelo[:modelo.index(";") + 1]
    return json.loads(dukpy.evaljs([modelo, bloco, "JSON.stringify(" + expr + ")"]))


def _pct(iA, pesos="{}", feitas=0, total=0, obra="null"):
    return _tela("calcAndamento(MODELO_DTZ, %d, %s, %d, %d, %s)" % (iA, pesos, feitas, total, obra))


def test_na_tela_briefing_concluido_sem_tarefa_e_1_de_9():
    # o 11% que o Pedro viu: Briefing concluído, Levantamento sem tarefa feita
    assert _tela("MODELO_DTZ.length") == 9 and _pct(1)["pct"] == 11


def test_na_tela_a_parte_feita_da_etapa_atual_entra():
    assert _pct(1, feitas=2, total=4)["pct"] == 17            # 1/9 + ½ · 1/9 = 16,7
    assert _pct(0, feitas=4, total=4)["pct"] == 11            # etapa toda feita e não concluída = a etapa inteira
    assert _pct(1, feitas=5, total=4)["pct"] == 22            # nunca passa da etapa
    assert _tela("calcAndamento(MODELO_DTZ, -1, {}, 0, 0, null)") is None      # etapa atual não marcada


def test_na_tela_o_peso_muda_a_conta():
    # Executivo (5ª) pesando 3: W = 8 + 3 = 11 → 4/11 antes + 3 · ½ / 11 = 36,4 + 13,6
    a = _pct(4, pesos='{"Executivo": 3}', feitas=1, total=2)
    assert a["pct"] == 50 and round(a["pAntes"], 1) == 36.4 and round(a["pAtual"], 1) == 13.6
    assert _tela("[pesoDa({a: -2}, 'a'), pesoDa({a: 'x'}, 'a'), pesoDa({a: 99}, 'a'), pesoDa({a: 0}, 'a'), pesoDa({}, 'a')]") \
        == [1, 1, 20, 0, 1]


def test_na_tela_a_obra_vem_do_cronograma_e_sem_ele_das_tarefas():
    assert _pct(7, obra="15.2")["pct"] == 79                  # 7/9 + 0,152/9 = 77,8 + 1,7
    assert _pct(7, obra="15.2")["obra"] is True
    assert _pct(7, feitas=1, total=4)["pct"] == 81            # sem cronograma: pelas tarefas (77,8 + 2,8)
    assert _pct(7, obra="150")["pct"] == 89                   # % absurdo não passa da etapa
    assert _pct(6, feitas=0, total=0, obra="50")["obra"] is False   # obra só na etapa de obra
    assert _tela("['Obra', 'Obras', 'Acompanhamento de obra', 'Manobra', 'Obrador', ''].map(ehEtapaDeObra)") \
        == [True, True, True, False, False, False]


def test_na_tela_cor_legivel_e_logo_so_do_bucket():
    for cor in ("#FFFF00", "#A5F3FC", "#FFFFFF"):
        saiu = _tela("corLegivel('%s')" % cor)
        assert 1.05 / (_luz(saiu) + 0.05) >= 4.5, (cor, saiu)
    assert _tela("corLegivel('#1e3a8a')") == "#1e3a8a"                          # escura já legível: fica
    assert _tela("[corLegivel('red;x'), corLegivel(''), corLegivel(null)]") == [None, None, None]
    assert _tela("marcaLimpa({nome: 'X', logo_url: 'https://evil.test/storage/v1/object/public/logos/a.png'}).logo") == ""
    assert _tela("marcaLimpa({nome: 'X', logo_url: '%s'}).logo" % LOGO) == LOGO
    assert _tela("[marcaLimpa({nome: '  '}), marcaLimpa(null)]") == [None, None]
