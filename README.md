# myVita — Backend

## Correr localmente (Docker)

```bash
cp backend/.env.example backend/.env
# edita backend/.env e define um JWT_SECRET_KEY real
docker compose up --build
```

- API: http://localhost:8000
- Docs (Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/health · Ready: http://localhost:8000/ready

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

## Estado atual

Implementado:
- Modelos: `User`, `Clinic`, `Patient`, `Staff`, `Appointment`, com isolamento multi-tenant via `clinic_id`
- Migration inicial validada (upgrade/downgrade reversível, testado com dados reais)
- Auth: Argon2id, cookie httpOnly + JWT, invalidação de sessão via `token_epoch`
- Endpoints: onboarding de clínica, registo de paciente, login/logout/me
- 16 testes automatizados (integridade de dados, segurança, integração HTTP)

Por fazer:
- Endpoints de consultas (`appointments`) — CRUD com scoping por clínica
- Gestão de staff pela clínica (convite/criação de médicos)
- Modelos adiados: `Medication`, `Notification`, `Consent`
- Rate limiting nos endpoints de login/registo
- CI (correr `pytest` automaticamente)
