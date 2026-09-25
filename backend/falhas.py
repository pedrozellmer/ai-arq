# -*- coding: utf-8 -*-
"""Catálogo de falhas — UM tipo por problema, cada um com a sua mensagem.

🩸 25/09/2026 — até aqui a tela e o e-mail de falha vinham de DOIS lugares que
não conversavam: o e-mail adivinhava o motivo FAREJANDO palavras no texto da
tela, e o que não casava caía em "quase sempre é PDF escaneado". Rodando o texto
real de 17 situações pelo código de produção, o e-mail contradizia a tela em 8 —
em 7 delas dizendo "PDF escaneado" pra quem teve problema de servidor, de
conversor, ou mandou DWG. 57 projetos com erro em 120 dias.

Regras do Pedro (25/09), que são a VOZ de todo texto daqui:
  · "ser verdadeiro com o cliente, sem expor muito as nossas fragilidades, e
    apontando o caminho pra resolver cada problema";
  · problema NOSSO → "a gente explica que já está resolvendo e em breve ele
    recebe reprocessado"; problema DELE (arquivo errado, tipo errado) → a gente
    direciona;
  · erro interno a gente primeiro ENTENDE (baixa, estuda, e aí reprocessa) — só
    servidor caído / falha de processamento é automático;
  · crédito de IA esgotado é interno: o cliente nunca lê isso.

Dado puro (só stdlib): quem monta o e-mail é `main._build_email_de_falha`, com o
layout padrão; a Central de E-mails mostra cada tipo em "Falhas — em revisão".
🚧 ENQUANTO `LIGADO` for False nada aqui chega ao cliente: o motor segue com as
mensagens antigas até o Pedro revisar os textos na Central.
"""

LIGADO = False

# Frase comum a TODO problema nosso — a promessa que a casa cumpre (o aviso
# interno leva a causa técnica; alguém estuda e reprocessa).
NOSSO_PROMESSA = ("<b>Não é o seu arquivo, e você não precisa fazer nada.</b> Já estamos "
                  "resolvendo, e você recebe o projeto reprocessado aqui por e-mail.")

# Atalho opcional dos tipos em que o DXF contorna o nosso leitor de DWG.
_ATALHO_DXF = ("<b>Se quiser adiantar:</b> salve o mesmo desenho em DXF (no AutoCAD ou "
               "BricsCAD: Salvar como → DXF 2013) e envie no mesmo projeto — em DXF a "
               "leitura costuma sair na hora.")

# Palavras que NUNCA aparecem pro cliente (entranha nossa, não caminho dele).
# Comparadas por PALAVRA inteira (\b), senão "oda" acusaria "toda" e "roda".
PALAVRAS_INTERNAS = ("crédito", "credit", "anthropic", "libredwg", "oda", "ezdxf",
                     "exceção", "traceback", "error code", "caiu", "bug", "quarentena")

