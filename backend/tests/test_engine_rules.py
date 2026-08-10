# -*- coding: utf-8 -*-
"""Rede de segurança — camada 1: testa as REGRAS DETERMINÍSTICAS do motor
(engine_rules.py) sem chamar a IA. Roda em segundos: `python tests/test_engine_rules.py`.

Cada teste trava um comportamento que JÁ quebrou ou que NÃO pode quebrar. Vários
codificam bugs reais de 27/06 (caso Luciano/Ademir/Magno) pra nunca voltarem.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine_rules import (  # noqa: E402
    extract_balanced_obj,
    salvage_truncated_json,
    normalize_items_payload,
    should_force_steel_kg,
    is_likely_wrong_type,
    extraction_has_quality_caveat,
    extract_block_name,
    is_nonsense_item,
    extract_type_code,
    response_truncated,
    is_floor_surface,
    linhas_pai_e_filho,
    contar_textos_repetidos,
    texto_conta_objeto,
    unidade_conflita_com_sinapi,
    grandeza_da_unidade,
    casar_texto_com_regiao,
)

_passed = 0
_failed = 0


def check(nome, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok  {nome}")
    else:
        _failed += 1
        print(f"  XX  FALHOU: {nome}")


print("== extract_balanced_obj ==")
obj, end = extract_balanced_obj('{"a":1}', 0)
check("objeto balanceado simples", obj == '{"a":1}' and end == 7)
obj, _ = extract_balanced_obj('{"a":1', 0)
check("truncado -> None", obj is None)
obj, _ = extract_balanced_obj('{"a":"x}y"}', 0)
check("chave } dentro de string nao fecha cedo", obj == '{"a":"x}y"}')
obj, _ = extract_balanced_obj('{"a":"esc\\"}", "b":1}', 0)
check("aspas escapada respeitada", obj == '{"a":"esc\\"}", "b":1}')

print("== salvage_truncated_json (caso Ademir: JSON cortado no teto) ==")
trunc = ('{"project_data": {"name": "SSP-PE", "total_area": 1200}, "items": [\n'
         '  {"item_num":"1","description":"parede drywall {especial}","unit":"m","quantity":120},\n'
         '  {"item_num":"2","description":"piso 60x60","unit":"m2","quantity":340},\n'
         '  {"item_num":"3","description":"forro de gesso cor')
r = salvage_truncated_json(trunc)
check("recupera 2 itens completos do truncado", len(r["items"]) == 2)
check("ignora o 3o item cortado", all(i["item_num"] in ("1", "2") for i in r["items"]))
check("chave-em-string nao confunde o parser", r["items"][0]["quantity"] == 120)
check("recupera project_data", r.get("project_data", {}).get("name") == "SSP-PE")
full = '{"items":[{"item_num":"1","quantity":1},{"item_num":"2","quantity":2}]}'
check("json completo -> todos os itens", len(salvage_truncated_json(full)["items"]) == 2)
check("lixo -> items vazio (nunca lanca)", salvage_truncated_json("xpto")["items"] == [])

print("== normalize_items_payload (caso Luciano: 'list' object has no attribute get) ==")
check("array cru vira {items:[...]}", normalize_items_payload([{"a": 1}, {"b": 2}]) == {"items": [{"a": 1}, {"b": 2}]})
check("dict passa intacto", normalize_items_payload({"items": [1]}) == {"items": [1]})
check("None -> items vazio", normalize_items_payload(None) == {"items": []})
check("string -> items vazio", normalize_items_payload("xpto") == {"items": []})

print("== should_force_steel_kg (caso Luciano: aco sempre kg, nunca m2) ==")
check("estribos -> forca kg", should_force_steel_kg("Estribos ∅5 mm CA-50 — Vigas Piso 1") is True)
check("aco S-400 -> forca kg", should_force_steel_kg("Aço S-400 — Pilar tipo peso unitário 20,5 kg") is True)
check("armadura em aco -> forca kg", should_force_steel_kg("Pilares de concreto armado — armadura em aço CA-50") is True)
check("forma NAO vira kg (e m2)", should_force_steel_kg("Vigas de concreto armado — fôrma em compensado") is False)
check("forma com armadura no texto ainda e forma", should_force_steel_kg("Fôrma de pilar com armadura aparente") is False)
check("concreto NAO vira kg (e m3)", should_force_steel_kg("Pilares de concreto armado — fck C25/30 — concreto") is False)
check("item de arquitetura nao vira kg", should_force_steel_kg("Piso porcelanato 60x60") is False)
check("vazio nao vira kg", should_force_steel_kg("") is False)

print("== is_likely_wrong_type (caso Magno: estrutural que e arquitetura) ==")
check("Magno 6/6 zerado -> dispara", is_likely_wrong_type([0, 0, 0, 0, 0, 0]) is True)
luciano = [0] * 15 + [1.5] * 19   # 34 itens, 44% zerado (estrutural REAL)
check("Luciano 44% zerado -> NAO dispara", is_likely_wrong_type(luciano) is False)
check("tudo medido -> NAO dispara", is_likely_wrong_type([1, 2, 3, 4]) is False)
check("lista vazia -> NAO dispara", is_likely_wrong_type([]) is False)
check("exatamente 75% -> dispara (>=)", is_likely_wrong_type([0, 0, 0, 1]) is True)
check("None na qty conta como zero", is_likely_wrong_type([None, None, None, 5]) is True)

print("== extraction_has_quality_caveat (trava de procedencia, regra no1) ==")
check("metadata vazio -> sem ressalva", extraction_has_quality_caveat({}) is False)
check("None -> sem ressalva", extraction_has_quality_caveat(None) is False)
check("extracao normal -> sem ressalva", extraction_has_quality_caveat({"sinal_medido": 50}) is False)
check("esteril -> ressalva (forca estimado)", extraction_has_quality_caveat({"extracao_esteril": True}) is True)
check("unidade suspeita -> ressalva", extraction_has_quality_caveat({"unidade_suspeita": "x"}) is True)
check("alerta de unidade -> ressalva", extraction_has_quality_caveat({"alerta_unidade": "maior 600m"}) is True)
check("xref nao resolvido -> ressalva", extraction_has_quality_caveat({"xref_nao_resolvido": "arq.dwg"}) is True)

print("== extract_block_name (dedup de bloco — bug HWB: cadeira contada 2x) ==")
check("bloco CAD aspas simples", extract_block_name("Cadeira ... bloco CAD 'cad-escr-02'") == "cad-escr-02")
check("bloco aspas simples", extract_block_name("Geladeira (bloco 'geladeira010')") == "geladeira010")
check("bloco com acento", extract_block_name("Fogao, bloco 'fogão'") == "fogão")
check("case-insensitive vira chave minuscula", extract_block_name("bloco CAD 'Geladeira'") == "geladeira")
check("sem bloco -> None", extract_block_name("Piso vinilico em m2") is None)
check("alvenaria bloco ceramico SEM aspas -> None", extract_block_name("Alvenaria de bloco ceramico ou de concreto") is None)
check("descricao vazia -> None", extract_block_name("") is None)

print("== is_nonsense_item / extract_type_code (caso Thamiry: drywall inflado 284 itens) ==")
check("secao transversal -> nonsense", is_nonsense_item("Area de secao transversal de paredes drywall") is True)
check("area de secao -> nonsense", is_nonsense_item("área de seção de parede no layer A-WALL") is True)
check("item normal -> NAO nonsense", is_nonsense_item("Divisoria drywall DRY 07") is False)
check("DRY 07 -> tipo 'DRY 07'", extract_type_code("Divisoria drywall tipo DRY 07 — espessura 95mm") == "DRY 07")
check("DW-12 -> tipo 'DW 12'", extract_type_code("Parede DW-12 chapa dupla") == "DW 12")
check("PAREDE (sem num) -> None", extract_type_code("Parede de alvenaria comum") is None)
check("vedacao generica -> None (nao funde sem codigo)", extract_type_code("sistema de vedacao em drywall") is None)

print("== response_truncated (#7 leitura incompleta: corte no teto de tokens) ==")
check("max_tokens -> truncado (avisa incompleta)", response_truncated("max_tokens") is True)
check("end_turn -> NAO truncado", response_truncated("end_turn") is False)
check("stop_sequence -> NAO truncado", response_truncated("stop_sequence") is False)
check("None -> NAO truncado (nao falsea aviso)", response_truncated(None) is False)
check("vazio -> NAO truncado", response_truncated("") is False)
check("espaco em volta nao engana", response_truncated(" max_tokens ") is True)

print("== is_floor_surface (caso LAAV 27/07: area informada 335,4 m2 replicada) ==")
# DEVEM contar como superficie de piso (herdam a area informada — corretos):
check("piso -> superficie", is_floor_surface("Piso — tipo a definir — área total da planta baixa") is True)
check("forro -> superficie", is_floor_surface("Forro — área total dos ambientes internos") is True)
check("pintura de piso -> superficie", is_floor_surface("Pintura de piso — Tinta Piso Suvinil cor Cinza — piso geral") is True)
check("pintura de forro -> superficie", is_floor_surface("Pintura de forro em gesso acartonado — látex acrílica branca") is True)
check("contrapiso -> superficie", is_floor_surface("Regularização de contrapiso — área total da laje") is True)
# NAO PODEM herdar a area (o bug): pontual, linear ou comodo especifico:
check("interruptor (piso=altura) -> NAO", is_floor_surface("Interruptor simples — H=1,10m do piso acabado — 220V") is False)
check("ponto de agua (piso=altura) -> NAO", is_floor_surface("Ponto de água fria — H=0,20m do piso acabado") is False)
check("ponto de pneumatica -> NAO", is_floor_surface("Ponto de pneumática — H=0,40m do piso acabado, ar comprimido") is False)
check("faixa de seguranca no piso -> NAO", is_floor_surface("Faixa de segurança em tinta epóxi — demarcação no piso, largura 5 cm") is False)
check("demarcacao de vagas -> NAO", is_floor_surface("Faixa de demarcação de vagas em tinta epóxi — piso, largura 5 cm") is False)
check("argamassa colante banheiro -> NAO", is_floor_surface("Argamassa colante para cerâmica dos banheiros — contrapiso/piso existente") is False)
check("impermeabilizante de banheiro -> NAO", is_floor_surface("Impermeabilizante em paredes de banheiros e cabine de pintura") is False)
check("impermeabilizacao area molhada -> NAO", is_floor_surface("Impermeabilização de piso em áreas molhadas (WC, vestiário)") is False)
# guarda-corpo do comportamento antigo que ja funcionava:
check("rodape no piso -> NAO (perimetro)", is_floor_surface("Rodapé de madeira — piso do showroom") is False)
check("parede -> NAO", is_floor_surface("Pintura de parede acrílica branca") is False)
check("luminaria em m2 -> NAO (contagem)", is_floor_surface("Luminária de piso LED embutida no forro") is False)
# 2a rodada — falsos-positivos pescados no teste real ev3c243d (155 itens):
check("bancada H=1m do piso -> NAO (movel/altura)", is_floor_surface("Bancada/balcão de atendimento — elemento horizontal a H=1,00m do piso, prof 1,99m") is False)
check("bebedouro de piso -> NAO (aparelho)", is_floor_surface("Bebedouro / purificador de água de coluna ou piso — vista 3D") is False)
check("contrapiso H=5cm -> SIM (espessura, nao posicao)", is_floor_surface("Contrapiso desempenado H=5cm — regularização sobre laje") is True)

# 🪤 O `sys.exit` morava AQUI, e tudo daqui pra baixo nunca rodava. A suíte
# dizia "74 passaram" e saía antes dos 6 testes de unidade contável — teste que
# existe, parece verde e não executa. Achado em 03/08/2026 ao investigar por que
# a correção de comprimento não disparava. O exit agora é a ÚLTIMA linha do
# arquivo; teste novo entra ANTES dele.


# ── coerência de unidade em item contável (caso Rafael, 01/08/2026) ─────────
from engine_rules import is_unit_mismatch_countable

check("condulete em ml -> MISMATCH", is_unit_mismatch_countable("Condulete de dados", "ml") is True)
check("condulete em un -> ok", is_unit_mismatch_countable("Condulete metálico", "un") is False)
check("eletroduto em ml -> ok (linear de verdade)", is_unit_mismatch_countable("Eletroduto corrugado", "ml") is False)
check("tomada em m -> MISMATCH", is_unit_mismatch_countable("Tomada 2P+T", "m") is True)
check("luminária em m² -> MISMATCH", is_unit_mismatch_countable("Luminária LED 60x60", "m²") is True)
check("cabeamento em ml -> ok", is_unit_mismatch_countable("Cabeamento par trançado Cat.6", "ml") is False)


# ── comprimento medido descartado ou com rótulo errado (Eloídes, 03/08/2026) ──
# 🔒 As observações abaixo são TEXTO REAL de produção, copiado de `project_items`
# (projeto de 03/08 11:33). A regra tinha sido escrita contra um exemplo à mão e
# nunca rodou num job de verdade — o deploy entrou 5 min DEPOIS do único job que
# a exercitaria. Teste com dado real é o que impede isso de voltar.
from engine_rules import (
    corrigir_comprimento_medido as _ccm,
    medida_de_comprimento_na_observacao as _mco,
    medida_e_base_de_calculo as _base,
)

_OBS_HIDRANTE = ("Fonte: comprimento total do layer 'BOMBEIRO' = 14.989,65 m. "
                 "Inclui rede principal e ramais de hidrantes. Dividir por diâmetro "
                 "na revisão. | Unidade ajustada de ml para m² (revisar quantidade).")
_OBS_RETFIRE = ("Fonte: comprimento total do layer 'RETFIRE_CONEXES' = 295,04 m. "
                "Representa o desenvolvimento linear das conexões. | Unidade "
                "ajustada de ml para un (revisar quantidade).")
_OBS_DRYWALL = ("Fonte: comprimento total do layer A-WALL = 1184.08 m. Inclui "
                "todos os tipos DRY 01, 02, 05, 06, 07 identificados na legenda.")

# pt-BR: 14.989,65 é quatorze mil — ler como float direto daria 14,98 (erro de 1000×)
check("le milhar pt-BR", _mco(_OBS_HIDRANTE) == 14989.65)
check("le decimal com virgula", _mco(_OBS_RETFIRE) == 295.04)
check("le decimal com ponto", _mco(_OBS_DRYWALL) == 1184.08)

_f = _ccm("Tubulação de aço para hidrantes", "m²", 0, _OBS_HIDRANTE)
check("hidrante zerado: recupera a quantidade", _f.get("quantity") == 14989.65)
check("hidrante zerado: vira metro", _f.get("unit") == "m")
check("hidrante zerado: NUNCA confirmado", _f.get("confidence") == "estimado")

_f2 = _ccm("Conexões sprinkler RetFire", "un", 0, _OBS_RETFIRE)
check("retfire zerado: recupera", _f2.get("quantity") == 295.04)

# unidade JÁ correta mas quantidade 0 — o caso que a 1ª versão deixava passar
_OBS_LIMPO = "Fonte: comprimento total do layer 'PROYECTO-OBRA-PLUVIAL' = 350,94 m."
_f3 = _ccm("Rede de drenagem pluvial", "ml", 0, _OBS_LIMPO)
check("unidade certa + qtd 0: recupera mesmo assim", _f3.get("quantity") == 350.94)
check("unidade certa: mantem ml", _f3.get("unit") == "ml")


# ── 🚨 o número citado é BASE DE CÁLCULO, não a resposta (achado 03/08) ───────
# Textos reais das linhas zeradas de drywall. Preencher o total nessas linhas
# daria número ERRADO — pior que deixar vazio.
_BASES = [
    ("guia = 2x o comprimento",
     "Derivado do comprimento total de paredes (layer A-WALL = 722,39 ml). "
     "Quantidade de guia = 2 × comprimento linear."),
    ("total cobre VÁRIOS tipos",
     "Fonte: comprimento total do layer A-WALL = 1184.08 m. Inclui todos os "
     "tipos DRY 01, 02, 05, 06, 07 identificados na legenda."),
    ("comprimento por tipo indisponível",
     "Tipo identificado na legenda. Comprimento total = 965,77 ml. "
     "Comprimento por tipo não disponível."),
    ("fita estimada A PARTIR da parede",
     "Comprimento de juntas estimado a partir do comprimento total de paredes "
     "(layer A-WALL = 965,77 ml)."),
    ("área precisa de pé-direito",
     "Área total não calculável sem pé-direito do mezanino. Comprimento total "
     "de paredes = 722,39 ml."),
    ("layer soma múltiplas vistas",
     "Comprimento total = 453,08 ml, incluindo múltiplas vistas "
     "(planta baixa + cortes + elevações)."),
]
for _nome, _obs in _BASES:
    check(f"base de calculo detectada: {_nome}", _base(_obs) is True)
    check(f"NAO recupera quando e base: {_nome}", _ccm("Item", "m²", 0, _obs) == {})

check("base: perfis PROPORCIONAIS ao comprimento",
      _base("Quantidade de perfis proporcional ao comprimento total de paredes "
            "(item 4 = 545,52 ml).") is True)
check("base: forma de viga SEM DISCRIMINACAO por secao",
      _base("Comprimento total de vigas: layer FO-VIGAS = 77.36 ml. Área de fôrma "
            "= comprimento × (largura + 2 × altura). Sem discriminação de "
            "comprimento por seção no DXF.") is True)

# 🪤 O vão até o "=" não pode atravessar frase. Este texto real fazia a regra
# ler a ALTURA de um corrimão ('CORRIMO-h=1,00m') como comprimento do
# guarda-corpo — número inventado numa linha que devia ficar vazia.
_OBS_CORRIMAO = ("Múltiplos blocos 'Guarda-corpo' nas fachadas. Layer "
                 "A-FLOR-HRAL: 15.47 m. Comprimento total não calculado — "
                 "confirmar com projeto. Texto ARQ_CAIXILHOS: 'CORRIMO-h=1,00m'.")
check("nao pesca numero da frase seguinte", _mco(_OBS_CORRIMAO) is None)
check("guarda-corpo fica vazio", _ccm("Guarda-corpo", "ml", 0, _OBS_CORRIMAO) == {})

# e o contrário: medição legítima não pode ser confundida com base de cálculo
check("medicao direta NAO e base (hidrante)", _base(_OBS_HIDRANTE) is False)
check("medicao direta NAO e base (retfire)", _base(_OBS_RETFIRE) is False)
check("medicao direta NAO e base (pluvial)", _base(_OBS_LIMPO) is False)
check("soma explicita do proprio item recupera",
      _ccm("Isolamento de dutos", "m", 0,
           "Estimativa baseada no comprimento total de dutos circulares Ø150 "
           "(~55m) + Ø100 (~3,5m) = 58,5m.").get("quantity") == 58.5)

# só o rótulo errado (quantidade bate com a medida) → corrige a unidade, não o número
_f4 = _ccm("Tubulação", "m²", 295.04, _OBS_RETFIRE)
check("rotulo errado: so troca a unidade", _f4.get("unit") == "m" and "quantity" not in _f4)

# 🔒 Casos em que NÃO pode mexer
check("sem medida na obs: nao mexe", _ccm("Parede", "m²", 0, "Área a levantar nas plantas.") == {})
check("obs vazia: nao mexe", _ccm("Parede", "m²", 0, None) == {})
check("area de verdade nao vira comprimento",
      _mco("Fonte: comprimento total do layer X = 50 m². Área hachurada.") is None)
check("quantidade diferente da medida: nao mexe (pode ser conta legitima)",
      _ccm("Tubulação", "m²", 88.0, _OBS_RETFIRE) == {})
check("'confirmar comprimento total' sem numero nao vira medida",
      _mco("Comprimento individual não extraído. Confirmar comprimento total no projeto.") is None)


# ══════════════════════════════════════════════════════════════════════
#  CARIMBO DA PRANCHA ≠ DESENHO DA OBRA
# ══════════════════════════════════════════════════════════════════════
# Caso HOTEL BRISAS (05/08/2026): texto do layer "Fundo Logotipo" — o fundo
# do carimbo — virou dois serviços na planilha ("Lastro de concreto magro",
# "Viga de baldrame"). Serviço que nasce do carimbo pode nem existir na obra.
from engine_rules import layer_is_carimbo as _lic

# Os que TÊM que pegar. 'Fundo Logotipo', 'FUNDO' e 'Muldura' são os três
# layers de carimbo que realmente produziram item no banco.
for _n in ("Fundo Logotipo", "FUNDO", "Muldura", "CARIMBO", "carimb-01",
           "Logo AIarq", "LOGOTIPO_A1", "SELO", "MARGEM", "MOLDURA", "Timbre"):
    check(f"carimbo pega '{_n}'", _lic(_n) is True)

# 🔒 Os que NUNCA podem cair. Todos são layers REAIS do banco que produziram
# medição legítima — alargar os tokens e derrubar um destes tira linha da
# planilha de um cliente.
#   · 'Fachada Fundos' e 'FUNDOS' — o token FUNDO é igualdade exata por isso
#   · 'LOGRADOURO' — por isso LOGO não pode ser prefixo
#   · 'LCVP_LEGENDA 2' — legenda elétrica deu os 1990 W do caso ConfortAr
#   · 'AR-ALVENARIA' — 98,53 m² medidos
for _n in ("Fachada Fundos", "FUNDOS", "LOGRADOURO", "LCVP_LEGENDA 2",
           "AR-ALVENARIA", "AR-ALV", "POSTE LUZ", "ESCADA-EST", "FORRO-GESSO",
           "ARQ-REVESTIMENTO", "IND-LEG", "A-WALL-IDEN", "NM-ALV", "NM-PISO",
           "Q TEXTO TITULO", "ACABAMENTO - Rotulos_Caneta_No__19"):
    check(f"carimbo NAO pega '{_n}'", _lic(_n) is False)

check("carimbo: vazio nao quebra", _lic("") is False and _lic(None) is False)


# 🚨 Observação que DENUNCIA o próprio número não pode virar quantidade.
# Caso real (rafaelcmnz@, 05/08/2026): a regra gravou 1960,75 ml de alvenaria
# a partir de uma observação que dizia "inclui faces duplas ... e possíveis
# duplicações ... dividir por 2". O freio não cobria esses termos.
_OBS_FACES_DUPLAS = (
    "Fonte: comprimento total do layer 'Alvenaria' = 1960.75 m. ATENCAO: este "
    "valor representa a soma de todas as linhas do layer (inclui faces duplas de "
    "parede, ambos os pavimentos e possiveis duplicacoes). Para converter em m2 "
    "de parede, multiplicar pelo pe-direito liquido e dividir por 2 (faces duplas).")
check("faces duplas: freio pega", _base(_OBS_FACES_DUPLAS) is True)
check("faces duplas: NAO grava quantidade",
      _ccm("Alvenaria de bloco ceramico", "ml", 0, _OBS_FACES_DUPLAS) == {})
for _t in ("inclui faces duplas", "possiveis duplicacoes", "dividir por 2",
           "ambos os pavimentos", "soma de todas as linhas", "multiplicar pelo pe-direito"):
    check(f"freio pega '{_t}'", _base(f"Comprimento total = 100 m. {_t}.") is True)
# 🔒 O legítimo continua passando — o freio não pode virar mordaça.
check("medicao limpa continua recuperando",
      _ccm("Rodape", "ml", 0,
           "Fonte: comprimento total do layer A-WALL = 722,39 m medido na "
           "geometria.").get("quantity") == 722.39)


# ── Regra dos 100% (WBS): o pai não pode ser irmão do filho ──────────────────
# Casos REAIS medidos em 08/08/2026 nos 69 projetos de cliente.
def _pf(itens, **kw):
    return linhas_pai_e_filho(itens, **kw)


def _i(d, u, q, disc="Estrutura"):
    return {"description": d, "unit": u, "quantity": q, "discipline": disc}


# 🐛 job 7f7ef56a: SUBTOTAL de concreto ao lado das sapatas que o compõem.
_sapatas = [
    _i("SUBTOTAL — Concreto C25/30 — Todas as sapatas", "m³", 12.4),
    _i("Concreto C25/30 — Sapata S1", "m³", 7.1),
    _i("Concreto C25/30 — Sapata S2", "m³", 7.2),
]
check("pega SUBTOTAL de concreto convivendo com as sapatas", len(_pf(_sapatas)) == 1)
check("aponta a linha-total, não as partes", _pf(_sapatas)[0]["indice"] == 0)
check("conta as partes certas", _pf(_sapatas)[0]["n_partes"] == 2)

# 🐛 job 66ebe2d9: "Armadura total de aço" ao lado das 4 armaduras.
check("pega 'Armadura total de aço' com as armaduras irmãs",
      len(_pf([
          _i("Armadura total de aço — peso total conforme quadro", "kg", 362.7),
          _i("Armadura CA-50 Ø8,0 mm — vigas", "kg", 91.7),
          _i("Armadura CA-60 Ø5,0 mm — radier", "kg", 88.8),
          _i("Armadura CA-50 Ø6,3 mm — radier", "kg", 53.41),
          _i("Armadura CA-50 Ø10,0 mm — pilares", "kg", 128.6),
      ])) == 1)

# 🔒 FALSO POSITIVO REAL (job 60837aaf): "uso geral" não é somatório.
check("'tomadas de uso geral' NÃO é linha-total",
      _pf([_i("Tomadas elétricas 2P+T — pontos de uso geral", "un", 60, "Elétrica"),
           _i("Tomada 2P+T sala", "un", 30, "Elétrica"),
           _i("Tomada 2P+T quarto", "un", 30, "Elétrica")]) == [])

# 🔒 "vb" é sempre 1 — casaria sempre e não prova nada (8 dos 17 casos brutos).
check("unidade vb fica de fora",
      _pf([_i("Limpeza final de obra — total", "vb", 1, "Serviços"),
           _i("Limpeza final de obra", "vb", 1, "Serviços")]) == [])

# 🔒 Disciplina diferente não é irmã: senão "área total" casa com qualquer m².
check("não compara entre disciplinas diferentes",
      _pf([_i("Área total de piso", "m²", 100, "Pisos"),
           _i("Forro de gesso", "m²", 100, "Forros")]) == [])

# 🔒 Unidade diferente não é irmã.
check("não compara entre unidades diferentes",
      _pf([_i("Comprimento total de parede", "m", 100),
           _i("Parede drywall", "m²", 100)]) == [])

# 🔒 Total SEM partes que fechem (metadado legítimo, job 2f9f81c2) fica quieto.
check("'Área total construída' sozinha não dispara",
      _pf([_i("Área total construída da edificação", "m²", 30995.8, "Metadados"),
           _i("Piso porcelanato", "m²", 120.0, "Pisos")]) == [])

# 🔒 Partes que NÃO fecham (soma bem longe) não disparam — é outra coisa.
check("soma distante do total não dispara",
      _pf([_i("Área total dos quartos", "m²", 124.4, "Pisos"),
           _i("Quarto 1", "m²", 12.0, "Pisos")]) == [])

# 🔒 Total zerado nunca dispara (a linha zerada tem regra própria).
check("linha-total zerada não dispara",
      _pf([_i("Concreto total", "m³", 0),
           _i("Sapata S1", "m³", 7.1)]) == [])

# 🔒 "totalmente" não é "total" — a fronteira de palavra tem que valer.
check("'totalmente' não vira linha-total",
      _pf([_i("Parede totalmente revestida", "m²", 100, "Rev"),
           _i("Parede revestida trecho A", "m²", 100, "Rev")]) == [])

# 🔒 A regra NUNCA muda quantidade — só descreve.
_antes = [dict(x) for x in _sapatas]
_pf(_sapatas)
check("a regra não altera os itens de entrada", _sapatas == _antes)

# Aceita objeto, não só dict (o motor passa BudgetItem).
class _It:
    def __init__(s_, d, u, q, disc):
        s_.description, s_.unit, s_.quantity, s_.discipline = d, u, q, disc


check("funciona com objeto, não só dict",
      len(_pf([_It("Concreto total das sapatas", "m³", 12.4, "Estrutura"),
               _It("Sapata S1", "m³", 6.2, "Estrutura"),
               _It("Sapata S2", "m³", 6.2, "Estrutura")])) == 1)


# ── Contagem de texto repetido (o número que o set() jogava fora) ────────────
# 🐛 Bug real: `set(textos)` matava a contagem antes da IA ver. 468 das 1.080
# linhas zeradas de 08/08 nasciam de "Fonte: texto layer 'txt' — 'Bebedouro'.
# Quantidade não indicada explicitamente."
_ctr = contar_textos_repetidos

check("conta repetido: 7 bebedouros viram ×7",
      _ctr(["Bebedouro"] * 7) == [("Bebedouro", 7)])
check("texto único não ganha contagem inflada",
      _ctr(["Bebedouro", "Banco"]) == [("Banco", 1), ("Bebedouro", 1)])
# 🔒 Caixa e espaço repetido são o MESMO texto — senão a contagem se fragmenta.
check("ignora caixa e espaço duplicado",
      _ctr(["Bebedouro", "BEBEDOURO", "bebedouro", "Bebedouro  "])[0][1] == 4)
check("devolve a forma mais frequente",
      _ctr(["BEBEDOURO", "Bebedouro", "Bebedouro"])[0][0] == "Bebedouro")
# 🔒 Ordem por contagem DESC: quem corta em 50 tem que pegar os contáveis.
# O código antigo ordenava alfabeticamente e descartava repetido por azar da letra.
check("ordena por contagem, não alfabético",
      [t for t, _ in _ctr(["Zzz", "Zzz", "Zzz", "Aaa"])] == ["Zzz", "Aaa"])
check("empate de contagem desempata alfabético",
      [t for t, _ in _ctr(["Bbb", "Aaa"])] == ["Aaa", "Bbb"])
# 🔒 Lixo curto fica de fora (era `len > 2` no código original).
check("descarta texto curto demais", _ctr(["ok", "a", "  ", "sim"]) == [("sim", 1)])
check("lista vazia não quebra", _ctr([]) == [])
check("None na lista não quebra", _ctr([None, "Porta"]) == [("Porta", 1)])
check("número vira texto sem quebrar", len(_ctr([123, 123])) == 1)
# 🔒 Determinístico: mesma entrada, mesma saída — o motor já sofre com variação.
check("é determinístico entre chamadas",
      _ctr(["A1", "A1", "B2", "C3", "B2"]) == _ctr(["B2", "C3", "A1", "B2", "A1"]))

# 🪤 Cota/nível repetido NÃO é objeto. Visto no DXF real AFP-AQ-LO-229 (08/08):
# "+0,00" ×18 e "+0,01" ×18 — 18 marcações de nível, zero objetos.
for _n in ("+0,00", "-1.50", "0,00", "12", "3,75", "±0,00", " +0,01 "):
    check(f"'{_n.strip()}' NÃO conta objeto", texto_conta_objeto(_n) is False)
for _r in ("Bebedouro", "P1", "PM2", "Porta 80", "Sala 01", "V-12"):
    check(f"'{_r}' CONTA objeto", texto_conta_objeto(_r) is True)
check("vazio não conta objeto", texto_conta_objeto("") is True)

# 🪤 Cabeçalho de quadro/legenda repete 1× por linha da tabela e NÃO é item.
# Visto nas pranchas reais 0326.CGR e 0226.HWB (08/08): "descrição" ×4, "repr." ×4.
# 🚨 O ×N PIORAVA isso — a palavra passava a parecer quantidade.
for _h in ("descrição", "Descrição", "DESCRIÇÃO", "descricao", "legenda", "observações",
           "obs", "Repr.", "quantidade", "qtd", "item", "unid.", "código", "área",
           "escala", "prancha", "total", "material"):
    check(f"cabeçalho '{_h}' NÃO conta objeto", texto_conta_objeto(_h) is False)
# 🔒 Só a palavra SOZINHA é cabeçalho — composta continua contando.
for _r in ("Descrição do forro", "Item de marcenaria", "Área de serviço",
           "Total de tomadas da sala", "LM1", "Bebedouro", "Porta PM2", "Tipo A"):
    check(f"'{_r}' CONTA objeto", texto_conta_objeto(_r) is True)

# ── Unidade do item × unidade oficial do SINAPI ──────────────────────────────
# 🔑 sinapi_composicao tem a unidade de 10.284 serviços desde abril e nunca foi
# usada pra conferir nada. 8,9% dos itens em m² tinham a unidade CONVERTIDA.
_uc = unidade_conflita_com_sinapi

# 🐛 O caso real: linha em metro linear com código SINAPI de área.
check("m² do SINAPI vs ml do item CONFLITA", _uc("ml", "M2") is True)
check("M2 vs m² é a MESMA grandeza", _uc("m²", "M2") is False)
check("UN do SINAPI vs m² do item CONFLITA", _uc("m²", "UN") is True)
check("KG vs UN conflita", _uc("un", "KG") is True)
check("M3 vs M2 conflita", _uc("m²", "M3") is True)
# 🔒 Mesma grandeza escrita diferente NÃO pode alarmar.
for _a, _b in (("m","M"), ("ml","M"), ("mts","M"), ("und","UN"), ("m3","M3"), ("t","KG")):
    check(f"'{_a}' e '{_b}' não conflitam", _uc(_a, _b) is False)
# 🔒 Incomparável fica quieto: verba/conjunto são coringas nossos; H/MES/CHP são
# mão de obra e equipamento do SINAPI, nunca descrevem item de prancha.
for _u in ("vb", "cj", "gl", "", None):
    check(f"unidade nossa '{_u}' é incomparável", _uc(_u, "M2") is False)
for _s in ("H", "MES", "CHP", "CHI", "UNXKM", "", None):
    check(f"unidade SINAPI '{_s}' é incomparável", _uc("m²", _s) is False)
check("grandeza reconhece caixa e espaço", grandeza_da_unidade("  M²  ") == "area")
check("grandeza de desconhecida é None", grandeza_da_unidade("xyz") is None)

# ── Casar o RÓTULO com a REGIÃO (o elo que faltava) ─────────────────────────
class _T:
    def __init__(s_, t, pos, layer="txt"): s_.text, s_.position, s_.layer = t, pos, layer
class _R:
    def __init__(s_, area, bbox, layer="ARQ"): s_.area, s_.bbox, s_.layer = area, bbox, layer

# 🐛 Caso real (job ccd0c8c1): "Piso — Sala de Aula 02" saía com quantidade 0
# enquanto a área da sala estava medida no desenho.
_sala = casar_texto_com_regiao([_T("Sala de Aula 02", (5, 5))],
                               [_R(48.0, (0, 0, 10, 10))])
check("rótulo dentro da região casa com a área", len(_sala) == 1 and _sala[0]["area"] == 48.0)
check("o par leva o texto junto", _sala[0]["texto"] == "Sala de Aula 02")

# 🔒 O MAIOR não pode engolir: sem isso o contorno do pavimento daria a área do
# andar inteiro pra cada cômodo — erro pior que não medir.
_dois = casar_texto_com_regiao([_T("Sala de Aula 02", (5, 5))],
                               [_R(900.0, (0, 0, 100, 100)), _R(48.0, (0, 0, 10, 10))])
check("casa com a MENOR região que contém", _dois[0]["area"] == 48.0)

# 🔒 Fora de qualquer região não inventa par.
check("texto fora não casa", casar_texto_com_regiao([_T("Legenda", (999, 999))],
                                                    [_R(48.0, (0, 0, 10, 10))]) == [])
# 🔒 Uma região não vira quantidade pra vários rótulos por padrão.
_multi = casar_texto_com_regiao([_T("A", (1, 1)), _T("B", (2, 2))], [_R(48.0, (0, 0, 10, 10))])
check("1 região = 1 rótulo por padrão", len(_multi) == 1)
# 🔒 Região sem bbox (hachura) fica de fora — não chuta.
check("região sem bbox é ignorada",
      casar_texto_com_regiao([_T("X", (1, 1))], [_R(48.0, ())]) == [])
check("área zero é ignorada",
      casar_texto_com_regiao([_T("X", (1, 1))], [_R(0, (0, 0, 10, 10))]) == [])
check("listas vazias não quebram", casar_texto_com_regiao([], []) == [])
check("texto sem posição não quebra",
      casar_texto_com_regiao([_T("X", None)], [_R(48.0, (0, 0, 10, 10))]) == [])


print()
print(f"RESULTADO: {_passed} passaram, {_failed} falharam")
sys.exit(1 if _failed else 0)
