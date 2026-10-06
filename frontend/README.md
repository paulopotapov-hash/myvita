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

## Produção — recomendação (não implementado neste momento)

Este repo não inclui ainda um Dockerfile/pipeline de produção para o frontend, de propósito — evita construir uma segunda pipeline não testada (build multi-stage, config de nginx) antes de a aplicação ter tido um primeiro deployment real. Quando isso for necessário, o caminho recomendado é:

1. `npm run build` → gera `dist/` (estático, sem servidor Node necessário).
2. Servir `dist/` através de um servidor de ficheiros estáticos simples (nginx, Caddy) ou de um serviço de hosting estático (Cloudflare Pages, Netlify, S3+CloudFront, etc.).
3. Configurar esse servidor/CDN para:
   - servir `index.html` para qualquer rota desconhecida (SPA fallback) — necessário porque isto usa React Router em modo `BrowserRouter`;
   - fazer proxy de `/api` para o backend, OU definir `VITE_API_BASE_URL` no build para apontar diretamente para a API (nesse caso, o backend precisa de ter essa origem em `CORS_ORIGINS` — ver `backend/README.md#production`).
4. Servir sempre por HTTPS — o cookie de sessão do backend é `Secure` em produção (`COOKIE_SECURE=true`), por isso só funciona em HTTPS.

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