# quem: 'nosso' (a casa age) · 'cliente' (ele age, com o passo a passo)
# automatico: o sistema re-tenta sozinho ANTES de avisar alguém (só servidor)
# arte: arquivo em assets/email/ · aviso: o que o Pedro faz ao receber o alerta
TIPOS = {
    # ── NOSSO: servidor (automático primeiro; só vira e-mail se não resolver) ──
    "servidor-instavel": {
        "quem": "nosso", "automatico": True, "arte": "falha-nossa.png",
        "rotulo": "Servidor instável (esgotou as tentativas automáticas)",
        "o_que_houve": "O processamento do <b>{projeto}</b> foi interrompido por uma "
                       "instabilidade no nosso servidor. Tentamos de novo automaticamente, "
                       "mas ainda não completou.",
        "aviso": "Servidor caiu/reiniciou no meio e as re-tentativas automáticas não "
                 "resolveram. Ver o health do servidor e reprocessar.",
    },
    "leitura-sobrecarregada": {
        "quem": "nosso", "automatico": True, "arte": "falha-nossa.png",
        "rotulo": "Serviço de leitura sobrecarregado (esgotou as tentativas)",
        "o_que_houve": "O serviço que lê as suas pranchas estava sobrecarregado quando o "
                       "<b>{projeto}</b> chegou, e o processamento não completou mesmo "
                       "depois de tentarmos de novo algumas vezes.",
        "aviso": "IA sobrecarregada (429/529/timeout) além das re-tentativas. Reprocessar "
                 "quando normalizar.",
    },
    # ── NOSSO: interno (alguém entende antes de reprocessar) ──
    "interno-da-conta": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Interno: crédito, chave ou configuração da IA",
        "o_que_houve": "O processamento do <b>{projeto}</b> parou por um problema do nosso "
                       "lado.",
        "aviso": "Erro permanente da IA (crédito, chave, modelo ou pedido inválido) — ver a "
                 "causa técnica. Se for crédito: recarregar e reprocessar a lista.",
    },
    "erro-no-sistema": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Erro no nosso código",
        "o_que_houve": "Tivemos uma falha no nosso sistema ao processar o <b>{projeto}</b>.",
        "aviso": "Exceção de programação derrubou o projeto. Consertar e reprocessar.",
    },
    "leitor-dwg-versao": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Leitor: versão de DWG que ainda não lemos",
        "o_que_houve": "O nosso leitor ainda não reconhece a versão em que o arquivo "
                       "<b>{arquivo}</b> foi salvo, e por isso não conseguiu abri-lo.",
        "atalho": _ATALHO_DXF,
        "aviso": "Nenhum conversor reconheceu o DWG. Baixar e testar; se abrir depois de "
                 "um conserto, reprocessar.",
    },
    "leitor-dwg-parou": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Leitor: parou no meio do DWG",
        "o_que_houve": "O nosso leitor parou no meio do arquivo <b>{arquivo}</b> e não "
                       "conseguiu terminar de abri-lo.",
        "atalho": _ATALHO_DXF,
        "aviso": "Conversor bateu no fim do arquivo antes do esperado. Baixar e testar — se "
                 "nem o CAD abrir, é o arquivo (aí vira 'arquivo-incompleto').",
    },
    "leitor-conversao": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Leitor: conversão do DWG saiu defeituosa",
        "o_que_houve": "Conseguimos abrir o arquivo <b>{arquivo}</b>, mas o nosso leitor não "
                       "conseguiu terminar de ler o desenho.",
        "atalho": _ATALHO_DXF,
        "aviso": "O DXF gerado pela conversão foi recusado na leitura. Baixar e reproduzir.",
    },
    "leitor-extracao": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Leitor: a leitura do DXF falhou",
        "o_que_houve": "O nosso leitor não conseguiu terminar de ler o desenho "
                       "<b>{arquivo}</b>.",
        "aviso": "A extração do DXF enviado pelo cliente falhou. Baixar e reproduzir local.",
    },
    "limite-prancha-grande": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Limite: prancha grande demais pra uma vez só",
        "o_que_houve": "A prancha <b>{arquivo}</b> é maior do que conseguimos processar de "
                       "uma vez hoje.",
        "atalho": ("<b>Se quiser adiantar:</b> envie uma prancha por vez, ou limpe o "
                   "desenho antes de exportar — o comando PURGE do AutoCAD tira camadas e "
                   "blocos sem uso e costuma reduzir bastante o tamanho."),
        "aviso": "Prancha acima do teto de memória. Tentar dividir/limpar aqui e "
                 "reprocessar.",
    },
    "limite-arquivo-grande": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Limite: arquivo grande demais (MB)",
        "o_que_houve": "O arquivo <b>{arquivo}</b> é maior do que conseguimos processar de "
                       "uma vez hoje.",
        "atalho": ("<b>Se quiser adiantar:</b> envie só a prancha que você precisa medir "
                   "agora, ou divida o arquivo em partes."),
        "aviso": "Arquivo acima do teto em MB. Separar as pranchas aqui e reprocessar.",
    },
    "limite-paginas": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Limite: páginas demais num envio só",
        "o_que_houve": "O envio do <b>{projeto}</b> tem mais páginas do que processamos de "
                       "uma vez.",
        "atalho": ("<b>Se quiser adiantar:</b> envie as pranchas em partes menores, no "
                   "mesmo projeto."),
        "aviso": "Envio acima do teto de páginas. Dividir aqui e reprocessar.",
    },
    # O freio de memória com o projeto SOZINHO no servidor (com outro rodando
    # junto, a culpa é da concorrência: `servidor-instavel`, que re-tenta só).
    "limite-memoria": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Limite: projeto grande demais pra memória do servidor",
        "o_que_houve": "O <b>{projeto}</b> é maior do que conseguimos processar de uma "
                       "vez hoje.",
        "atalho": ("<b>Se quiser adiantar:</b> envie as pranchas em duas ou três partes "
                   "menores, no mesmo projeto."),
        "aviso": "Freio de memória com o projeto sozinho no servidor (não foi "
                 "concorrência). Dividir as pranchas aqui e reprocessar.",
    },
    "isolado-para-analise": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Isolado: derrubou o processamento mais de uma vez",
        "o_que_houve": "O processamento do <b>{projeto}</b> não completou, e separamos o "
                       "arquivo para olhar com atenção.",
        "aviso": "O projeto derrubou o processo repetidas vezes e entrou em quarentena. "
                 "Baixar, entender (memória? arquivo?) e reprocessar.",
    },
    # ── CLIENTE: a gente direciona, com o passo a passo ──
    "dwg-autocad-mep": {
        "quem": "cliente", "automatico": False, "arte": "falha-arquivo.png",
        "rotulo": "Arquivo do AutoCAD MEP/Architecture",
        "assunto": "{projeto} — falta um passo pra gente ler o seu arquivo",
        "titulo": "Falta um passo no seu arquivo",
        "o_que_houve": "O arquivo <b>{arquivo}</b> foi feito no AutoCAD MEP ou Architecture, "
                       "que guarda paredes e equipamentos como “objetos inteligentes”. "
                       "Nenhum conversor automático abre esse tipo de arquivo direto — não é "
                       "defeito seu, é a natureza dele.",
        "passos": ["No AutoCAD, com o arquivo aberto, digite <b>EXPORTTOAUTOCAD</b> e "
                   "aperte Enter.",
                   "Escolha a versão <b>2013</b> e confirme — ele cria um arquivo novo (o seu "
                   "original não muda).",
                   "Abra esse arquivo novo, salve como <b>DXF</b> e envie no mesmo projeto."],
        "fecho": "Assim que o DXF chegar, a gente mede o desenho de verdade.",
        "aviso": "Nada a fazer agora — o cliente recebeu o passo a passo. Olhar em 1-2 dias "
                 "se o DXF chegou.",
    },
    "pdf-escaneado": {
        "quem": "cliente", "automatico": False, "arte": "falha-pdf.png",
        "rotulo": "PDF escaneado (imagem)",
        "assunto": "{projeto} — precisamos do desenho, não da imagem",
        "titulo": "Precisamos do desenho, não da imagem",
        "o_que_houve": "O PDF <b>{arquivo}</b> é uma imagem — escaneado ou fotografado. De "
                       "uma imagem não dá pra medir com precisão.",
        "passos": ["No seu CAD, plote a prancha em <b>PDF vetorial</b> (com escala) — ou "
                   "salve como <b>DXF</b>.",
                   "Envie o arquivo novo no mesmo projeto."],
        "fecho": "Com DXF a gente mede o desenho; com PDF vetorial, identifica os itens e "
                 "estima as quantidades.",
        "aviso": "Nada a fazer agora — o cliente recebeu o caminho.",
    },
    "pdf-sem-quantidade": {
        "quem": "cliente", "automatico": False, "arte": "falha-pdf.png",
        "rotulo": "PDF lido sem nenhuma quantidade",
        "assunto": "{projeto} — lemos o desenho, mas faltou informação",
        "titulo": "Lemos o desenho, mas faltou informação",
        "o_que_houve": "Lemos o <b>{arquivo}</b>, mas não saiu nenhuma quantidade: a prancha "
                       "tem só o desenho, sem quadros de áreas, legendas ou especificações.",
        "passos": ["Se tiver o arquivo do CAD, salve como <b>DXF</b> (Salvar como → DXF "
                   "2013) e envie no mesmo projeto — é dele que sai quantidade medida.",
                   "Se só tiver PDF, envie a prancha que traz os quadros de áreas e as "
                   "legendas."],
        "fecho": "",
        "aviso": "Nada a fazer agora — o cliente recebeu o caminho.",
    },
    "arquivo-incompleto": {
        "quem": "cliente", "automatico": False, "arte": "falha-arquivo.png",
        "rotulo": "Arquivo chegou incompleto/corrompido",
        "assunto": "{projeto} — o arquivo chegou incompleto",
        "titulo": "O arquivo chegou incompleto",
        "o_que_houve": "O arquivo <b>{arquivo}</b> termina antes do que deveria — ele pode "
                       "ter sido salvo pela metade ou corrompido no caminho.",
        "passos": ["Abra o arquivo no seu CAD e confira se ele abre inteiro.",
                   "Salve de novo (de preferência em <b>DXF</b>) e envie no mesmo projeto.",
                   "Se nem o seu CAD abrir, procure a última versão salva ou o backup "
                   "automático (<b>.bak</b>)."],
        "fecho": "",
        "aviso": "Nada a fazer agora — se o cliente disser que o arquivo abre no CAD dele, "
                 "vira 'leitor-dwg-parou' (é nosso).",
    },
    "tipo-errado-estrutura": {
        "quem": "cliente", "automatico": False, "arte": "falha-tipo.png",
        "rotulo": "Tipo errado: Estrutura numa planta de arquitetura",
        "assunto": "{projeto} — o tipo do projeto ficou trocado",
        "titulo": "O tipo do projeto ficou trocado",
        "o_que_houve": "O <b>{projeto}</b> foi enviado como <b>Estrutura</b>, mas o desenho é "
                       "de arquitetura (plantas, ambientes, portas). Com o tipo Estrutura a "
                       "leitura procura só concreto, fôrma e aço — por isso não saiu nada.",
        "passos": ["Envie o mesmo arquivo de novo escolhendo o tipo <b>Arquitetura</b>."],
        "fecho": "É grátis e leva poucos minutos.",
        "aviso": "Nada a fazer agora — o cliente recebeu o caminho.",
    },
    # ── o que ninguém previu: honesto, e o aviso pede pra classificar ──
    "desconhecido": {
        "quem": "nosso", "automatico": False, "arte": "falha-nossa.png",
        "rotulo": "Não previsto — classificar",
        "o_que_houve": "O processamento do <b>{projeto}</b> parou por um problema do nosso "
                       "lado.",
        "aviso": "Tipo de falha que o catálogo não conhece. Entender a causa técnica, "
                 "reprocessar, e acrescentar o tipo ao catálogo (backend/falhas.py).",
    },
}


