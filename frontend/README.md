# myVita — Frontend

React + Vite + TypeScript + Tailwind CSS v4 + React Router + TanStack Query + Zod.

## Correr localmente

```bash
cd frontend
npm install
npm run dev
```

Abre `http://localhost:5173`. O servidor de dev do Vite faz proxy de `/api` para `http://localhost:8000` (o backend a correr localmente) — ver `vite.config.ts`. Isto evita CORS em dev: o browser só fala com `localhost:5173`.

Com Docker Compose (`docker compose up` na raiz do repo), o proxy aponta para o serviço `backend` em vez de `localhost` — ver `VITE_PROXY_TARGET` no `docker-compose.yml`.

## Variáveis de ambiente

Ver `.env.example`. Só existe uma: `VITE_API_BASE_URL`, e só é preciso defini-la se a API viver numa origem/subdomínio diferente do frontend em produção. **Nunca colocar secrets aqui** — tudo o que está num `.env` do Vite fica visível no JS entregue ao browser.

## Segurança — decisões importantes

- **Sem localStorage/sessionStorage para sessão.** A sessão vive inteiramente no cookie httpOnly `myvita_session`, que o JavaScript nunca consegue ler — é assim que o backend já funciona, o frontend não inventa um segundo mecanismo.
- **CSRF:** todo o pedido `POST/PUT/PATCH/DELETE` lê o cookie `myvita_csrf` (não-httpOnly, de propósito) e envia-o no header `X-CSRF-Token` — ver `src/lib/apiClient.ts`. Implementado exatamente como o backend espera, nada inventado.
- **`credentials: 'include'`** em todos os pedidos — sem isto os cookies nunca seriam enviados.
- **Proteção de rotas é UX, não autorização.** `ProtectedRoute`/`RoleRoute` evitam mostrar UI errada a quem não devia vê-la, mas o backend é sempre a fonte de verdade — todas as chamadas continuam sujeitas ao RBAC/multi-tenancy do backend, nenhuma proteção do frontend substitui isso.
- **Erros nunca expõem internals.** `src/lib/errorMessages.ts` só mostra o `detail` que o próprio backend já garante ser seguro (ver `backend/app/main.py`); nunca stack traces, SQL, ou o corpo bruto da resposta.

## Imagem de produção

O `Dockerfile` multi-stage executa `npm ci` e `npm run build`, depois copia apenas o `dist/` para um Nginx não-root. O Nginx serve ficheiros estáticos em `8080` e faz fallback para `index.html`, portanto URLs do React Router podem ser abertas diretamente.

Na stack de produção, o reverse proxy P1.2 serve frontend e `/api` na mesma origem. Por isso o build usa `VITE_API_BASE_URL` vazio e o browser envia cookies/CSRF para caminhos relativos, sem CORS entre frontend e API. A variável continua disponível para deployments independentes do frontend:

```bash
docker build --build-arg VITE_API_BASE_URL=https://api.example.pt -t myvita-frontend ./frontend
docker run --rm -p 8080:8080 myvita-frontend
curl http://localhost:8080/healthz
```

Para iniciar a stack HTTP local de validação, define os secrets backend e usa o overlay próprio:

```bash
PUBLIC_DOMAIN=localhost \
docker compose -f docker-compose.prod.yml -f docker-compose.prod-http.yml up -d --build
```

Abre `http://localhost` apenas para uma verificação local. Um deployment real deve usar o overlay TLS documentado no README principal, porque o cookie de sessão backend permanece `Secure`. Variáveis `VITE_*` são públicas e nunca podem conter secrets.

## Testes

```bash
npm run test          # vitest run
npm run test:coverage # com cobertura
npm run typecheck     # tsc -b --noEmit
npm run lint          # oxlint
```

Testes cobrem: cliente API (CSRF, credentials, parsing de erros), rotas protegidas (loading/não-autenticado/erro-de-servidor/autenticado), restrição por role, fluxo de login completo, navegação por role no layout autenticado.

## Limitações conhecidas (por falta de endpoint no backend, não por bug)

- **Perfil do paciente** não mostra data de nascimento/telefone depois do registo inicial — não existe um `GET /patients/me`, só a resposta do próprio registo. Documentado na própria página em vez de inventar dados.
- **Consultas** não podem ser atualizadas/canceladas pela UI — o backend só suporta criar e listar (`POST`/`GET /api/v1/appointments`), sem `PATCH`/`DELETE`.
