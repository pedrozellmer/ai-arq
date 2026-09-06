# -*- coding: utf-8 -*-
"""O campo que mais muda a planilha só podia ser informado ANTES — e no upload
o cliente ainda não viu o problema.

🎯 26/08/2026. A rota `/api/project/{job}/inform-area` existe desde o caso
cliente-21: o cliente informa DEPOIS do processamento e a planilha é refeita na
hora, sem reprocessar e sem custo de IA. Só que ela aceitava **apenas a ÁREA** —
e a própria docstring dela sempre disse: *"itens que não escalam com piso
(pintura de parede, rodapé) NÃO são preenchidos"*.

Medido em 45 dias, % de linhas de área/comprimento que saem EM BRANCO:

    não informou nada .......... 93 projetos, 1.767 itens ... 59,5%
    informou só a ÁREA .......... 7 projetos,   177 itens ... 64,4%   <- não ajuda
    informou só o PÉ-DIREITO .... 5 projetos,    33 itens ... 27,3%
    informou os dois ............ 5 projetos,    72 itens ... 29,2%

**O pé-direito corta a linha em branco pela metade. A área sozinha não muda
nada** — e isso é o controle: não é só "cliente engajado preenche campo".
Mesmo assim, o mecanismo pós-fato existia para a área e não para o pé-direito.

🔑 POR QUE ISSO IMPORTA: a verdade de campo (96 correções de 6 clientes reais,
3 semanas) diz que **87% do que o cliente corrige é PREENCHER linha zerada**,
não consertar número errado. Ver [[project_verdade_de_campo_20260826]].

🔑 E POR QUE DEPOIS É MELHOR QUE ANTES: no upload ele ainda não viu o problema.
Na tela do projeto ele está olhando a linha em branco.

Alvo medido no acervo (134 projetos concluídos):
    44 com pintura de parede em branco
    15 mostrariam o convite (têm parede MEDIDA — dá pra completar)
    29 ficam calados (pintura vazia mas sem parede medida — pedir não resolve)
    10 já informaram
Os 15 guardam 38.223 m de parede medida.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)


def _corpo(caminho):
    txt = io.open(caminho, encoding="utf-8").read()
    return chr(10).join(l for l in txt.split(chr(10))
                        if not l.strip().startswith(("#", "//")))


_MAIN = _corpo(os.path.join(_BACKEND, "main.py"))
_PROJ = io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()


def test_a_rota_aceita_o_pe_direito():
    assert "pe_direito: float = 0" in _MAIN, (
        "o payload de inform-area voltou a aceitar só a área — o campo que "
        "corta a linha em branco pela metade ficou de fora de novo")


def test_area_deixou_de_ser_obrigatoria():
    """Informar SÓ o pé-direito tem que passar."""
    assert "area: float = 0" in _MAIN, (
        "`area` voltou a ser obrigatória: quem quer informar só o pé-direito "
        "leva 422 e o convite novo não funciona")
    assert "Informe a área total (m²) ou o pé-direito (m)." in _MAIN, (
        "sumiu a validação de 'veio um dos dois'")


def test_pe_direito_fora_da_faixa_e_recusado():
    """🚨 Um pé-direito errado multiplica a pintura INTEIRA.

    Mesma faixa do campo do upload (1,8 a 8 m). Digitar 27 no lugar de 2,7 daria
    uma pintura 10× maior com a conta escrita parecendo legítima.
    """
    assert "1.8 <= pe_dir <= 8" in _MAIN, (
        "a faixa do pé-direito sumiu — 27 m viraria pintura 10× maior")


def test_a_derivacao_da_pintura_e_CHAMADA_na_rota():
    """🪤 Guarda de CALL SITE. A derivação já existia e essa rota nunca a
    chamava — era exatamente o buraco."""
    i_rota = _MAIN.find("def inform_project_area")
    assert i_rota > 0, "a rota sumiu"
    trecho = _MAIN[i_rota:i_rota + 9000]
    assert "_derive_pintura_pe_direito(items" in trecho, (
        "a rota salva o pé-direito e NÃO deriva a pintura — o cliente informa "
        "e a linha continua em branco, que é o defeito de origem")


def test_informar_SO_o_pe_direito_nao_apaga_a_area_medida():
    """🚨 Regra nº1: trocar medição por rótulo de estimativa sem pedir.

    Se `area` vem 0, a área que o projeto já tinha não pode virar 0 nem ser
    marcada como 'informado por você'.
    """
    i = _MAIN.find("def inform_project_area")
    t = _MAIN[i:i + 9000]
    assert "_area_ja_tinha" in t, (
        "a área anterior não é preservada quando vem só o pé-direito")
    assert 'if area > 0:' in t and 'pd.total_area_source = "informado"' in t, (
        "a fonte da área é carimbada 'informado' mesmo quando o cliente não "
        "informou área nenhuma")


def test_o_pe_direito_e_PERSISTIDO_no_projeto():
    """🪤 Mesma armadilha do `user_total_area`: campo que não existe na RPC
    `update_project_status` é descartado em SILÊNCIO. Sem gravar, um reprocesso
    futuro perde o pé-direito e a pintura some de novo."""
    i = _MAIN.find("def inform_project_area")
    t = _MAIN[i:i + 9000]
    assert '"user_pe_direito"' in t and "_projeto_patch" in t, (
        "o pé-direito informado não é gravado por `_projeto_patch` — some no "
        "próximo reprocesso")


def test_o_convite_da_tela_nao_pergunta_o_que_nao_resolve():
    """🚨 A 3ª condição é a que separa 'dá pra completar' de 'pedir por pedir'.

    Medido: das 44 telas com pintura em branco, 29 NÃO têm parede medida em
    metro linear. Nessas, informar a altura não completa nada — e pedir dado
    que não resolve queima a confiança do cliente.
    """
    assert "function maybeShowPeDireitoPrompt" in _PROJ, "o convite sumiu"
    i = _PROJ.find("function maybeShowPeDireitoPrompt")
    t = _PROJ[i:i + 1800]
    # 🪤 A 1ª versão deste teste só procurava a PALAVRA `paredeMedida` — e a
    # declaração da variável continuava lá mesmo com o `return` removido, então
    # a sabotagem passou VERDE. Procurar o identificador não é conferir a
    # decisão: o que tem que existir é o `return`.
    assert "if (!paredeMedida) return;" in t, (
        "o convite parou de SAIR quando não há parede medida — apareceria nos "
        "29 projetos onde informar a altura não completa nada")
    assert "if (!pinturaVazia) return;" in t, (
        "parou de sair quando a pintura já tem número")
    assert "'teto'" in t and "'forro'" in t, (
        "parou de excluir teto/forro: a conta comprimento × altura é de PAREDE")


def test_a_trava_de_ja_informou_le_um_campo_que_EXISTE():
    """🪤 A ARMADILHA QUE QUASE PASSOU. A RPC `list_user_projects` NÃO devolve
    `user_pe_direito` (conferido no banco em 26/08: devolve job_id,
    project_name, typology, status, total_area, warnings, …).

    Ler o campo inexistente dá `undefined`, a trava nunca fecha, e o convite
    aparece pra quem já informou. Guarda que sempre passa é pior que guarda
    nenhum — é o mesmo erro do `hover:` que eu contei errado em 24/08.
    """
    i = _PROJ.find("function maybeShowPeDireitoPrompt")
    t = _PROJ[i:i + 1800]
    assert "proj.user_pe_direito" not in t, (
        "a trava voltou a ler `proj.user_pe_direito`, que a RPC não devolve — "
        "sempre undefined, sempre passa")
    assert "proj.warnings" in t and "pé-direito de" in t.lower(), (
        "a trava não lê o aviso, que é o único sinal que a RPC entrega")


def test_o_backend_escreve_o_aviso_que_a_tela_le():
    """As duas pontas: se o backend parar de escrever a frase, a trava da tela
    deixa de funcionar em silêncio."""
    assert "INFORMADO POR VOCÊ" in _MAIN
    i = _MAIN.find("def inform_project_area")
    t = _MAIN[i:i + 9000]
    assert "Pé-direito de" in t, (
        "o backend parou de escrever o aviso do pé-direito nos warnings — a "
        "trava da tela lê essa frase e vai passar a mostrar o convite sempre")


def test_o_caminho_da_AREA_continua_igual():
    """Regressão: o caso cliente-21 não pode quebrar."""
    i = _MAIN.find("def inform_project_area")
    t = _MAIN[i:i + 9000]
    assert "_apply_area_honesty(" in t and "apenas_preencher=True" in t, (
        "o preenchimento por área informada mudou de forma")
    assert '"user_total_area"' in t, "parou de gravar a área informada"


def test_o_log_conta_o_que_aconteceu():
    assert '"motor:informou-depois"' in _MAIN, (
        "informar depois não deixa rastro — não dá pra saber se o convite novo "
        "está sendo usado nem se ele completa alguma coisa")
    assert '"motor:informou-depois",' in _MAIN[:_MAIN.find("async def")], (
        "o stage não foi registrado na lista de stages conhecidos do log")