def assunto_do_email(tipo: str, projeto: str) -> str:
    t = TIPOS.get(tipo) or TIPOS["desconhecido"]
    p = (projeto or "").strip() or "Seu projeto"
    if t["quem"] == "nosso":
        return f"{p} — tivemos um problema do nosso lado"
    return t["assunto"].format(projeto=p)


def titulo_do_email(tipo: str) -> str:
    t = TIPOS.get(tipo) or TIPOS["desconhecido"]
    if t["quem"] == "nosso":
        return "Tivemos um problema do nosso lado"
    return t["titulo"]


def texto_da_tela(tipo: str, projeto: str = "", arquivo: str = "") -> str:
    """A MESMA história do e-mail, curta, pro erro que aparece na tela do projeto."""
    t = TIPOS.get(tipo) or TIPOS["desconhecido"]
    base = _preenche(t["o_que_houve"], projeto, arquivo)
    if t["quem"] == "nosso":
        return _sem_tags(f"{base} {NOSSO_PROMESSA}")
    passos = " ".join(f"{i}. {p}" for i, p in enumerate(t.get("passos") or [], 1))
    return _sem_tags(f"{base} Como resolver: {passos}")


def _preenche(txt: str, projeto: str, arquivo: str) -> str:
    import html as _h
    return txt.format(projeto=_h.escape((projeto or "").strip() or "seu projeto"),
                      arquivo=_h.escape((arquivo or "").strip() or "que você enviou"))


