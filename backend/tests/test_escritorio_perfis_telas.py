# -*- coding: utf-8 -*-
"""Perfis do Escritório nas TELAS (26/09/2026 — maquete aprovada pelo Pedro).

Quem decide é o banco (seção 26) e o servidor (test_escritorio_perfis_servidor.py). Aqui, o que a tela promete a
cada perfil — e que ela não OFERECE o que o banco vai recusar (botão que só dá erro é defeito pro cliente):
  • cliente e fornecedor abrem só as telas deles; o menu deles não tem atas, equipe nem quantitativo;
  • o fornecedor não cria tarefa e só MOVE a dele (e só marca o checklist);
  • a resposta do cliente vai pelo servidor, e a tela não oferece apagar o que o cliente respondeu;
  • a foto chega com o login no cabeçalho — nunca com token na URL — e nome de etapa não entra em onclick;
  • reenviar o convite de um fornecedor não apaga a subpasta dele;
  • cadastro curto só pra cliente/fornecedor; o painel só leva pro Escritório quem é SÓ de fora.
🧪 Guarda genérico: todo onclick="nome(...)" da tela tem a função `nome` — botão pra função que não existe só
apareceria no clique de alguém.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NL = chr(10)


def _ler(nome):
    return io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


H = _ler("escritorio.html")


def _fn(nome):
    """O corpo da função de nível de topo `nome` (até a próxima função de topo)."""
    for cab in ("async function " + nome + "(", "function " + nome + "("):
        i = H.find(NL + cab)
        if i >= 0:
            fim = min([j for j in (H.find(NL + "function ", i + 1), H.find(NL + "async function ", i + 1),
                                   H.find(NL + "// ══", i + 1)) if j > 0] or [len(H)])
            return H[i:fim]
    raise AssertionError("função não achada: " + nome)


def test_todo_onclick_da_tela_chama_uma_funcao_que_existe():
    chamadas = set(re.findall('onclick="([A-Za-z_][A-Za-z0-9_]*)[(]', H))
    faltam = [n for n in sorted(chamadas)
              if ("function " + n + "(") not in H and ("const " + n + " =") not in H and n not in ("if", "return")]
    assert not faltam, "onclick pra função que não existe: %s" % faltam
    assert {"verFoto", "responderEmissao", "mandarDepois", "virarTarefa", "salvarColuna", "sairDaConta"} <= chamadas


def test_cada_perfil_abre_so_as_telas_dele():
    n = _fn("navegar")
    assert "souEquipe() ? ['capa', 'tarefas', 'arquivos', 'emissoes', 'atas', 'equipe', 'fotos']" in n
    # 27/09: o cronograma (só leitura, sem dinheiro) é tela SÓ do cliente — a equipe usa o cronograma do projeto medido
    assert ("souFornecedor() ? ['capa', 'tarefas', 'arquivos', 'emissoes', 'fotos'] "
            ": ['capa', 'tarefas', 'emissoes', 'fotos', 'cronograma']") in n
    assert "VIEW = telas.includes(r.view) ? r.view : 'capa';" in n


def test_o_cronograma_do_cliente_vem_do_servidor_e_nao_mostra_dinheiro():
    c = _fn("carregarCronogramaCliente")
    assert "apiEsc(`projetos/${PROJ.id}/cronograma`)" in c
    assert "pedido !== CR_PEDIDO || !PROJ || PROJ.id !== projAqui) return;" in c                   # resposta velha (trocou de projeto) não pinta a tela
    for proibido in ("valor", "R$", "curva", "sb.from(", "cronogramas"):
        assert proibido not in c, proibido
    assert "cronograma: telaCronogramaCliente" in H
    assert "${cli ? it('cronograma', 'crono', 'Cronograma da obra') : ''}" in _fn("renderMoldura")


def test_apagar_projeto_so_a_admin_e_so_com_o_nome_digitado():
    e = _fn("editarProjeto")
    assert 'onclick="apagarProjeto()">Apagar projeto</button>' in e
    a = _fn("apagarProjeto")
    assert a.strip().split(NL)[1].strip() == "if (!souAdmin()) return;"
    ok = a[a.index("$('ap-ok').onclick"):]
    assert ok.index("if ($('ap-nome').value.trim() !== String(PROJ.nome).trim()) return toast(") < ok.index("apiEsc(")
    assert "apiEsc(`projetos/${PROJ.id}`, 'DELETE')" in ok
    # quem apaga é o SERVIDOR (tira os acessos do Drive antes); a tela nunca apaga direto no banco
    assert "sb.from('escritorio_projetos').delete(" not in H
    # só some da lista depois que o servidor disse ok
    assert ok.index("if (!r.ok)") < ok.index("PROJETOS = PROJETOS.filter(")


def test_o_menu_de_fora_nao_tem_atas_equipe_nem_quantitativo():
    m = _fn("renderMoldura")
    fora = m[m.index("if (!souEquipe()) {"):]
    fora = fora[:fora.index("return;")]
    for proibido in ("'atas'", "'equipe'", "projeto.html", "financeiro.html", "memorial.html", "cronograma.html"):
        assert proibido not in fora, proibido
    assert "cli ? '' : it('arquivos'" in fora                 # o cliente nem a pasta: recebe pelas Emissões


def test_o_fornecedor_nao_cria_tarefa_e_so_move_a_dele():
    t = _fn("telaTarefas")
    assert "const cria = souEquipe();" in t
    assert "cria ? '<button class=\"btn btn-p\" onclick=\"novaTarefa()\">+ Nova tarefa</button>' : ''" in t
    assert "${cria ? `<div><button class=\"add\"" in t
    assert _fn("abrirCartao").strip().split(NL)[1].strip() == "if (souFornecedor()) return abrirCartaoFornecedor(id);"
    s = _fn("salvarColuna")
    assert ".update({ status: st, posicao: pos })" in s and "titulo" not in s and "descricao" not in s


def test_o_checklist_do_fornecedor_so_marca():
    b = _fn("blocoChecklist")
    assert "const mexe = souEquipe();" in b
    assert b.index("mexe ? `<button type=\"button\" class=\"chk-x\"") < b.index("apagarChk(")
    assert b.index("${mexe ? `<div class=\"linha\"") < b.index("addChk(")


def test_a_resposta_do_cliente_vai_pelo_servidor_e_nao_se_apaga_na_tela():
    r = _fn("responderEmissao")
    assert "apiEsc(`emissoes/${e.id}/responder`, 'POST', { tipo, nota: nota || null })" in r
    assert "if (tipo === 'revisao' && !nota) return toast(" in r
    assert "if (x.pelo_cliente) return toast(" in _fn("apagarRetorno")
    assert "${souAdmin() && !x.pelo_cliente ? ` <button type=\"button\" class=\"chk-x\"" in _fn("telaEmissoes")


def test_a_foto_vem_com_o_login_no_cabecalho_nunca_na_url():
    u = _fn("urlDaFoto")
    assert "/fotos/${id}/imagem?tam=${tam}`, { headers: { Authorization: 'Bearer '" in u
    assert "access_token}" not in u.split("headers")[0] and "token=" not in u
    e = _fn("enviarFotos")
    assert "headers: { Authorization: 'Bearer '" in e and "fd.append('fotos', a, a.name)" in e


def test_nome_de_etapa_nas_fotos_vai_em_data_e_nao_em_onclick():
    f = _fn("telaFotos")
    chip = f[f.index("const chip ="):]
    chip = chip[:chip.index(NL)]
    assert "data-ff=\"${esc(k)}\"" in chip and "onclick" not in chip


def test_reenviar_o_convite_do_fornecedor_nao_apaga_a_subpasta_dele():
    e = _fn("enviarConvite")
    assert "if (CV_PRE.perfil && corpo.perfil === CV_PRE.perfil && !corpo.pasta) delete corpo.perfil;" in e
    assert "perfil: { freela: 'equipe', fornecedor: 'fornecedor', cliente: 'cliente' }[m.papel]" in H


def test_o_convite_guarda_o_perfil_que_o_servidor_disse():
    c = _ler("convite.html")
    assert "const perfil = ['cliente', 'fornecedor'].includes(v.dados.perfil) ? v.dados.perfil : 'equipe';" in c
    assert "window.aiarqConvite.guardar(token, { projeto, por, perfil });" in c


def test_cadastro_curto_so_pra_cliente_e_fornecedor():
    c = _ler("cadastro.html")
    i = c.index("if (_convite.perfil === 'cliente' || _convite.perfil === 'fornecedor') {")
    bloco = c[i:c.index("});", i)]
    assert "['cpf_cnpj', 'empresa', 'area', 'cargo', 'referral_source']" in bloco
    assert "'Cliente de obra (Escritório)'" in bloco and "area.value = rotulo" in bloco
    assert "nome" not in bloco.split("forEach")[1] and "whatsapp" not in bloco and "aceita_termos" not in bloco


def test_o_painel_so_leva_pro_escritorio_quem_e_so_de_fora():
    d = _ler("dashboard.html")
    i = d.index("const soDeFora =")
    linha = d[i:d.index(NL, i)]
    assert "(meus.count || 0) === 0" in linha and "(equipe.count || 0) === 0" in linha and "(fora.data || []).length > 0" in linha
    assert "!sessionStorage.getItem('aiarq_escritorio_levou')" in d and ".in('papel', ['dono', 'freela'])" in d


def test_sair_pelo_escritorio_apaga_a_lembranca_dos_projetos():
    s = _fn("sairDaConta")
    assert "localStorage.removeItem('aiarq_esc_mapa')" in s and "sb.auth.signOut()" in s


# ── board de 27/09: os médios das telas ──
def test_com_dois_clientes_cada_um_responde_a_sua():
    """SEG-3/TELA-6: o 2º cliente lia "Você aprovou" pela aprovação do outro e perdia os botões."""
    i = H.index("const esperaResposta = (e) => {")
    espera = H[i:H.index("};", i)]
    assert "if (souCliente()) return !respondeuEu(e) && (u.tipo === 'enviado' || !!u.pelo_cliente);" in espera
    assert "const respondeuEu = (e) => evDa(e).some((x) => x.pelo_cliente && x.registrado_por === EU.id);" in H
    assert "'Você aprovou'" not in H and "esc(quemRespondeu(x)) + (x.tipo === 'aprovado' ? ' aprovou'" in H
    assert "if (x.registrado_por === EU.id) return 'Você';" in H
    # só diz "avisado" quando o aviso saiu
    r = _fn("responderEmissao")
    assert "const avisou = !!(r.dados && r.dados.aviso_enviado);" in r and "avisou ? 'Aprovado — o escritório foi avisado'" in r


def test_aguardando_cliente_so_com_o_cliente_vendo():
    """TELA-7/CEO-3: a coluna contava "Com o cliente", mas o cliente não via o cartão."""
    m = _fn("mover")
    assert ("if (st === 'cliente' && t.status !== 'cliente' && !t.do_cliente && clientesAtivos().length"
            " && mostrarAoCliente === undefined) {") in m
    assert "confirmarDeFora([avisoCliente(t)], 'Mostrar e mover'" in m and "if (mostrarAoCliente) mud.do_cliente = true;" in m
    s = _fn("salvarCartao")
    assert "if (st === 'cliente' && st !== t.status && clientesAtivos().length) mud.do_cliente = true;" in s


def test_abrir_cartao_pra_quem_e_de_fora_pede_ok_e_diz_o_que_ele_ve():
    """TELA-3/CEO-4: marcar o marceneiro no cartão abria a conversa interna inteira pra ele, sem aviso."""
    s = _fn("salvarCartao")
    assert ".filter(deFora)" in s and "(fornecedor) vai ler este cartão" in s and "(cliente) vai ver o título" in s
    assert "if (avisos.length) return confirmarDeFora(avisos, 'Salvar assim', () => gravarCartao(id, rascunho), () => abrirCartao(id, rascunho));" in s
    assert "sb.from('escritorio_tarefas').update" not in s, "salvarCartao grava sem passar pelo aviso"
    a = _fn("abrirCartao")
    assert "const daEquipe = gente.filter((m) => !deFora(m)), deForaG = gente.filter(deFora);" in a
    assert "<b>Visível pra quem é de fora:</b>" in a
    # o @ não oferece o cliente (ele não vê comentário) nem o fornecedor que não está no cartão
    assert "m.papel !== 'cliente' && (m.papel !== 'fornecedor' || CART.pessoas.includes(m.id))" in a
    assert "gente.filter(podeMencionar)" in a


def test_usar_pasta_mostra_a_previa_antes_de_ligar():
    """TELA-1: ligar a pasta dava edição à equipe inteira num clique, com e-mail do Google que não se desfaz."""
    u = _fn("usarPasta")
    antes = u[:u.index("if (!confirmado) {")]
    assert "apiEsc(" not in antes, "chama o servidor antes de decidir se é prévia"
    previa = u[u.index("if (!confirmado) {"):u.index("return;", u.index("if (!confirmado) {"))]
    assert "{ pasta: String(pasta).trim(), previa: true }" in previa and "usarPasta((v.pasta && v.pasta.id) || pasta, true)" in previa
    assert "v.drive_inteiro" in previa and "v.outros_projetos" in previa


def test_tirar_do_projeto_diz_o_que_houve_com_aquela_pessoa():
    t = _fn("tirarDaPasta")
    assert "saida === 'a_mao'" in t and "saida === 'outro_projeto'" in t
    # a falha DELA vem das falhas de TIRAR; a de DAR acesso a outra pessoa não é culpa de quem saiu
    assert "(!saida && (d.falhas_tirar || []).length)" in t and "(d.falhas || []).length" not in t
    assert "Emitidos" in t, "pro cliente, o socorro aponta os arquivos emitidos (ele nunca esteve na pasta)"


def test_apagar_dados_espera_o_drive_tirar_o_acesso():
    a = _fn("apagarDadosPessoa")
    i_pend = a.index("const pend = DEST.filter((d) => d.membro_id === id && d.permission_id).length;")
    i_se = a.index("if (pend) {")
    assert i_pend < i_se < a.index(".delete(") and "return abrirModal('Ainda não dá pra apagar'" in a[i_se:i_se + 200]


def test_a_pasta_do_fornecedor_que_ja_entrou_se_escolhe_pelo_servidor():
    """TELA-9: quem entrou sem pasta ficava sem pra sempre."""
    e = _fn("editarPessoa")
    assert "m.papel === 'fornecedor' && m.status !== 'removido'" in e and 'id="pe-pasta"' in e
    s = _fn("salvarPessoa")
    assert "apiEsc(`projetos/${PROJ.id}/membros/${id}/pasta`, 'POST', { pasta: sel.value || null })" in s
    assert "drive_pasta_id:" not in s and "drive_pasta_nome:" not in s, "a tela gravando a pasta direto no banco"


def test_cadastro_sem_o_convite_no_navegador_pergunta_ao_servidor():
    """TELA-10/MKT-3: quem abria o convite num navegador e entrava por outro caía no cadastro LONGO."""
    c = _ler("cadastro.html")
    i = c.index("if (!_convite && window.API_BASE) {")
    assert i < c.index("if (_convite) {", i), "a pergunta ao servidor tem que vir ANTES do bloco do convite"
    bloco = c[i:c.index("if (_convite) {", i)]
    assert "/api/escritorio/convite/pendentes" in bloco and "_voltaSemCodigo = true;" in bloco
    assert "perfil: c0.perfil || 'equipe'" in bloco
