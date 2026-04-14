# -*- coding: utf-8 -*-
"""Agente IA para Instagram — responde DMs e gera conteúdo automaticamente."""
import os
import json
import logging
import anthropic
from typing import Optional

logger = logging.getLogger("instagram_agent")

# ══════════════════════════════════════════════════════════════════
#  System prompt — personalidade do agente no Instagram
# ══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_DM = """Você é o assistente virtual da AI.arq no Instagram.
A AI.arq é uma plataforma que transforma pranchas de arquitetura (PDFs de plantas) em planilhas de orçamento automaticamente, usando inteligência artificial.

Nosso slogan: "Planilha de orçamento em minutos, não em dias."

## Sobre o serviço:
- O usuário envia PDFs do anteprojeto ou projeto executivo
- A IA analisa cada prancha e extrai todos os itens de orçamento automaticamente
- Gera uma planilha Excel (.xlsx) profissional organizada por 16 disciplinas
- A planilha sai pronta para enviar aos fornecedores
- Segue normas SINAPI/TCPO

## Números que impressionam:
- 10+ tipos de pranchas reconhecidos (layout, forro, piso, pontos elétricos, mobiliário, marcenaria, demolição, etc.)
- 130+ tipos de itens identificados automaticamente
- 745+ pontos elétricos mapeados
- 16 disciplinas de obra cobertas
- Processamento em ~10 minutos
- Até 20 pranchas por projeto

## Recursos especiais:
- Compara situação atual vs novo layout em reformas
- Conta portas, divisórias, luminárias com especificações
- Marca itens duvidosos em laranja para revisão humana
- Colunas de preço prontas para preenchimento

## Preços:
- Projeto Pequeno (até 5 pranchas): R$ 49
- Projeto Médio (6-10 pranchas): R$ 99 (mais popular)
- Projeto Grande (11+ pranchas): R$ 149
- PRIMEIRO PROJETO É GRÁTIS! Sem cartão de crédito.
- Sem mensalidade — pague por projeto.

## Site: ai.arq.br
## Status: Beta Gratuito com vagas limitadas

## Regras de comportamento:
- Responda SEMPRE em português brasileiro, de forma profissional mas amigável
- Seja conciso — respostas de Instagram devem ser curtas (2-4 frases no máximo)
- Use emojis com moderação (1-2 por mensagem, tipo: ✅ 📐 🏗️ 💡)
- NUNCA prometa valores de orçamento específicos — diga que a plataforma gera o orçamento
- Sempre direcione o usuário para ai.arq.br quando fizer sentido
- Se perguntarem sobre assuntos fora de arquitetura/orçamento, redirecione educadamente
- Se perguntarem preço, informe os planos acima e destaque que o primeiro é grátis
- Se perguntarem como funciona, explique: enviar PDFs → IA analisa → baixar planilha pronta
- Seja entusiasmado com o serviço mas sem exagerar
- NÃO dê conselhos de engenharia estrutural, jurídicos ou financeiros
- Se a pessoa parecer um potencial cliente (arquiteto, engenheiro, decorador), incentive a testar grátis
- Se o usuário mandar "oi", "olá", "bom dia" etc, cumprimente e pergunte como pode ajudar
"""

SYSTEM_PROMPT_CONTENT = """Você é o social media manager da AI.arq, uma plataforma de orçamento de obras com IA.
Seu trabalho é criar conteúdo envolvente para o Instagram sobre arquitetura, reformas e o serviço AI.arq.

## Sobre a AI.arq:
- Transforma pranchas de arquitetura (PDFs) em planilhas de orçamento automaticamente
- Usa inteligência artificial para analisar plantas e extrair quantitativos
- Gera planilhas Excel profissionais com 16 disciplinas de obra
- Segue normas SINAPI/TCPO
- Site: ai.arq.br

## Tipos de conteúdo que você cria:

1. DICA_ARQUITETURA — Dicas práticas sobre materiais, layouts, tendências, reformas
2. DIVULGAÇÃO — Posts sobre funcionalidades e benefícios da AI.arq
3. EDUCAÇÃO_ORÇAMENTO — Explicações sobre como fazer orçamento de obra, o que são quantitativos, SINAPI
4. ESTATÍSTICA — Números e fatos interessantes sobre construção civil no Brasil
5. CURIOSIDADE — Fatos curiosos sobre arquitetura e design

