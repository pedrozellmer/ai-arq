# Análise de Concorrência — AI.arq (junho/2026)

> Estudo multi-agente de 12 concorrentes BR de IA para orçamento/quantitativo de obra.
> 11 vivos, 1 provavelmente morto (MadeAI/arqcloud). Foco: onde o AI.arq joga.

## 1. Mapa do mercado

### Vivos e confirmados

| Concorrente | Vivo? | Orçamento c/ R$? | Lê BIM/IFC? | Lê CAD/planta de verdade? | Preço | Ameaça |
|---|---|---|---|---|---|---|
| **Concretu** | Sim | Sim | Não | Não (chat/texto) | Assinatura, trial | **ALTA** |
| **Vobi** | Sim (YC W22, ~US$5M) | Sim | Não | Não (sensor de cômodo) | ~R$103/mês | Média |
| **VIGHA** | Sim (10 anos) | Sim | Não | Não (texto) | R$96/mês | Média |
| **Orçafascio** | Sim (incumbente) | Sim | Sim (Revit) | Não (texto) | R$180/mês | Média |
| **Calc Gênio** | Sim (early) | Sim | Não | **Sim — imagem/PDF raster** | R$79/mês | Média |
| **Brickup** | Sim | Sim | Não | Não | Freemium | Média |
| **Obra Prima** | Sim (gigante gestão) | Sim | Não | Não | Sob consulta | Média (latente) |
| **i9 Orçamentos** | Sim (8 anos) | Sim | Não | Não (texto) | R$80-132/mês | Baixa |
| **Sienge (Softplan)** | Sim (líder ERP) | Sim | Não | Não (paramétrico) | Enterprise | Baixa |
| **eCustos** | Sim | Sim | Não | Não (paramétrico) | R$60-80/mês | Baixa |
| **Construflow** | Sim | Não | Não | Não | R$700-1.700/mês | Baixa |

### Provavelmente morto
- **MadeAI (arqcloud):** vitrine bonita mas /sobre e /preços em 404, preços não renderizam, LinkedIn errado, zero imprensa, zero social. Números (450 clientes, 98%) sem corroboração. **Não é ameaça hoje.** (Instinto do Pedro confirmado: IG parado desde 2019.)

## 2. Leitura do espaço
Mercado **lotado de "gerador de orçamento com preço", quase vazio no nicho do AI.arq**. Padrão quase universal:
1. **Todos precificam** (10 de 11) — orçamento via SINAPI é commodity, piso da categoria.
2. **Quase todos são assinatura mensal** — avulso/1º-grátis é raríssimo.
3. **A "IA" parte de TEXTO/parâmetros, não da prancha** — VIGHA, i9, Sienge, eCustos, Orçafascio, Concretu, Brickup geram orçamento de uma *descrição digitada* ("casa 110m² padrão médio"). **Ninguém abre o DWG e mede a geometria.**
4. **Maioria é suíte de gestão (ERP do setor)** — Vobi, Sienge, Brickup, Obra Prima. Quantitativo é módulo, no máximo.

**Quem importa:** Concretu (posicionamento/tom mais próximos, mas lê por texto), Calc Gênio (único que promete ler a planta, mas early + só raster + vai bater na armadilha do PDF sem texto), Vobi (ameaça por distribuição/dinheiro, mas não lê CAD).

**Buraco desocupado:** "**medir a prancha de verdade**" (DWG/DXF, esquadrias, divisórias, MEP). Os players sérios não fizeram isso.

## 3. Diferenciais reais do AI.arq
1. **Mede a geometria do CAD (DWG/DXF), não chuta por texto** — diferencial técnico quase exclusivo e difícil de copiar.
2. **Semáforo branco=medido / laranja=estimado** — ninguém tem; todos são caixa-preta com "98% de precisão".
3. **1º grátis + avulso, sem assinatura** — quase todos exigem virar assinante pra testar.

### Onde fica atrás
- Não entrega o R$ final que o leigo "quer ver"; não lê BIM/IFC; sem suíte/lock-in; sem distribuição/marca (Vobi 109K IG, Sienge 38K); a armadilha do PDF vetorial sem texto (qty=0).

## 4. A tensão "só quantitativo, sem preço"
**Veredito: vantagem defensável, mas hoje mal vendida.** O problema não é a regra, é a comunicação. "Não fazemos orçamento" soa como menos produto — mas o AI.arq faz a parte **mais difícil e valiosa** (medir da prancha) e deixa de fora a **trivial e perigosa** (colar preço SINAPI genérico ignorando BDI/fornecedor/região). Todo concorrente que promete preço exato está chutando, e o orçamentista sabe disso.

**Recomendação:** MANTER e AFIAR o porquê. Não virar precificador. Opcional (passo 2): preço-referência SINAPI marcado **laranja**, por item, com fonte+data, nunca total fechado — respeita a regra dura e fecha o gap psicológico do "quero ver um número".

## 5. Ações priorizadas (fundador solo, beta)
1. **[RÁPIDO]** Reposicionar em "medimos sua prancha de verdade" + honestidade (vs o chute paramétrico dos outros).
2. **[RÁPIDO]** "Teste do desafio" como gancho: *suba a prancha, veja item por item o que foi MEDIDO vs estimado, sem cartão*.
3. **[RÁPIDO]** Conteúdo: "Por que não te entregamos o preço (e por que isso te protege)" — vira objeção em diferencial + SEO.
4. **[RÁPIDO]** Educação PDF vetorial sem texto + empurrar DWG/DXF no onboarding (parte já existe).
5. **[MÉDIO]** Preço-referência SINAPI laranja (opcional, por item, fonte+data).
6. **[MÉDIO]** Exportação Excel estruturada por capítulo SINAPI — vira o passo *anterior* ao i9/Orçafascio/eCustos (complemento, não concorrente).
7. **[MÉDIO]** Provar tração com 3-5 casos reais ponta-a-ponta (régua de ligar cobrança).
8. **[DECISÃO]** NÃO construir BIM/IFC, suíte de gestão nem cronograma pago agora — onde os gigantes são imbatíveis e o diferencial some.

## 6. Aposta nº 1 (próximos 60 dias)
**"O Raio-X da sua prancha":** tornar o "medido vs estimado" o produto inteiro, usado como arma de aquisição via o teste grátis sem atrito.

> *"Suba o DWG, receba em minutos um quantitativo onde cada item vem marcado — BRANCO = medi de verdade no seu desenho, LARANJA = estimativa, revise. Sem cartão. Sem assinatura. O preço é seu."*

É o cruzamento dos 3 diferenciais únicos (mede CAD + honestidade + atrito zero) — nenhum concorrente tem os três. 100% executável por fundador solo: é posicionamento + landing + onboarding. O motor e o semáforo **já existem** — é vender o que já tem, do ângulo certo.

---
*Regras de copy pública (consultar antes de mexer na landing): fonte em toda afirmação técnica (NBR/SINAPI com data), cor+ícone+texto (daltonismo), nada interno exposto.*