def _sem_tags(txt: str) -> str:
    import re as _r
    return " ".join(_r.sub(r"<[^>]+>", "", txt).split())


# ── Ligação com o motor (25/09/2026) ─────────────────────────────────────────
# O motor levanta `Falha(tipo, mensagem_antiga)` no ponto onde CONHECE a causa.
# Com LIGADO=False a mensagem é EXATAMENTE a de antes (nada muda pro cliente) —
# mas o tipo viaja junto e vai pro log, que é o dado da revisão do Pedro.

class Falha(RuntimeError):
    """Falha com o TIPO do catálogo. `str()` é o que a tela mostra."""

    def __init__(self, tipo, mensagem_antiga="", arquivo="", projeto=""):
        self.tipo = tipo if tipo in TIPOS else "desconhecido"
        self.arquivo = (arquivo or "").strip()
        if LIGADO or not mensagem_antiga:
            texto = texto_da_tela(self.tipo, projeto, self.arquivo)
        else:
            texto = mensagem_antiga
        super().__init__(texto)


def tipo_da_excecao(e, classe_antiga: str = "") -> str:
    """O tipo de uma exceção que chegou ao fim do job.

    `Falha` já traz o tipo. O resto vem da classificação que já existia
    (`main.como_classificar_a_falha`): erro de programação → erro-no-sistema;
    passageiro (reinício, timeout…) → servidor-instavel; o resto → desconhecido
    (NUNCA o balde que acusa o arquivo do cliente sem prova)."""
    t = getattr(e, "tipo", None)
    if t in TIPOS:
        return t
    return {"nosso": "erro-no-sistema",
            "passageiro": "servidor-instavel"}.get(classe_antiga, "desconhecido")