## Regras para legendas:
- Português brasileiro, tom profissional mas acessível
- Máximo 2000 caracteres na legenda
- Comece com um gancho forte (pergunta, dado surpreendente, frase de impacto)
- Termine com um CTA (call to action) — ex: "Acesse ai.arq.br e teste grátis!"
- Inclua quebras de linha para facilitar a leitura
- Use emojis com moderação (3-5 por post)

## Regras para hashtags:
- 20-25 hashtags relevantes
- Mix de hashtags amplas (#arquitetura, #reforma) e nichadas (#orcamentodeobra, #sinapi)
- Sempre incluir: #aiarq #orcamentocomia #arquitetura

## Formato de resposta — SEMPRE retorne JSON válido:
{
  "caption": "texto da legenda aqui",
  "hashtags": ["hashtag1", "hashtag2", ...],
  "image_type": "tip|promo|stat",
  "image_title": "titulo curto para a imagem",
  "image_body": "texto de apoio para a imagem (2-3 frases)",
  "image_stat_number": "130+" (apenas se image_type for "stat"),
  "image_stat_label": "itens identificados" (apenas se image_type for "stat")
}
"""

# Temas pre-definidos para variedade no conteudo automatico
CONTENT_THEMES = [
    {"topic": "Dica sobre escolha de revestimentos para banheiro", "type": "DICA_ARQUITETURA"},
    {"topic": "Como a IA está transformando o setor de construção civil", "type": "DIVULGAÇÃO"},
    {"topic": "O que são quantitativos de obra e por que são importantes", "type": "EDUCAÇÃO_ORÇAMENTO"},
    {"topic": "Número de reformas residenciais no Brasil por ano", "type": "ESTATÍSTICA"},
    {"topic": "Dica sobre iluminação em ambientes corporativos", "type": "DICA_ARQUITETURA"},
    {"topic": "Como a AI.arq extrai itens de uma planta de forro", "type": "DIVULGAÇÃO"},
    {"topic": "Diferença entre SINAPI e TCPO na orçamentação", "type": "EDUCAÇÃO_ORÇAMENTO"},
    {"topic": "Tempo médio gasto fazendo orçamento manualmente vs com IA", "type": "ESTATÍSTICA"},
    {"topic": "Tendências de materiais sustentáveis em 2025", "type": "DICA_ARQUITETURA"},
    {"topic": "Como interpretar uma planta de demolição", "type": "EDUCAÇÃO_ORÇAMENTO"},
    {"topic": "Benefícios de ter um orçamento detalhado antes da obra começar", "type": "EDUCAÇÃO_ORÇAMENTO"},
    {"topic": "Dica sobre tipos de piso para áreas de alto tráfego", "type": "DICA_ARQUITETURA"},
    {"topic": "Como a AI.arq identifica portas e ferragens nas pranchas", "type": "DIVULGAÇÃO"},
    {"topic": "Curiosidade sobre a história do concreto armado no Brasil", "type": "CURIOSIDADE"},
    {"topic": "Erros comuns na hora de fazer um orçamento de obra", "type": "EDUCAÇÃO_ORÇAMENTO"},
    {"topic": "Dica sobre divisórias de vidro em escritórios modernos", "type": "DICA_ARQUITETURA"},
    {"topic": "Quantas disciplinas de obra existem em um projeto comercial", "type": "ESTATÍSTICA"},
    {"topic": "Como funciona a marcenaria sob medida em projetos corporativos", "type": "DICA_ARQUITETURA"},
    {"topic": "A importância do layout na produtividade do escritório", "type": "CURIOSIDADE"},
    {"topic": "Como a AI.arq processa até 20 pranchas em 2 minutos", "type": "DIVULGAÇÃO"},
    {"topic": "Dica sobre forro mineral vs forro de gesso", "type": "DICA_ARQUITETURA"},
    {"topic": "O papel do orçamentista na construção civil", "type": "EDUCAÇÃO_ORÇAMENTO"},
    {"topic": "Tipos de luminárias mais usados em projetos comerciais", "type": "DICA_ARQUITETURA"},
    {"topic": "Como a tecnologia BIM e IA se complementam", "type": "DIVULGAÇÃO"},
    {"topic": "Dica sobre acústica em ambientes abertos de trabalho", "type": "DICA_ARQUITETURA"},
    {"topic": "Percentual de desperdício em obras sem orçamento adequado", "type": "ESTATÍSTICA"},
    {"topic": "Como ler uma planta de pontos elétricos e dados", "type": "EDUCAÇÃO_ORÇAMENTO"},
    {"topic": "A evolução do design de interiores corporativos", "type": "CURIOSIDADE"},
    {"topic": "Funcionalidades da planilha gerada pela AI.arq", "type": "DIVULGAÇÃO"},
    {"topic": "Dica sobre persianas e cortinas em projetos de alto padrão", "type": "DICA_ARQUITETURA"},
]


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY nao configurada")
    return anthropic.Anthropic(api_key=api_key)


# ══════════════════════════════════════════════════════════════════
#  Resposta de DM
# ══════════════════════════════════════════════════════════════════

def generate_dm_reply(
    conversation_history: list[dict],
    incoming_message: str,
) -> str:
    """Gera resposta inteligente para uma DM do Instagram.

    Args:
        conversation_history: lista de {"role": "user"|"assistant", "text": "..."}
        incoming_message: mensagem que acabou de chegar

    Returns:
        Texto da resposta (max ~1000 chars pro Instagram)
    """
    client = _get_client()

    # Montar mensagens no formato da API Anthropic
    messages = []
    for msg in conversation_history[-8:]:  # ultimas 8 msgs de contexto
        role = msg["role"] if msg["role"] in ("user", "assistant") else "user"
        messages.append({"role": role, "content": msg["text"]})

    # Adicionar mensagem nova
    messages.append({"role": "user", "content": incoming_message})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            temperature=0.7,
            system=SYSTEM_PROMPT_DM,
            messages=messages,
        )

        reply = response.content[0].text.strip()
        # Garantir que nao excede limite do Instagram DM
        if len(reply) > 1000:
            reply = reply[:997] + "..."
        return reply

    except Exception as e:
        logger.error(f"Erro gerando resposta de DM: {e}")
        return "Oi! Obrigado por entrar em contato. Acesse ai.arq.br para conhecer nosso servico de orcamento com IA! 📐"


# ══════════════════════════════════════════════════════════════════
#  Geracao de conteudo para posts
# ══════════════════════════════════════════════════════════════════

def generate_post_content(
    topic: str,
    content_type: str = "DICA_ARQUITETURA",
) -> dict:
    """Gera conteudo completo para um post (legenda + hashtags + dados da imagem).

    Returns:
        dict com: caption, hashtags, image_type, image_title, image_body, etc.
    """
    client = _get_client()

    prompt = f"""Crie um post de Instagram sobre o seguinte tema:

Tema: {topic}
Tipo de conteudo: {content_type}

Retorne APENAS o JSON, sem markdown, sem explicacao."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            temperature=0.8,
            system=SYSTEM_PROMPT_CONTENT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()

        # Limpar caso venha com markdown code block
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        # Validar campos obrigatorios
        assert "caption" in result
        assert "hashtags" in result
        assert "image_type" in result
        assert "image_title" in result

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Erro parseando JSON do conteudo: {e}")
        return _fallback_content(topic)
    except Exception as e:
        logger.error(f"Erro gerando conteudo: {e}")
        return _fallback_content(topic)


def get_next_theme(last_index: int = -1) -> dict:
    """Retorna o proximo tema do calendario rotativo."""
    next_idx = (last_index + 1) % len(CONTENT_THEMES)
    return {**CONTENT_THEMES[next_idx], "index": next_idx}


def _fallback_content(topic: str) -> dict:
    """Conteúdo de fallback caso a IA falhe."""
    return {
        "caption": (
            f"💡 {topic}\n\n"
            "A AI.arq transforma suas pranchas de arquitetura em planilhas "
            "de orçamento completas, usando inteligência artificial.\n\n"
            "📐 Acesse ai.arq.br e teste agora!"
        ),
        "hashtags": [
            "aiarq", "orcamentocomia", "arquitetura", "reforma",
            "construcaocivil", "engenharia", "projeto", "obra",
            "plantabaixa", "designdeinteriores", "orcamentodeobra",
        ],
        "image_type": "tip",
        "image_title": topic[:60],
        "image_body": "Acesse ai.arq.br para saber mais sobre como a IA pode transformar seu fluxo de trabalho.",
    }
