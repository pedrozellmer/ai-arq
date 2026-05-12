# Histórico Completo da Sessão — AI.arq

## Resumo do Projeto
- **Produto**: AI.arq — Planilha de Orçamento com IA
- **Site**: ai.arq.br
- **Backend**: ai-arq.onrender.com
- **Domínio**: ai.arq.br (Registro.br)
- **Instagram**: @ai.arq.br
- **Facebook**: AI.arq

---

## O que foi construído (em ordem cronológica)

### Fase 1: Orçamento do Projeto Vista Guanabara
- Leitura de 10 pranchas PDF de arquitetura (Demolição, Layout, Arquitetura, Pisos, Forro, Pontos, Marcenaria, Mobiliário)
- Extração de texto com pdfplumber
- Renderização de imagens com pypdfium2
- Análise com Claude API (vision)
- Geração de planilha .xlsx com openpyxl
- 5 versões da planilha (v1 a v5) com refinamentos progressivos
- Comparativo com orçamento gerado pelo GPT
- Pesquisa de melhores práticas (SINAPI, TCPO, NBR)
- PDF comparativo de fornecedores (modelo)

### Fase 2: Landing Page e Site
- Landing page HTML com Tailwind CSS (4 opções de cor testadas — escolhida: gradiente indigo→cyan)
- Domínio ai.arq.br registrado no Registro.br
- Deploy no GitHub Pages (pedrozellmer.github.io/ai-arq)
- DNS configurado (A record → GitHub Pages)
- Favicon personalizado (logo AI gradiente)
- Open Graph tags para WhatsApp/Facebook/LinkedIn
- robots.txt para permitir scraping social

### Fase 3: Backend
- FastAPI com Python
- Endpoints: /api/process, /api/status, /api/download, /api/health, /api/checkout
- Processamento prancha por prancha (economia de memória)
- DPI 120, max 1000px, JPEG 80%, gc.collect()
- Deploy no Render (Standard $25/mês, 2GB RAM)
- Autodeploy configurado
- Threading separado para não bloquear HTTP
- Jobs salvos em arquivo JSON (sobrevive restarts)

### Fase 4: Autenticação e Cadastro
- Login com Google (Supabase Auth + Google OAuth)
- Login com email/senha
- Cadastro complementar (WhatsApp, CPF/CNPJ, empresa, área, cargo)
- Cadastro não obrigatório (banner suave em vez de redirect forçado)
- Google Cloud Console configurado (OAuth client, consent screen, produção)

### Fase 5: Dashboard
- Sidebar com navegação (Novo Projeto, Meus Projetos, Cashback, Como Funciona, Meu Cadastro, Meus Pagamentos, FAQ)
- Upload drag & drop com dropdown de tipo de prancha (auto-detecta)
- Campo nome do projeto (pré-preenchido com data)
- Progresso real do servidor (não fake)
- Tempo estimado dinâmico (~40s/prancha)
- Lista de arquivos por projeto (expansível no histórico)
- Aviso de poucos itens (≤3 pranchas)
- Guia pré-upload (quais pranchas enviar)
- Ícone de casinha animado durante processamento

### Fase 6: Pagamento
- Stripe integrado (cartão + PIX)
- Preços: R$49 (≤5 pranchas), R$99 (6-10), R$149 (11+)
- Primeiro projeto grátis
- Códigos beta para acesso gratuito (BETA-AI.ARQ-NOME)
- Cashback R$20 por enviar planilha revisada

### Fase 7: Páginas Legais e FAQ
- Termos de Uso (15 seções, LGPD, limitações da IA)
- Política de Privacidade (10 seções, dados reais auditados)
- FAQ (27 perguntas, 6 seções, accordion com busca)
- Todas reescritas com dados reais do sistema

### Fase 8: Painel Admin
- URL secreta: ai.arq.br/admin.html
- Acesso restrito ao email admin (zarelalopes@gmail.com)
- Dashboard: total usuários, códigos beta, receita
- Usuários: tabela com todos os cadastros + busca
- Códigos Beta: gerar novos, ver uso, desativar
- Botão "Painel Admin" no sidebar (só pro admin)

