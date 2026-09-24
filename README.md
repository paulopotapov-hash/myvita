# myVita — Backend + Frontend

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

- Frontend: http://localhost:5173
- API: http://localhost:8000
- Docs interativas (Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/health · Ready (confirma ligação à BD): http://localhost:8000/ready

Para parar: `Ctrl+C`, depois `docker compose down` (ou `docker compose down -v` para apagar também os dados da BD).

Documentação específica do frontend (stack, variáveis de ambiente, decisões de segurança, recomendação de produção): `frontend/README.md`.

## Correr sem Docker (dev local)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edita DATABASE_URL para apontar a um Postgres local
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend, num terminal separado:
```bash
cd frontend
npm install
npm run dev
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
export JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")  # >=32 bytes, exigido no arranque
pytest -v --cov=app
```

## Qualidade de código

```bash
cd backend
ruff check .        # lint
mypy app             # type checking
pip-audit -r requirements.txt   # dependências vulneráveis/desatualizadas (ver política abaixo)
```

Configuração em `backend/pyproject.toml`. O CI (`.github/workflows/ci.yml`) corre exatamente estes comandos, mais as migrations, em cada push/PR, contra um Postgres real (serviço do GitHub Actions, não SQLite).

**Política de dependency scanning:** o `pip-audit` do CI **bloqueia o build**, não é meramente informativo. Uma vulnerabilidade nova e sem exceção documentada falha o CI. Exceções só existem com justificação escrita, uma a uma, em `backend/SECURITY-EXCEPTIONS.md` — atualmente cobre CVEs do `starlette` (transitivo via `fastapi`) sem fix compatível com a versão atual do FastAPI sem um upgrade major; confirmámos por grep que o código não usa nenhuma das superfícies afetadas.

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
- **Sessões:** cookie httpOnly + JWT (HS256/384/512 apenas — outros algoritmos são rejeitados no arranque; chave mínima de 32 bytes, também imposta no arranque), invalidação imediata via `token_epoch` (logout, mudança de password).
- **CSRF:** ver secção acima.
- **Rate limiting:** login (10/min), registo de paciente e onboarding de clínica (5/min), criação de staff (20/min) — tudo pelo IP real do cliente (`app/core/client_ip.py`, ver nota sobre trusted proxy abaixo), não pelo IP do reverse proxy. Armazenamento em memória, adequado a uma única réplica; ver comentário em `app/core/rate_limit.py` para o que muda com múltiplas réplicas (Redis).
- **Security headers:** `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, e `Strict-Transport-Security` quando `ENVIRONMENT=production`.
- **CORS:** origins, métodos (`GET`/`POST`/`PATCH`/`DELETE`) e headers (`Content-Type`, `X-CSRF-Token`, `X-Request-ID`) explícitos — nunca `*`. Produção recusa arrancar com `CORS_ORIGINS` vazio ou contendo `*` (incompatível com `allow_credentials=True`, que a app usa para os cookies).
- **Trusted proxy / IP do cliente:** `X-Forwarded-For` só é aceite quando o peer TCP direto está em `TRUSTED_PROXIES` (vazio por padrão — nada é confiado até se configurar explicitamente). Sem isto, qualquer cliente podia falsificar o próprio IP e contornar rate limiting ou poluir o audit log — ver `app/core/client_ip.py`.
- **Multi-tenancy:** isolamento por `clinic_id` reforçado a nível de serviço (nunca confia em `clinic_id` vindo do payload do cliente); testado explicitamente contra IDOR entre clínicas.
- **Audit logging:** ver secção própria abaixo.
- **Timing side-channel:** `authenticate()` executa sempre uma verificação Argon2 completa, mesmo para emails inexistentes, para não revelar por timing quais emails têm conta.
- **Tratamento de erros:** exceções não tratadas e erros de base de dados nunca devolvem stack traces, SQL, ou credenciais ao cliente — apenas uma mensagem genérica; o detalhe fica nos logs internos, associado ao `request_id` (ver Observability abaixo). Ver `app/main.py`.
- **Não fazemos (ainda):** rotação automática de secrets, 2FA, bloqueio de conta após N tentativas falhadas (o rate limiting por IP mitiga parcialmente).

## Audit logging & acesso clínico

Tabela única `audit_logs` (ver `app/models/audit_log.py` para a justificação de não a separar em duas). Cobre:

- Eventos de segurança: `LOGIN_SUCCESS`/`LOGIN_FAILURE`, `LOGOUT`, `PATIENT_CREATED`, `STAFF_CREATED`, `CLINIC_CREATED`, `PERMISSION_DENIED`, `CSRF_FAILURE`, `RATE_LIMITED`.
- Acesso clínico: `STAFF_VIEWED_APPOINTMENT`, `PATIENT_VIEWED_OWN_RECORD` — atualmente instrumentado na listagem de consultas (`GET /api/v1/appointments`), que é o único endpoint de leitura de dados sensíveis que existe hoje no código. **Não há ainda endpoints de leitura/detalhe de ficha de paciente** — quando existirem, devem emitir `STAFF_VIEWED_PATIENT` da mesma forma.

Cada escrita usa a sua própria sessão de BD (`app/core/audit.py`), independente da transação do pedido que a originou — assim uma falha de login ou uma transação revertida não apagam o registo de auditoria. Nunca contém passwords, JWTs, cookies, tokens CSRF, ou dados clínicos — só identificadores mínimos. Ver testes em `tests/test_audit_logging.py`, incluindo um teste dedicado a confirmar que nenhuma password aparece na tabela.

## Backups & Recovery

O Compose de produção inclui um serviço `backup` dedicado. Ele espera pela base de dados, faz um backup inicial ao arrancar e depois executa `pg_dump -Fc` diariamente às 03:00 UTC. Os dumps e respetivos checksums SHA-256 ficam no volume persistente separado `myvita_backups`; o serviço só pertence à rede interna `data` e não publica portas.

Configuração opcional:

```env
BACKUP_SCHEDULE=0 3 * * *
BACKUP_RETENTION_DAYS=14
BACKUP_TIMEZONE=UTC
BACKUP_RUN_ON_START=true
```

`BACKUP_SCHEDULE` usa cinco campos cron. A retenção corre apenas depois de um backup bem-sucedido e elimina somente pares `myvita_*.dump`/`.sha256` expirados; ficheiros temporários nunca são considerados backups. Cada dump é escrito num ficheiro temporário com permissões restritas, validado com `pg_restore --list`, renomeado atomicamente e só depois recebe o checksum.

Verificar o backup mais recente (por omissão deve ter menos de 36 horas):

```bash
docker compose -f docker-compose.prod.yml exec -T backup \
  su-exec postgres /opt/myvita/check_backup.sh /backups
```

Para um restore, identifica primeiro o dump dentro do serviço e executa o script com confirmação explícita. O script valida o checksum e o arquivo antes de tocar na base de dados:

```bash
docker compose -f docker-compose.prod.yml exec backup sh -lc 'ls -lh /backups/myvita_*.dump'
docker compose -f docker-compose.prod.yml exec -T backup \
  su-exec postgres /opt/myvita/restore_db.sh /backups/myvita_YYYYMMDDTHHMMSSZ.dump --yes
```

O segundo comando é destrutivo para `POSTGRES_DB`; revê o alvo e o ficheiro antes de usar `--yes`. Para operações manuais fora do container continuam disponíveis os scripts:

```bash
# Backup (produz um .dump em ./backups, ou no diretório indicado)
DB_HOST=localhost DB_PORT=5432 DB_NAME=myvita DB_USER=myvita PGPASSWORD=... \
  ./scripts/backup_db.sh ./backups

# Restore (destrutivo — pede confirmação a menos que passes --yes)
DB_HOST=localhost DB_PORT=5432 DB_NAME=myvita DB_USER=myvita PGPASSWORD=... \
  ./scripts/restore_db.sh ./backups/myvita_20260101T000000Z.dump
```

O volume PostgreSQL (`myvita_pg_data`) **não é um backup**. O volume separado `myvita_backups` permite recuperar de uma migration ou `DELETE` acidental, mas continua no mesmo host. Não protege contra perda, corrupção ou comprometimento do host; cópias off-site ficam deliberadamente para P2.2. Os backups também não são cifrados pela aplicação, portanto o acesso ao host e ao volume deve ser restrito.

**Verificado operacionalmente** (não é só "os scripts existem"):
- `backup_db.sh` falha com código de saída 1 e sem ficheiro parcial quando o Postgres está inacessível (testado apontando para uma porta fechada).
- Nenhuma password aparece no terminal ou nos logs — o scheduler cria um `PGPASSFILE` com modo `0600`, fora do volume e do Git.
- `restore_db.sh` recusa avançar sem o nome exato da BD escrito na confirmação (ou `--yes` explícito).
- Ciclo completo backup → restore para uma BD nova testado com PostgreSQL real, incluindo dados sentinela.

**RPO/RTO — valores de referência, não requisitos definidos.** Isto precisa de decisão operacional (com que frequência corre o backup, onde fica guardado, quem o monitoriza):
- RPO proposto: 24h com o agendamento diário por omissão — reduz para o intervalo real escolhido.
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

`docker-compose.prod.yml` usa um Nginx dedicado como único ingresso público. Frontend, backend e PostgreSQL não publicam portas; o proxy encaminha `/` para o frontend e `/api`, `/health` e `/ready` para o backend.

```text
Internet → proxy → frontend
                 → backend → PostgreSQL
```

Para validar localmente por HTTP, usa o overlay que desativa cookies `Secure` apenas nesse ambiente:

```bash
POSTGRES_USER=myvita POSTGRES_PASSWORD='valor-local' POSTGRES_DB=myvita \
JWT_SECRET_KEY='gera-um-valor-com-pelo-menos-32-bytes' PUBLIC_DOMAIN=localhost \
docker compose -f docker-compose.prod.yml -f docker-compose.prod-http.yml up -d --build
```

O proxy fica em `HTTP_PORT` (80 por omissão). Se mudares essa porta para um teste local, define também `LOCAL_ORIGIN` (por exemplo `http://localhost:18081`). `PUBLIC_DOMAIN` define o `server_name`; nenhum destes valores é secreto. O bundle usa `/api` na mesma origem e já não precisa de uma URL pública separada.

Diferenças chave em relação ao dev:
- `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/`JWT_SECRET_KEY`/`PUBLIC_DOMAIN` são **obrigatórios, sem default** — o compose recusa arrancar se faltar algum.
- Postgres não expõe a porta 5432 ao host — só é acessível a partir do container `backend`.
- Sem volumes de código montados — corre exatamente o que está na imagem construída pelo `Dockerfile`.
- `ENVIRONMENT=production`, `DEBUG=false`, `COOKIE_SECURE=true` fixos (a app recusa arrancar com `COOKIE_SECURE=false`, `CORS_ORIGINS` vazio/`*`, ou `JWT_SECRET_KEY` com menos de 32 bytes, quando `ENVIRONMENT=production` — ver `app/core/config.py`).
- O proxy tem IP fixo `172.30.0.10` na rede `edge`; só esse IP entra em `TRUSTED_PROXIES`. O proxy sobrescreve `X-Forwarded-For`, em vez de confiar num valor enviado pelo cliente.
- Backend e frontend correm como utilizadores não-root; a imagem final do frontend contém apenas Nginx e os assets compilados.
- A rede `data` é interna e liga apenas backend/PostgreSQL. A rede `edge` liga proxy/frontend/backend. Só o proxy publica uma porta.

### Ativar HTTPS quando existirem domínio e certificados

O ficheiro `docker-compose.prod-tls.yml.example` e `proxy/nginx.tls.conf.template.example` preparam porta 443, TLS 1.2/1.3, redirecionamento HTTP→HTTPS, HSTS e `X-Forwarded-Proto: https`. Copia o overlay para fora do repositório, substitui o caminho absoluto por um diretório que contenha `fullchain.pem` e `privkey.pem`, e inicia-o juntamente com `docker-compose.prod.yml`. Nunca guardes a chave privada no Git.

No deployment real:

- define `PUBLIC_DOMAIN=app.example.com`;
- mantém `COOKIE_SECURE=true` e `ENVIRONMENT=production`;
- usa `CORS_ORIGINS='["https://app.example.com"]'` se precisares de uma origem explícita (a navegação normal é same-origin);
- publica 80 apenas para redirecionar e 443 para HTTPS;
- obtém/renova certificados fora desta configuração (plataforma, ACME ou secret manager).

## Observability

- **Request ID:** todo o pedido recebe um `X-Request-ID` — reutiliza o do cliente se for bem formado (`[A-Za-z0-9_-]{8,64}`), senão gera um UUID4 novo. Devolvido no header da resposta e presente em todas as linhas de log do pedido (`app/core/request_context.py`).
- **Logging estruturado:** texto legível em `development`; JSON (uma linha por evento) em `staging`/`production`, pronto a ser ingerido por qualquer sistema externo sem parsing especial (`app/core/logging_setup.py`). Nunca inclui passwords, JWTs, cookies, tokens CSRF, headers `Authorization`, ou payloads de pedidos — o logging de pedidos regista apenas `method`, `path`, `status_code`, `duration_ms`, `request_id`.
- **Métricas:** `GET /metrics` (formato texto Prometheus) — contagem de pedidos por método/classe de status, duração, falhas de autenticação, eventos de rate limiting, erros de base de dados. Sem dependência nova, sem labels de alta cardinalidade (nunca `user_id`, `patient_id`, `email`, nome da clínica). **Desativado (404) por omissão** — só responde se `METRICS_TOKEN` estiver configurado, e exige esse valor no header `X-Metrics-Token`.
- `/health` — o processo está vivo; nunca toca na base de dados (uma BD lenta ou em baixo não deve fazer o processo parecer morto).
- `/ready` — confirma a ligação à base de dados com um `SELECT 1`; usa isto nos healthchecks do orquestrador, não como endpoint de alta frequência.

## Estado atual

Implementado:
- Modelos: `User`, `Clinic`, `Patient`, `Staff`, `Appointment`, `AuditLog`, com isolamento multi-tenant via `clinic_id`
- Migrations validadas (upgrade/downgrade reversível, testado com Postgres real, inclusive em CI)
- Auth: Argon2id, cookie httpOnly + JWT (HMAC only, chave mínima 32 bytes), invalidação de sessão via `token_epoch`
- Proteção CSRF: double-submit cookie assinado (HMAC), ligado à sessão
- Rate limiting em login, registo de paciente, onboarding de clínica e criação de staff — pelo IP real do cliente, mesmo atrás de reverse proxy (`TRUSTED_PROXIES`)
- Security headers e CORS explícito (origins/métodos/headers, nunca `*`)
- Audit logging + clinical access logging (tabela `audit_logs`, sessão própria, sem dados sensíveis)
- Request ID por pedido, logging estruturado (JSON em produção/staging), métricas mínimas em `/metrics` (protegido por token, 404 por omissão)
- Tratamento de erros que nunca expõe stack traces/SQL/credenciais ao cliente
- Endpoints: onboarding de clínica, registo de paciente, gestão de staff, marcação de consultas, login/logout/me, diretório de pacientes (`GET /patients`, staff/admin) e de staff (`GET /staff`, qualquer autenticado) — os dois últimos adicionados para o frontend conseguir mostrar nomes em vez de UUIDs e escolher paciente/profissional ao marcar consulta
- Frontend (`frontend/`): React + Vite + TypeScript + Tailwind + React Router + TanStack Query + Zod — ver `frontend/README.md`
- Proteção anti-IDOR: uma clínica nunca consegue marcar consultas usando pacientes/staff de outra clínica (testado e bloqueado)
- CI (GitHub Actions): lint (ruff), type checking (mypy), testes com Postgres real, migrations (upgrade + downgrade + upgrade), coverage, dependency scanning **bloqueante** (pip-audit com exceções documentadas em `SECURITY-EXCEPTIONS.md`), build da imagem Docker
- Dependabot (pip, GitHub Actions, Docker base image)
- Backup/restore automático diário, atómico, com checksum, retenção configurável, volume persistente separado e verificação end-to-end (`scripts/backup_db.sh`, `scripts/restore_db.sh`)
- `docker-compose.prod.yml` separado do dev, sem defaults inseguros, sem exposição desnecessária da BD
- 73 testes automatizados, 95% de cobertura de linhas em `app/`

Por fazer:
- Endpoints para atualizar/cancelar consultas (`PATCH`/`DELETE`) — e, quando existirem, os eventos `APPOINTMENT_UPDATED`/`APPOINTMENT_CANCELLED` já definidos em `AuditAction`
- Endpoints de leitura/detalhe de ficha de paciente — e o evento `STAFF_VIEWED_PATIENT` já definido, à espera de ter onde ligar
- Modelos adiados: `Medication`, `Notification`, `Consent`
- Bloqueio de conta após N tentativas falhadas (hoje mitigado só pelo rate limiting por IP)
- Cópias off-site dos backups locais (P2.2)
- Upgrade major do FastAPI/Starlette (necessário para fechar os últimos CVEs do `starlette` — ver `SECURITY-EXCEPTIONS.md`; deliberadamente não feito nesta fase por ser um upgrade de framework, não hardening)

## Notas para produção que dependem do ambiente de deployment

O que está implementado no código não substitui isto — depende de decisões e infraestrutura fora do repositório:
- Confirmar operacionalmente que o horário e retenção configurados correspondem ao RPO/RTO acordado
- Reverse proxy / TLS em frente ao backend — e configurar `TRUSTED_PROXIES` corretamente para esse proxy
- Gestão real de secrets (GitHub Secrets para CI; um vault/secret manager para produção — nunca um `.env` commitado)
- Valores de RPO/RTO acordados operacionalmente, não os valores de referência acima
- Monitorização/alerting sobre os logs e sobre falhas de `/ready` (a app expõe `/metrics`; ligar isso a um Prometheus/Grafana real, se algum dia fizer sentido, é infraestrutura, não código)
- Armazenamento dos backups fora da máquina da própria base de dados (offsite)
