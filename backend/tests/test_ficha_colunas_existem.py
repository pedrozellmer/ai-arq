# -*- coding: utf-8 -*-
"""Toda coluna que a ficha do usuario pede EXISTE no banco (31/08/2026).

O QUE ACONTECEU: na 1a versao da ficha eu pedi `fornecedor,created_at` de
`project_supplier_quotes`. As colunas reais sao `supplier_name,uploaded_at`.
O PostgREST devolveu 400, a secao apareceu vazia — e "comparativo: nenhum" e
indistinguivel de "esse cliente nunca usou o comparativo".

Quem pegou foi a TARJA de `_falhas`, no primeiro cliente que o Pedro abriu:
"comparativo de fornecedores: resposta inesperada (status 400)". A tarja fez o
trabalho dela. Este teste existe pra o erro nem chegar la.

🪤 O RETRATO ABAIXO E UM SNAPSHOT, nao uma consulta ao banco (a bancada roda
sem rede). Se uma coluna for renomeada em producao, este teste continua verde e
mentindo — o que pega isso e a tarja de `_falhas` na tela. Ao mudar schema,
atualize o retrato aqui no mesmo commit.
Retrato tirado de `information_schema.columns` em 31/08/2026.
"""
import ast
import inspect
import os
import re
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

SCHEMA = {
    "profiles": "accept_marketing,age_confirmed_at,area,company,company_brand_color,"
                "cpf_cnpj,created_at,email,full_name,logo_url,referral_detail,"
                "referral_source,role,user_id,whatsapp",
    "projects": "address,archived,archived_at,auto_resume_count,comparativo_assinatura,"
                "comparativo_gerado_em,completed_at,created_at,desenho_assinatura,"
                "error_message,file_types,files_count,id,is_eval,items_count,job_id,"
                "layout_area,parent_job_id,phase,planilha_assinatura,planilha_gerada_em,"
                "project_name,project_type,reprocess_count,revisao_aberta_em,"
                "revisao_aberturas,status,total_area,typology,user_email,user_id,"
                "user_name,user_pe_direito,user_prazo_meses,user_status,user_total_area,"
                "warnings",
    "nps_responses": "category,comment,context,created_at,id,job_id,score,stage_ratings,"
                     "user_email,user_id,user_name",
    "processing_survey": "answer,created_at,id,job_id,question_key,user_email",
    "contact_messages": "admin_notes,attachment_filename,attachment_size_kb,"
                        "attachment_url,created_at,email,id,message,message_type,name,"
                        "phone,replied_at,source_page,status,subject,updated_at,user_agent",
    "chat_leads": "converted_at,converted_user_id,created_at,email,first_question,id,"
                  "last_message_at,n_messages,name,notes,phone,source_page,user_agent",
    "item_reviews": "action,comment,edits,id,item_id,job_id,reviewed_at,reviewed_by",
    "item_notes": "author,created_at,id,item_id,job_id,note,updated_at",
    "revision_feedback": "arquivo,created_at,id,itens,job_id,mediana_abs_delta_pct,"
                         "n_adicionados,n_alterados,n_mantidos,n_originais,n_removidos,"
                         "n_revisados,por_confidence,por_disciplina",
    "project_memorial": "conteudo,itens_assinatura,job_id,updated_at",
    "cronogramas": "created_at,data_inicio,duracao_meses,fases_custom,id,itens_assinatura,"
                   "job_id,k_sigmoid,lookahead,notas,updated_at",
    "project_supplier_quotes": "id,items,job_id,n_items_quoted,original_filename,"
                               "parse_error,parser_mode,status,storage_path,supplier_name,"
                               "total_bruto,total_mao_obra,total_material,uploaded_at,"
                               "uploaded_by",
    "project_clients": "address_site,client_company,client_email,client_name,client_phone,"
                       "created_at,id,internal_notes,job_id,updated_at",
    "agent_conversations": "answer,created_at,duration_ms,error,id,iterations,job_id,"
                           "question,tool_calls,user_id",
    "user_credits": "amount_cents,created_at,description,expires_at,id,source,source_ref,"
                    "used_at,used_on_job_id,user_id",
    "usage_events": "created_at,event,id,job_id,meta,path,user_email,user_id",
    "email_sent_log": "email,id,kind,sent_at,subject",
}
SCHEMA = {t: set(c.split(",")) for t, c in SCHEMA.items()}

