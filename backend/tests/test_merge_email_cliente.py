# -*- coding: utf-8 -*-
"""Como o merge chega no cliente — e por que não pode usar o e-mail do filhote.

Pedro, 24/08/2026: *"e como esse merge aparecia pro cliente? vai um email
automático tb pra ele explicando? acho que vale hein"*.

Vale, e o e-mail tinha que ser OUTRO. O do filhote diz "melhoramos o motor e
REFIZEMOS a leitura do seu projeto". Num merge isso é falso: a gente não releu
nada — juntou, prancha por prancha, o melhor de duas leituras que já existiam.
Mandar o texto errado ensina o cliente a desconfiar do que a gente escreve.

A pergunta que um orçamentista faz no segundo em que ouve "juntamos duas
planilhas" é *"então está contado em dobro?"*. O e-mail responde isso antes de
ele perguntar.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 🪤 Janela de tamanho fixo mede o vizinho (ou um pedaço) e passa
# verde por engano — a auditoria de 25/08 achou 17 assim. O recorte
# certo mora num lugar só.
from _corpo import corpo_de, ENVIO_E_BUILDER  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _corpo(nome, tam=12000):
    """🪤 A 1ª versão disto cortava no próximo `@app.` e engolia a função
    SEGUINTE inteira — dois testes mediram o corpo errado e um deles passou
    verde por causa de texto que nem era da função em teste.

    O fim de uma função é o próximo `def` na coluna zero, não o próximo
    decorador."""
    src = _main()
    i = src.index("def " + nome)
    nl = chr(10)
    marcas = [src.find(m, i + 10)
              for m in (nl + "def ", nl + "@app.", nl + "async def ")]
    marcas = [m for m in marcas if m > 0]
    corpo = src[i:min(marcas) if marcas else i + tam]
    # 05/09: o e-mail virou envio + builder (ver ENVIO_E_BUILDER em _corpo.py) —
    # o texto que o cliente lê mora no builder; medir só o envio é meia leitura.
    _b = ENVIO_E_BUILDER.get(nome)
    if _b and ("def " + _b) in src:
        corpo += _corpo(_b, tam)
    return corpo


def _sem_comentarios(src):
    _NL = chr(10)
    return _NL.join(l for l in src.splitlines() if not l.strip().startswith("#"))


def _so_o_que_o_cliente_le(nome):
    """🪤 Dois enganos que este arquivo cometeu antes de acertar:

    1. o guarda lia a DOCSTRING, onde eu cito a frase errada exatamente pra
       explicar por que ela não pode aparecer. Um guarda assim ou dá alarme
       falso, ou me faz apagar a documentação pra calar o alarme;
    2. o guarda procurava uma frase inteira que, no código, está QUEBRADA em
       duas linhas — e acusava falta do que estava lá.

    3. (31/08) o guarda lia o COMENTÁRIO. Eu documentei um bug do teto semanal
       citando a frase "refizemos a leitura" pra explicar o estrago, e o teste
       acusou o e-mail do merge de dizer o que ele não diz. É o engano nº1 de
       novo, em outra roupa — e é o erro assinatura desta casa: ler comentário
       como código.

    🪤 NÃO dá pra cortar todo "#": o HTML do e-mail é cheio de cor (#FFFBEB).
    Só sai a linha cujo primeiro caractere não-branco é "#" — que é como os
    comentários deste arquivo são escritos.

    Aqui saem a docstring e os comentários; o espaço em branco vira simples."""
    corpo = _corpo(nome)
    aspas = corpo.find('"""')
    if aspas > 0:
        fim = corpo.find('"""', aspas + 3)
        if fim > 0:
            corpo = corpo[:aspas] + corpo[fim + 3:]
    linhas = [ln for ln in corpo.splitlines() if not ln.lstrip().startswith("#")]
    return " ".join(" ".join(linhas).split())


# ══════════════════════════════════════════════════════════════════════════
#  O e-mail certo pra cada caso
# ══════════════════════════════════════════════════════════════════════════
def test_existe_um_email_proprio_pro_merge():
    assert "def _email_leitura_combinada" in _main()


def test_o_email_do_merge_NAO_diz_que_refizemos_a_leitura():
    """A frase do filhote seria mentira aqui — a gente não releu nada."""
    corpo = _so_o_que_o_cliente_le("_email_leitura_combinada")
    assert "refizemos a leitura" not in corpo.lower()
    assert "Melhoramos o motor" not in corpo


def test_o_email_do_merge_explica_o_que_e():
    corpo = _corpo("_email_leitura_combinada")
    assert "duas vezes" in corpo
    assert "combinada" in corpo


def test_o_email_responde_a_pergunta_da_dobra_sem_ser_perguntado():
    """🚨 'Juntaram duas planilhas' faz qualquer orçamentista pensar em dobra.
    Se o e-mail não responde, ele desconfia da planilha inteira."""
    corpo = _corpo("_email_leitura_combinada")
    assert "Nenhuma prancha entrou duas vezes" in corpo


def test_o_email_diz_onde_conferir_a_procedencia_linha_a_linha():
    corpo = _so_o_que_o_cliente_le("_email_leitura_combinada")
    assert "de qual leitura ela veio" in corpo


def test_o_email_carrega_o_aviso_de_sobreposicao_quando_existe():
    """O merge APONTA código repetido em duas pranchas; o cliente tem que ver
    isso no e-mail, não só se abrir a planilha."""
    corpo = _corpo("_email_leitura_combinada")
    assert "CONFERIR ANTES DE SOMAR" in corpo


def test_o_aviso_de_sobreposicao_so_sai_quando_ha_sobreposicao():
    """Controle negativo — alarme que sai sempre vira ruído ignorado.

    🪤 A 1ª versão deste guarda checava `sobre_html = ""`, o NOME de uma
    variável. Reescrevi o e-mail montando o bloco inline e o teste quebrou sem
    que nada de comportamento mudasse. Guarda tem que medir a condição, não a
    forma de escrever."""
    corpo = _corpo("_email_leitura_combinada")
    # 🪤 25/08 (auditoria): a versao anterior era TAUTOLOGICA — `i_cond < i_texto
    # or corpo.index("_sobre = next(") < i_cond`. A 1a clausula ja era FALSA
    # (o texto procurado esta na BUSCA, la em cima; a condicao vem depois) e a 2a
    # e sempre verdadeira, porque em Python a variavel tem que ser definida antes
    # de usada. O guarda nao garantia nada.
    #
    # O que importa e outra coisa: o que VAI PRO E-MAIL (`_hc.escape(_sobre)`)
    # tem que estar debaixo do `if _sobre:`. Sem alarme, nada e mostrado.
    i_cond = corpo.index("if _sobre:")
    i_render = corpo.index("_hc.escape(_sobre)")
    assert i_cond < i_render, (
        "o quadro de sobreposicao e montado fora da condicao — sairia sempre, "
        "inclusive em projeto sem sobreposicao nenhuma")


def test_o_email_reusa_o_aviso_ja_gravado_em_vez_de_recalcular():
    """Recalcular a mesma coisa em dois lugares é um lugar a mais pra divergir."""
    corpo = _corpo("_email_leitura_combinada")
    assert 'filho.get("warnings")' in corpo


def test_o_email_diz_que_a_versao_dele_continua():
    """Regra dura nº7: nunca dar a entender que a nova substitui a dele."""
    corpo = _corpo("_email_leitura_combinada")
    assert "continua no painel" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  O Liberar tem que saber distinguir merge de releitura
# ══════════════════════════════════════════════════════════════════════════
def test_o_liberar_reconhece_o_merge_pelo_prefixo():
    corpo = _corpo("admin_liberar_filhote", tam=9000)
    assert '_e_merge = str(eval_job_id).startswith("mg")' in corpo


def test_o_merge_ganha_nome_proprio_no_painel_do_cliente():
    """Chamar merge de 'nova leitura (motor atualizado)' seria mentir no título."""
    corpo = _corpo("admin_liberar_filhote", tam=9000)
    assert "versão combinada (o melhor das duas leituras)" in corpo


def test_o_liberar_escolhe_o_email_certo():
    corpo = _corpo("admin_liberar_filhote", tam=12000)
    assert "_email_leitura_combinada(pai, filho, eval_job_id" in corpo
    assert "if _e_merge" in corpo


def test_revogar_devolve_o_nome_de_teste_certo():
    """🪤 Em 23/08 o revogar gravava de volta o nome JÁ renomeado e o job ficava
    marcado como liberado mesmo depois de recolhido. Agora tem que funcionar
    pros DOIS sufixos."""
    corpo = _corpo("admin_liberar_filhote", tam=9000)
    assert "_nome_filho.endswith(_SUFIXO)" in corpo
    assert '" — combinada" if _e_merge else " — avaliação"' in corpo


# ══════════════════════════════════════════════════════════════════════════
#  Cada linha da planilha combinada diz de qual leitura veio
# ══════════════════════════════════════════════════════════════════════════
def test_a_linha_do_merge_carrega_a_leitura_de_origem():
    """Pedro, 24/08: "sempre coloca a fonte na planilha". Numa planilha
    COMBINADA a fonte tem uma camada a mais: de QUAL leitura a linha veio."""
    corpo = _corpo("admin_merge_criar", tam=12000)
    assert '"Veio da " + _sel' in corpo
    assert "_merge_data_curta" in corpo


def test_o_carimbo_de_leitura_nao_apaga_a_observacao_que_ja_existia():
    """A observação carrega a Fonte: da medição — perder isso seria trocar uma
    procedência por outra."""
    corpo = _corpo("admin_merge_criar", tam=12000)
    assert '(_obs + " | " if _obs else "")' in corpo


def test_data_ruim_nao_vira_carimbo_errado():
    """Melhor sem carimbo do que com data errada."""
    corpo = _corpo("_merge_data_curta", tam=1200)
    assert "return None" in corpo
    assert "except Exception" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  ⏱️ O 1º uso real: o estudo parecia travado
# ══════════════════════════════════════════════════════════════════════════
#
# 24/08, Pedro clicando pela 1ª vez: *"não fez nada, ele tá rolando a página pra
# baixo e não fazendo nada"*. O backend TINHA respondido — a juíza rodou, está
# no log llm:cache. Três defeitos empilhados:
#
#   1. as juízas rodavam UMA DEPOIS DA OUTRA: ~21 s só de IA (4 pranchas),
#      mais carregar 410 itens — na borda dos 45 s que o authFetch corta;
#   2. a rota não estava na lista de "rotas lentas" do authFetch, então herdava
#      o teto de 45 s em vez dos 180 s;
#   3. a caixa de espera não tinha cronômetro, então "está pensando" e "morreu"
#      eram a MESMA tela — ele esperou, achou que tinha morrido, clicou de novo
#      (o log mostra os dois cliques, com 30 s de intervalo).


def test_as_juizas_rodam_em_paralelo():
    corpo = _corpo("admin_merge_preview", tam=9000)
    src = _main()
    i = src.index("def _merge_montar")
    j = src.index("@app.get(\"/api/admin/merge-preview", i)
    montar = src[i:j]
    assert "ThreadPoolExecutor" in montar, (
        "as juízas voltaram a rodar em sequência — o tempo vira a SOMA das "
        "pranchas em vez da mais lenta")
    assert "_ex.map(" in montar


def test_o_paralelo_preserva_a_ordem_das_pranchas():
    """🪤 `executor.map` devolve na ordem da entrada; um `as_completed` embaralharia
    e o veredito iria pra a prancha errada — o pior tipo de bug, porque a tela
    continuaria bonita."""
    src = _main()
    montar = corpo_de("_merge_montar")
    assert "zip(_disputadas, _vs)" in montar


def test_o_teto_de_tempo_da_tela_e_explicito():
    import io as _io
    import os as _os
    admin = _io.open(_os.path.join(_os.path.dirname(_BACKEND), "admin.html"),
                     encoding="utf-8").read()
    i = admin.index("/api/admin/merge-preview/")
    assert "timeoutMs: 180000" in admin[i:i + 300], (
        "a rota do estudo voltou a herdar o teto de 45 s do authFetch")
    j = admin.index("/api/admin/merge-criar/")
    assert "timeoutMs: 180000" in admin[j:j + 300]


def test_a_caixa_de_espera_mostra_o_tempo():
    """Sem cronômetro, esperar e travar são indistinguíveis pra quem olha."""
    import io as _io
    import os as _os
    admin = _io.open(_os.path.join(_os.path.dirname(_BACKEND), "admin.html"),
                     encoding="utf-8").read()
    assert 'id="merge-cron"' in admin
    assert "clearInterval(_cron)" in admin


def test_montar_a_tela_esta_dentro_de_try():
    """🚨 Era o que matava tudo em silêncio: erro ao desenhar não era pego, a
    função morria e a caixa 'Lendo...' ficava pra sempre."""
    import io as _io
    import os as _os
    admin = _io.open(_os.path.join(_os.path.dirname(_BACKEND), "admin.html"),
                     encoding="utf-8").read()
    i = admin.index("_mergeUltimo = d;")
    trecho = admin[i:i + 1400]
    i_try = trecho.index("try {")
    i_html = trecho.index("mergeHtml(d, jobId)")
    assert i_try < i_html, "a montagem da tela voltou a ficar fora do try"
    assert "falhei ao desenhar a tela" in trecho
    assert "JSON.stringify(d" in trecho, (
        "sem o resultado cru na tela, o próximo erro me faz adivinhar de novo")


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Duas linhas do MESMO projeto, o mesmo botao azul
# ══════════════════════════════════════════════════════════════════════════
#
# 24/08, depois que o merge do Alan nasceu: a aba Filhotes passou a ter DUAS
# linhas do projeto dele — a releitura (ev597afa, 92→151) e a combinada
# (mg634d18, 92→179). As duas "concluído", as duas marcadas "melhorou", as duas
# com o mesmo botao azul "Liberar pro cliente".
#
# Clicar na errada entrega ao cliente a versao que PERDE as 38 portas dele. E o
# clique errado manda e-mail: nao da pra desfazer o que ele leu.
def _admin():
    import io as _io
    import os as _os
    return _io.open(_os.path.join(_os.path.dirname(_BACKEND), "admin.html"),
                    encoding="utf-8").read()


def test_a_linha_da_combinada_tem_selo_proprio():
    src = _admin()
    assert "COMBINADA &mdash; a melhor prancha de cada leitura" in src
    assert "String(f.job_id).startsWith('mg')" in src


def test_a_releitura_avisa_quando_existe_combinada_melhor():
    """O aviso vai na linha PERIGOSA, nao na certa — quem esta prestes a errar
    e quem precisa ler."""
    src = _admin()
    assert "function temMergeMelhor" in src
    assert "Libere a combinada, n" in src


def test_o_aviso_so_aparece_se_a_combinada_for_melhor_E_nao_liberada():
    """Controle negativo: aviso que sai sempre vira ruido ignorado."""
    src = _admin()
    i = src.index("function temMergeMelhor")
    corpo = src[i:i + 700]
    assert "!x.liberado" in corpo
    assert "> Number(f.depois?.medidos || 0)" in corpo


def test_a_combinada_nunca_avisa_de_si_mesma():
    src = _admin()
    i = src.index("function temMergeMelhor")
    corpo = src[i:i + 400]
    assert "if (!f || String(f.job_id).startsWith('mg')) return 0;" in corpo


def test_o_confirm_do_liberar_diz_QUAL_versao_esta_indo():
    """Ultima chance antes do e-mail sair."""
    src = _admin()
    i = src.index("async function liberarFilhote")
    corpo = src[i:i + 1600]
    assert "Vers" in corpo and "COMBINADA (" in corpo
    assert "RELEITURA (" in corpo


def test_o_resultado_do_merge_rola_ate_onde_a_pessoa_esta_olhando():
    """🚨 3 cliques do Pedro terminaram em tela vazia. Na 3ª o merge FOI criado
    (10s, no log) e a mensagem nasceu ACIMA do que ele via: o painel do estudo
    tem ~2000px e o resultado ~150px, entao a pagina encolhe embaixo dos pes de
    quem estava no fim. Acao que nao termina com algo visivel ONDE a pessoa
    esta olhando e indistinguivel de acao que nao aconteceu."""
    src = _admin()
    i = src.index("async function mergeCriar")
    # 🪤 Janela FIXA corta função e mede o pedaço errado — me pegou 2x hoje.
    # O fim é a próxima função no nível zero.
    j = src.find(chr(10) + "async function ", i + 10)
    k = src.find(chr(10) + "function ", i + 10)
    fins = [x for x in (j, k) if x > 0]
    corpo = src[i:min(fins) if fins else i + 4000]
    assert corpo.count("scrollIntoView") >= 2, (
        "o sucesso E o erro precisam rolar ate a vista — nao adianta so um")
    assert "N&atilde;o criei o projeto combinado" in corpo or "criei o projeto combinado" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  🎨 O e-mail tem que PARECER do AI.arq (e o rodape nao e enfeite)
# ══════════════════════════════════════════════════════════════════════════
#
# Pedro, 24/08: "o texto do email vai explicativo ne? (...) e vai na formatacao
# de ia arq ne? temos alguma foto legal nesse email?"
#
# Nao ia. A 1a versao saia como <div> cru: sem logo, sem a barra indigo->cyan,
# sem CTA padrao e — o que importa de verdade — SEM O RODAPE, que e onde moram o
# link de privacidade e o "responda pra remover seus dados". Ele notou pelo
# visual; o custo real era de LGPD (regra dura nº6).
def test_o_email_do_merge_usa_a_moldura_da_marca():
    corpo = _corpo("_email_leitura_combinada")
    assert "_email_wrap(" in corpo, (
        "voltou a montar HTML cru — sem logo, sem CTA e SEM o rodape de "
        "privacidade (LGPD)")


def test_tem_imagem_com_alt_que_se_sustenta_sozinho():
    """O Gmail bloqueia imagem por padrao. Se o alt nao disser nada, o cliente
    ve um retangulo vazio no meio do e-mail."""
    corpo = _corpo("_email_leitura_combinada")
    assert "_email_img(" in corpo
    i = corpo.index("_email_img(")
    trecho = corpo[i:i + 320]
    assert "medidos do CAD" in trecho, "o alt da imagem nao carrega a mensagem"


def test_tem_preheader():
    """Preheader e a 2a linha que aparece na caixa de entrada ANTES de abrir.
    Quem nao tem esta jogando fora espaco gratis."""
    corpo = _corpo("_email_leitura_combinada")
    assert "preheader=" in corpo


def test_o_assunto_NAO_leva_entidade_html():
    """🪤 A 1a versao tinha 'vers&atilde;o' no subject com um .replace() pra
    consertar. Entidade HTML nao e decodificada no cabecalho do e-mail — o
    cliente leria o codigo na caixa de entrada."""
    corpo = _corpo("_email_leitura_combinada")
    i = corpo.index("subject = ")
    linha = corpo[i:corpo.index(chr(10), i)]
    assert "&" not in linha, "entidade HTML vazando pro assunto: %s" % linha


def test_o_CTA_aponta_pro_projeto_COMBINADO():
    """Mandar pro dashboard generico faz o cliente procurar; mandar pro projeto
    errado e pior ainda."""
    corpo = _corpo("_email_leitura_combinada")
    assert "job_id=%s" in corpo and "merge_job" in corpo


def test_o_email_da_RELEITURA_tambem_usa_a_moldura():
    """🚨 A auditoria dos 17 e-mails (24/08) achou que eu tinha consertado o do
    merge e deixado o IRMAO pra tras. `_email_leitura_nova` ainda saia como
    <div> cru — sem logo, sem CTA e SEM o rodape de privacidade (regra dura
    nº6). TRES clientes ja tinham recebido assim."""
    corpo = _corpo("_email_leitura_nova")
    assert "_email_wrap(" in corpo
    assert "preheader=" in corpo


def test_os_DOIS_emails_de_versao_nova_tem_o_mesmo_padrao():
    """Guarda de simetria: e facil consertar um e esquecer o outro — foi
    exatamente o que aconteceu. Se um ganhar moldura/preheader e o outro nao,
    isto reprova."""
    for nome in ("_email_leitura_nova", "_email_leitura_combinada"):
        c = _corpo(nome)
        assert "_email_wrap(" in c, "%s sem moldura da marca" % nome
        assert "preheader=" in c, "%s sem preheader" % nome
        assert "continua no painel" in c, "%s nao diz que a versao dele fica" % nome
        i = c.index("subject = ")
        assert "&" not in c[i:c.index(chr(10), i)], "%s: entidade HTML no assunto" % nome


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Simetria: consertar um e esquecer o irmao ja aconteceu DUAS vezes
# ══════════════════════════════════════════════════════════════════════════
def test_os_DOIS_emails_contam_o_que_PIOROU():
    """25/08 (auditoria): o e-mail do merge PERDEU o quadro do que piorou quando
    eu o reescrevi pra entrar na moldura da marca. O irmao tinha; este ficou sem.

    E a SEGUNDA vez no mesmo par: antes fora a moldura em si (consertei o do
    merge e deixei o da releitura como <div> cru). Par de funcoes que faz quase
    a mesma coisa precisa de guarda de simetria, nao de disciplina."""
    for nome in ("_email_leitura_combinada", "_email_leitura_nova"):
        c = corpo_de(nome)
        assert "_piores" in c, "%s nao calcula o que piorou" % nome
        assert "piorou" in c.lower(), "%s nao mostra o que piorou" % nome
        assert "if _piores:" in c, "%s mostra o alarme sem condicao" % nome


def test_o_merge_roda_a_rede_do_selo_e_o_extrator():
    """🚨 O merge grava project_items POR FORA do motor, entao pulava as duas
    passadas que todo item normal atravessa: a rede da REGRA DURA Nº1 e o
    extrator de especificacao. "Os itens ja passaram" nao vale — a rede nasceu
    em 24/08 e os jobs de origem podem ser anteriores."""
    c = corpo_de("admin_merge_criar")
    assert "selos_sem_geometria as _ssg_m" in c, "o merge nao roda a rede do selo"
    assert "_spec_campos(" in c, "o merge nao extrai marca/codigo/cor"
    assert '"marca", "codigo_fabricante", "cor"' in c, (
        "as colunas de especificacao nao entram no insert do merge")


def test_o_rebaixamento_do_merge_corrige_o_PLACAR():
    """Se a rede rebaixa item no merge, o numero de medidos muda — e e esse
    numero que vai no e-mail. Rebaixar e mandar o placar velho seria mentir."""
    c = corpo_de("admin_merge_criar")
    i = c.index("_rebaixados = _ssg_m(")
    assert "med_merge = sum(" in c[i:i + 1400], (
        "o placar nao e recalculado depois do rebaixamento")


def test_CONTROLE_o_filtro_de_comentario_nao_cegou_o_guarda():
    """🧪 31/08 — depois de ensinar o helper a ignorar comentário, ele podia ter
    virado cego. Prova nos dois sentidos, sem tocar em arquivo nenhum."""
    def _limpa(txt):
        linhas = [ln for ln in txt.splitlines() if not ln.lstrip().startswith("#")]
        return " ".join(" ".join(linhas).split())

    # a frase num COMENTÁRIO não é achado (era o alarme falso)
    assert "refizemos a leitura" not in _limpa(
        '    # o filhote diz "refizemos a leitura"\n'
        '    corpo = "Combinamos as duas leituras"').lower()
    # a frase no TEXTO DO CLIENTE continua sendo achado
    assert "refizemos a leitura" in _limpa(
        '    # comentário inocente\n'
        '    corpo = "Refizemos a leitura do seu projeto"').lower()
    # e a cor do HTML não pode ser comida pelo filtro
    assert "#FFFBEB" in _limpa('    corpo = "background:#FFFBEB;padding:10px"')
