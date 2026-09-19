# myVita — Backend

## Como correr (Docker — recomendado)

```bash
cd myvita
cp backend/.env.example backend/.env
```

Abre `backend/.env` e substitui `JWT_SECRET_KEY` por um valor real, por exemplo gerado com:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Depois:
```bash
docker compose up --build
```

- API: http://localhost:8000
- Docs interativas (Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/health · Ready (confirma ligação à BD): http://localhost:8000/ready

Para parar: `Ctrl+C`, depois `docker compose down` (ou `docker compose down -v` para apagar também os dados da BD).

## Correr sem Docker (dev local)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edita DATABASE_URL para apontar a um Postgres local
alembic upgrade head
uvicorn app.main:app --reload
```

## Migrations

```bash
cd backend
alembic upgrade head                 # aplicar
alembic revision --autogenerate -m "descrição"   # nova migration
alembic downgrade -1                 # reverter a última
```

## Testes

Requer um Postgres real acessível (não SQLite — ver `tests/conftest.py` para porquê).

```bash
cd backend
pip install -r requirements.txt --break-system-packages
export TEST_DATABASE_URL=postgresql+psycopg://myvita:myvita@localhost:5432/myvita
export DATABASE_URL=$TEST_DATABASE_URL   # audit logging escreve através desta ligação — ver app/core/audit.py
pytest -v --cov=app
```

## Qualidade de código

```bash
cd backend
ruff check .        # lint
mypy app             # type checking
pip-audit -r requirements.txt   # dependências vulneráveis/desatualizadas
```

Configuração em `backend/pyproject.toml`. O CI (`.github/workflows/ci.yml`) corre exatamente estes comandos, mais as migrations, em cada push/PR, contra um Postgres real (serviço do GitHub Actions, não SQLite).

## Segurança: CSRF

Todos os pedidos autenticados que mudam estado (`POST`/`PUT`/`PATCH`/`DELETE`) exigem um token CSRF, além do cookie de sessão. Estratégia: **double-submit cookie assinado (HMAC) e ligado à sessão**.

Como o frontend deve usar isto:
1. Após login/registo, o backend define dois cookies: `myvita_session` (httpOnly, como sempre) e `myvita_csrf` (**não** httpOnly — de propósito, para o JS conseguir lê-lo).
2. Antes de qualquer `POST`/`PUT`/`PATCH`/`DELETE`, lê o valor de `myvita_csrf` via `document.cookie` e envia-o no header `X-CSRF-Token`.
3. Pedidos `GET`/`HEAD`/`OPTIONS` não precisam deste header.

```js
function getCookie(name) {
  return document.cookie.split('; ').find(r => r.startsWith(name + '='))?.split('=')[1];
}

fetch('/api/v1/staff', {
  method: 'POST',
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': getCookie('myvita_csrf'),
  },
  body: JSON.stringify(payload),
});
```

O token CSRF invalida-se automaticamente ao fazer logout (está ligado ao `token_epoch` do utilizador) — não precisas de o gerir manualmente além de o reler a cada login.

## Security

- **Passwords:** Argon2id, política mínima aplicada de forma consistente no registo de paciente, criação de staff e onboarding de clínica (`app/core/validators.py`).
- **Sessões:** cookie httpOnly + JWT (HS256/384/512 apenas — outros algoritmos são rejeitados no arranque), invalidação imediata via `token_epoch` (logout, mudança de password).
- **CSRF:** ver secção acima.
- **Rate limiting:** login (10/min), registo de paciente e onboarding de clínica (5/min), criação de staff (20/min) — tudo por IP (`app/core/rate_limit.py`). Armazenamento em memória, adequado a uma única réplica; ver comentário no ficheiro para o que muda com múltiplas réplicas (Redis).
- **Security headers:** `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, e `Strict-Transport-Security` quando `ENVIRONMENT=production`.
- **Multi-tenancy:** isolamento por `clinic_id` reforçado a nível de serviço (nunca confia em `clinic_id` vindo do payload do cliente); testado explicitamente contra IDOR entre clínicas.
- **Audit logging:** ver secção própria abaixo.
- **Timing side-channel:** `authenticate()` executa sempre uma verificação Argon2 completa, mesmo para emails inexistentes, para não revelar por timing quais emails têm conta.
- **Não fazemos (ainda):** rotação automática de secrets, 2FA, bloqueio de conta após N tentativas falhadas (o rate limiting por IP mitiga parcialmente).