### Fase 9: Instagram e Facebook
- Conta Instagram: @ai.arq.br (profissional)
- Página Facebook: AI.arq (vinculada ao Instagram)
- Meta Developer App: AI.arq (com Instagram Content Publishing API)
- Testador do Instagram configurado
- Token de acesso gerado e testado
- Logo dark centralizado criado

---

## Credenciais e Configurações

### Supabase
- URL: https://kqjabzwgbfuivzlcfvvu.supabase.co
- Anon Key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
- Tabelas: profiles, beta_codes

### Render
- Serviço: ai-arq (Standard, 2GB RAM)
- URL: https://ai-arq.onrender.com
- Variáveis: ANTHROPIC_API_KEY, STRIPE_SECRET_KEY
- Autodeploy: On Commit

### Stripe
- Publishable Key: pk_live_51SafSd0t4KZGOuLP...
- Métodos: Cartão + PIX

### Google Cloud
- Projeto: ai-arq
- OAuth Client ID: 558106235498-j3gsv9gup0abudhamphvtmii20o5c7n9.apps.googleusercontent.com
- Status: Em produção (até 100 usuários)

### Meta Developer
- App: AI.arq
- App ID: 1213702540634947
- Instagram App ID: 1421819986294553
- Instagram User ID: 27523351593920440

### GitHub
- Repo: pedrozellmer/ai-arq
- GitHub Pages: ativo com custom domain ai.arq.br

---

## Arquivos do Projeto

### Frontend (GitHub Pages)
- index.html — Landing page
- login.html — Login (Google + Email)
- cadastro.html — Cadastro complementar
- dashboard.html — Dashboard principal
- admin.html — Painel administrativo
- termos.html — Termos de Uso
- privacidade.html — Política de Privacidade
- faq.html — FAQ (27 perguntas)
- favicon.ico / favicon.png — Logo
- og-image.png — Preview para WhatsApp/redes
- robots.txt — Permissões de scraping

### Backend (Render)
- backend/main.py — FastAPI endpoints + Stripe
- backend/processor.py — Pipeline de PDFs
- backend/analyzer.py — Claude API Vision (prompts por prancha)
- backend/spreadsheet.py — Gerador de planilha .xlsx
- backend/models.py — Pydantic models
- backend/Dockerfile — Deploy container
- backend/requirements.txt — Dependências

---

## Pesquisas Realizadas
- Benchmark AECV-bench (acurácia IA em plantas: 40-60% símbolos, 95% texto)
- Togal.AI, Beam AI, Civils.ai (concorrentes)
- SINAPI, TCPO (referências de custo Brasil)
- NBR 8995 (iluminação), NBR 10897 (sprinklers)
- Claude Vision best practices (temperature=0, contagem por fórmula)
- Guia de planilha orçamentária obra privada (BDI 30%, EAP)
- Fórmulas: pintura (TCPO vãos ≤2m²), pisos (+10% perda), AC (600-800 BTU/m²)

---

## Bugs Corrigidos (21 total)
- Texto corrompido "orconcorrência" (6 locais)
- Tag </button> em vez de </a> no CTA
- Links mortos no footer do login
- Texto duplicado "do projeto do projeto"
- "as arquivos" → "os arquivos"
- FAQ BIM com accordion quebrado
- Copyright © em todas as páginas
- currentUser não declarado globalmente
- Busca por coluna 'id' inexistente
- Redirect forçado pro cadastro
- Flash da página de cadastro no login
- Tempo estimado desproporcional
- Servidor 502 durante processamento (threading fix)
- Memory exceeded no Render (DPI/crops otimizados)

---

## Próximos Passos
1. Agente de posts automáticos no Instagram (token pronto, falta criar agente)
2. Calibrar IA com mais projetos reais (beta testers)
3. Email profissional contato@ai.arq.br (Zoho Mail)
4. Suporte a DWG (futuro)
5. Segundo produto: renderização 3D com IA (futuro)
