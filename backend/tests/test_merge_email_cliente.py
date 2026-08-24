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
    return src[i:min(marcas) if marcas else i + tam]


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

    Aqui sai a docstring e o espaço em branco vira espaço simples."""
    corpo = _corpo(nome)
    aspas = corpo.find('"""')
    if aspas > 0:
        fim = corpo.find('"""', aspas + 3)
        if fim > 0:
            corpo = corpo[:aspas] + corpo[fim + 3:]
    return " ".join(corpo.split())


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
    assert "sobre_html" in corpo


def test_o_aviso_de_sobreposicao_so_sai_quando_ha_sobreposicao():
    """Controle negativo — alarme que sai sempre vira ruído ignorado."""
    corpo = _corpo("_email_leitura_combinada")
    assert 'sobre_html = ""' in corpo


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
    i = src.index("def _merge_montar")
    montar = src[i:i + 4000]
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