## Audit logging & acesso clínico

Tabela única `audit_logs` (ver `app/models/audit_log.py` para a justificação de não a separar em duas). Cobre:

- Eventos de segurança: `LOGIN_SUCCESS`/`LOGIN_FAILURE`, `LOGOUT`, `PATIENT_CREATED`, `STAFF_CREATED`, `CLINIC_CREATED`, `PERMISSION_DENIED`, `CSRF_FAILURE`, `RATE_LIMITED`.
- Acesso clínico: `STAFF_VIEWED_APPOINTMENT`, `PATIENT_VIEWED_OWN_RECORD` — atualmente instrumentado na listagem de consultas (`GET /api/v1/appointments`), que é o único endpoint de leitura de dados sensíveis que existe hoje no código. **Não há ainda endpoints de leitura/detalhe de ficha de paciente** — quando existirem, devem emitir `STAFF_VIEWED_PATIENT` da mesma forma.

Cada escrita usa a sua própria sessão de BD (`app/core/audit.py`), independente da transação do pedido que a originou — assim uma falha de login ou uma transação revertida não apagam o registo de auditoria. Nunca contém passwords, JWTs, cookies, tokens CSRF, ou dados clínicos — só identificadores mínimos. Ver testes em `tests/test_audit_logging.py`, incluindo um teste dedicado a confirmar que nenhuma password aparece na tabela.

## Backups & Recovery

```bash
# Backup (produz um .dump em ./backups, ou no diretório indicado)
DB_HOST=localhost DB_PORT=5432 DB_NAME=myvita DB_USER=myvita PGPASSWORD=... \
  ./scripts/backup_db.sh ./backups

# Restore (destrutivo — pede confirmação a menos que passes --yes)
DB_HOST=localhost DB_PORT=5432 DB_NAME=myvita DB_USER=myvita PGPASSWORD=... \
  ./scripts/restore_db.sh ./backups/myvita_20260101T000000Z.dump
```

Um volume Docker (`myvita_pg_data`) **não é um backup** — protege contra o container ser removido, não contra uma migration má, um `DELETE` errado, ou o disco corromper. Os scripts acima é que são o backup real; ambos falham alto (`set -euo pipefail`) e nunca aceitam a password como argumento de linha de comandos.

**RPO/RTO — valores de referência, não requisitos definidos.** Isto precisa de decisão operacional (com que frequência corre o backup, onde fica guardado, quem o monitoriza):
- RPO proposto: 24h (backup diário) — reduz para o intervalo real escolhido.
- RTO proposto: poucas horas, dependendo do tamanho da BD e de onde o backup está guardado.

Procedimento de disaster recovery:
```
Falha da base de dados
        ↓
Provisionar novo PostgreSQL
        ↓
scripts/restore_db.sh <último backup>
        ↓
alembic upgrade head   (se o backup for anterior à migration atual)
        ↓
Verificar /health e /ready
        ↓
Verificar login/CRUD básico manualmente
```

## Production

`docker-compose.prod.yml` é o ficheiro de produção — separado do `docker-compose.yml` de desenvolvimento, que monta o código como volume e expõe o Postgres no host (nenhum dos dois é aceitável em produção).

```bash
docker compose -f docker-compose.prod.yml up -d
```