# 🪤 A 1a versao deste extrator era REGEX com DOTALL e atravessava a fronteira
# entre uma chamada e a seguinte: o trecho do `profiles` engolia o do `projects`
# e o teste acusava colunas de projects como se fossem de profiles. Regex nao
# entende onde uma chamada termina — o parser de Python entende.
_FUNCS = {"_busca", "_por_email", "_por_job"}
_RE_SELECT = re.compile(r"select=([a-z_,]+)")
_RE_ORDER = re.compile(r"order=([a-z_]+)\.")
_RE_FILTRO = re.compile(r"([a-z_]+)=eq\.")


def _literais(no):
    """Todos os pedacos de string literal dentro de um argumento (o resto da
    query e variavel — `q_em`, `_in` — e nao carrega nome de coluna)."""
    return "".join(n.value for n in ast.walk(no)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str))


def _pedidos():
    """(tabela, {colunas pedidas}) de cada secao da ficha, via AST."""
    arvore = ast.parse(textwrap.dedent(inspect.getsource(main.admin_ficha_usuario)))
    out = []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                and no.func.id in _FUNCS and no.args):
            continue
        tabela = _literais(no.args[0]).strip()
        if not tabela:
            continue
        corpo = " ".join(_literais(a) for a in no.args[1:])
        cols = set()
        for m in _RE_SELECT.findall(corpo):
            cols |= {c for c in m.split(",") if c}
        if no.func.id == "_por_job":
            # aqui o select vem cru, sem o prefixo "select="
            bruto = _literais(no.args[1])
            if "select=" not in bruto:
                cols |= {c for c in bruto.split(",") if c and "=" not in c and "&" not in c}
            cols.add("job_id")
        cols |= set(_RE_ORDER.findall(corpo))
        cols |= set(_RE_FILTRO.findall(corpo))
        out.append((tabela, cols))
    return out


def test_a_ficha_pede_de_tabelas_conhecidas():
    desconhecidas = sorted({t for t, _ in _pedidos() if t not in SCHEMA})
    assert not desconhecidas, (
        "a ficha lê tabela que não está no retrato: %s. Atualize o SCHEMA deste "
        "arquivo no mesmo commit." % desconhecidas)


def test_TODA_coluna_pedida_pela_ficha_existe():
    """O teste que teria evitado o 400 do comparativo."""
    erros = []
    for tabela, cols in _pedidos():
        if tabela not in SCHEMA:
            continue
        faltando = sorted(cols - SCHEMA[tabela])
        if faltando:
            erros.append(f"{tabela}: {faltando}")
    assert not erros, (
        "a ficha pede coluna que NÃO existe — o PostgREST devolve 400 e a seção "
        "fica vazia, o que na tela vira 'o cliente não usou isso': " + " | ".join(erros))


def test_CONTROLE_o_extrator_acha_as_secoes():
    """Sem isto, os testes acima passariam vazios (achando 0 seções) e a gente
    acharia que está protegido. Guarda que não prova que enxerga não vale."""
    p = _pedidos()
    assert len(p) >= 12, "extraí só %d seções da ficha — o extrator quebrou" % len(p)
    tabelas = {t for t, _ in p}
    for obrigatoria in ("projects", "nps_responses", "item_reviews",
                        "agent_conversations", "project_supplier_quotes"):
        assert obrigatoria in tabelas, f"não extraí a seção de {obrigatoria}"


def test_CONTROLE_o_teste_REPROVA_coluna_inventada():
    """Prova que a checagem morde: uma coluna que não existe tem que aparecer."""
    falso = {"project_supplier_quotes": {"job_id", "fornecedor", "created_at"}}
    faltando = sorted(falso["project_supplier_quotes"] - SCHEMA["project_supplier_quotes"])
    assert faltando == ["created_at", "fornecedor"], faltando
