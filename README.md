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
pytest -v
```

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

## Estado atual

Implementado:
- Modelos: `User`, `Clinic`, `Patient`, `Staff`, `Appointment`, com isolamento multi-tenant via `clinic_id`
- Migration inicial validada (upgrade/downgrade reversível, testado com dados reais)
- Auth: Argon2id, cookie httpOnly + JWT, invalidação de sessão via `token_epoch`
- Proteção CSRF: double-submit cookie assinado (HMAC), ligado à sessão — ver secção acima
- Endpoints: onboarding de clínica, registo de paciente, gestão de staff, marcação de consultas, login/logout/me
- Proteção anti-IDOR: uma clínica nunca consegue marcar consultas usando pacientes/staff de outra clínica (testado e bloqueado)
- 37 testes automatizados (integridade de dados, segurança, CSRF, integração HTTP, isolamento entre clínicas)

Por fazer:
- Endpoints para atualizar/cancelar consultas (`PATCH`/`DELETE`)
- Modelos adiados: `Medication`, `Notification`, `Consent`
- Rate limiting nos endpoints de login/registo
- CI (correr `pytest` automaticamente)