def tipo_do_erro_de_leitura(errblob: str, veio_da_conversao: bool = False) -> str:
    """Todas as pranchas falharam com erro permanente/desconhecido: qual tipo?

    Lê a causa TÉCNICA (o texto do erro de cada prancha), não o texto da tela."""
    m = (errblob or "").lower()
    if any(t in m for t in ("credit balance is too low", "purchase credits")):
        return "interno-da-conta"
    if "grande demais pra processar com segurança" in m:
        return "limite-arquivo-grande"
    if ("extração isolada falhou" in m or "dxfstructureerror" in m
            or "invalid sort handle" in m):
        return "leitor-conversao" if veio_da_conversao else "leitor-extracao"
    if any(t in m for t in ("authentication_error", "permission_error", "not_found_error",
                            "invalid_request", "status=401", "status=403", "status=404")):
        return "interno-da-conta"
    return "desconhecido"


def tipo_sem_itens(is_structural: bool, paginas_vetoriais: int,
                   tem_pdf: bool, tem_cad: bool) -> str:
    """A leitura terminou sem NENHUM item: qual tipo? (o mesmo que o texto antigo dizia)."""
    if is_structural:
        return "tipo-errado-estrutura"
    if tem_pdf and not tem_cad:
        return "pdf-sem-quantidade" if paginas_vetoriais > 0 else "pdf-escaneado"
    return "leitor-extracao"


def tipo_do_dwg_que_nao_abriu(aec: bool, truncado: bool) -> str:
    """DWG que nenhum conversor abriu: MEP é natureza do arquivo (o cliente age);
    os outros dois são o nosso leitor (a casa age)."""
    if aec:
        return "dwg-autocad-mep"
    if truncado:
        return "leitor-dwg-parou"
    return "leitor-dwg-versao"
