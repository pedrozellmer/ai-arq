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