Diferenças chave em relação ao dev:
- `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`JWT_SECRET_KEY`/`CORS_ORIGINS` são **obrigatórios, sem default** — o compose recusa arrancar se faltar algum.
- Postgres não expõe a porta 5432 ao host — só é acessível a partir do container `backend`.
- Sem volumes de código montados — corre exatamente o que está na imagem construída pelo `Dockerfile`.
- `ENVIRONMENT=production`, `DEBUG=false`, `COOKIE_SECURE=true` fixos (a app recusa arrancar com `COOKIE_SECURE=false` em produção — ver `app/core/config.py`).
- Backend continua a correr como utilizador não-root (herdado do `Dockerfile`, igual em dev e produção).
- Agnóstico de cloud — corre da mesma forma numa VPS, AWS/Azure/GCP, ou qualquer host Docker. Não inclui reverse proxy/TLS — coloca um (nginx, Caddy, Traefik, ou o LB da tua cloud) à frente do serviço `backend`.

## Observability

- Logging estruturado por texto (JSON ainda não — ver "Por fazer"), com nível `INFO` por omissão e `DEBUG` apenas quando `DEBUG=true` (nunca em produção).
- Eventos de auditoria (`myvita.audit`) e de autenticação (`myvita.auth`) em loggers próprios — nunca imprimem passwords/tokens.
- `/health` — o processo está vivo (sem dependências externas, rápido).
- `/ready` — confirma ligação à base de dados; usa isto nos healthchecks do orquestrador, não no load balancer de alta frequência.
- Métricas (contagem de pedidos, erros, rate limiting): **por fazer** — ver secção seguinte.

## Estado atual

Implementado:
- Modelos: `User`, `Clinic`, `Patient`, `Staff`, `Appointment`, `AuditLog`, com isolamento multi-tenant via `clinic_id`
- Migrations validadas (upgrade/downgrade reversível, testado com Postgres real, inclusive em CI)
- Auth: Argon2id, cookie httpOnly + JWT, invalidação de sessão via `token_epoch`, algoritmo JWT restrito a HMAC
- Proteção CSRF: double-submit cookie assinado (HMAC), ligado à sessão
- Rate limiting em login, registo de paciente, onboarding de clínica e criação de staff
- Security headers (`X-Frame-Options`, HSTS em produção, etc.)
- Audit logging + clinical access logging (tabela `audit_logs`, sessão própria, sem dados sensíveis)
- Endpoints: onboarding de clínica, registo de paciente, gestão de staff, marcação de consultas, login/logout/me
- Proteção anti-IDOR: uma clínica nunca consegue marcar consultas usando pacientes/staff de outra clínica (testado e bloqueado)
- CI (GitHub Actions): lint (ruff), type checking (mypy), testes com Postgres real, migrations (upgrade + downgrade + upgrade), coverage, scan de dependências (pip-audit), build da imagem Docker
- Dependabot (pip, GitHub Actions, Docker base image)
- Backup/restore com verificação de integridade (`scripts/backup_db.sh`, `scripts/restore_db.sh`)
- `docker-compose.prod.yml` separado do dev, sem defaults inseguros, sem exposição desnecessária da BD
- 55 testes automatizados, 97% de cobertura de linhas em `app/`

Por fazer:
- Endpoints para atualizar/cancelar consultas (`PATCH`/`DELETE`) — e, quando existirem, os eventos `APPOINTMENT_UPDATED`/`APPOINTMENT_CANCELLED` já definidos em `AuditAction`
- Endpoints de leitura/detalhe de ficha de paciente — e o evento `STAFF_VIEWED_PATIENT` já definido, à espera de ter onde ligar
- Modelos adiados: `Medication`, `Notification`, `Consent`
- Logging estruturado em JSON e `request_id` por pedido
- Métricas (contagem/duração de pedidos, erros, eventos de rate limiting)
- Bloqueio de conta após N tentativas falhadas (hoje mitigado só pelo rate limiting por IP)
- Backup automatizado agendado (os scripts existem; falta o cron/scheduler que os invoca em produção)

## Notas para produção que dependem do ambiente de deployment

O que está implementado no código não substitui isto — depende de decisões e infraestrutura fora do repositório:
- Onde e com que frequência o backup corre de facto (o script existe; o agendamento não está no código)
- Reverse proxy / TLS em frente ao backend
- Gestão real de secrets (GitHub Secrets para CI; um vault/secret manager para produção — nunca um `.env` commitado)
- Valores de RPO/RTO acordados operacionalmente, não os valores de referência acima
- Monitorização/alerting sobre os logs e sobre falhas de `/ready`
