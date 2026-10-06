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

Testes cobrem: cliente API (CSRF, credentials, parsing de erros), rotas protegidas, restrição por role, login (incluindo segundo fator), navegação por role, schemas de validação, mapeamento de erros do backend para campos de formulário e os fluxos clínicos (consultas, registos clínicos, medicação, consentimentos, notificações) e de conta (palavra-passe, contas da clínica).

## Estado funcional

Legenda: **Implementado** · **Parcial** · **Não implementado**. Reflete o código em `src/`; o backend continua a ser a fonte de verdade de RBAC e isolamento por clínica.

### Autenticação e conta

| Área | Estado | Notas |
| --- | --- | --- |
| Login/logout, sessão por cookie httpOnly, restauro de sessão, redirecionamento após login, tratamento de 401 | Implementado | `/login`, `ProtectedRoute`, `SessionExpiryBoundary` |
| MFA (TOTP) | Implementado | Segundo passo no login (código ou código de recuperação); ativação com códigos de recuperação em `/app/seguranca` e no ecrã de configuração obrigatória |
| Alteração de palavra-passe (voluntária e obrigatória) | Implementado | `/app/seguranca`; ecrã bloqueante quando a conta o exige |
| Recuperação de acesso | Parcial | O pedido regista-se para a clínica e a ligação de redefinição é emitida pelo administrador em `/app/contas`; **não há envio automático por email** |
| Registo de paciente, onboarding de clínica, aceitação de convite | Implementado | Disponibilidade controlada pela configuração pública do backend |

### Papéis e permissões (UX; o backend aplica as regras)

| Papel | Pode |
| --- | --- |
| Paciente | Apenas os seus dados: consultas, dados clínicos (leitura), consentimentos (conceder/revogar), notificações, perfil, segurança |
| Médico/Enfermeiro (`staff`) | Pacientes, consultas (incluindo motivo), registos clínicos e medicação (escrita), consentimentos (leitura) |
| Administrativo (`staff` `admin`) | Pacientes (lista) e consultas sem motivo clínico; sem conteúdo clínico nem consentimentos |
| Administrador da clínica | Equipa (convites), contas (recuperação/desativação), pacientes (lista), consultas sem motivo; sem conteúdo clínico nem consentimentos |

### Fluxos clínicos

| Área | Estado | Notas |
| --- | --- | --- |
| Consultas | Parcial | Listar, detalhe, criar, alterar **duração e motivo** e cancelar (com confirmação). Alterar data/hora, paciente, profissional ou estado (confirmada, concluída, falta) existe no backend mas **não tem UI** |
| Registos clínicos | Parcial | Listar, criar, editar (nova versão) e listar revisões (versão e data). **Não** mostra o conteúdo de revisões antigas |
| Medicação | Parcial | Criar (nome, dosagem, via, frequência, instruções, datas), ver, editar, concluir e descontinuar (com confirmação). Mostra até 100 registos e avisa quando há mais; sem filtro por estado nem data de fim ao terminar (o backend assume hoje) |
| Consentimentos | Implementado | Paciente concede/revoga (o histórico é preservado); médicos e enfermeiros consultam |
| Notificações | Parcial | Lista paginada e marcar como lida. **O backend não gera notificações automaticamente**, por isso a lista só tem conteúdo se este for criado fora da aplicação |
| Equipa e contas (administrador) | Implementado | Convites, repor 2FA, ligação de redefinição, exigir nova palavra-passe, desativar/reativar |

### Formulários e feedback

- Validação cliente com Zod em `src/lib/validation.ts` (espelha limites do backend; o backend revalida). Erros aparecem junto ao campo; erros 422 do backend são mapeados para o campo (`formErrorsFrom`) ou mostrados como mensagem geral.
- Pedidos de escrita bloqueiam o botão enquanto decorrem (sem duplo envio) e mostram sucesso (`role="status"`) ou erro (`role="alert"`) com `FormMessage`. Ações destrutivas pedem confirmação.
- Componentes partilhados: `Button`, `TextField`, `TextAreaField`, `SelectField`, `FormMessage`, `LoadingSpinner`, `ErrorState`, `EmptyState`.

## Limitações conhecidas (por falta de endpoint ou decisão de produto)

- Notificações automáticas (ver acima): depende de uma decisão de produto e provavelmente de alteração ao modelo no backend.
- Recuperação de acesso sem entrega por email: sem canal de entrega aprovado.
- Não existe endpoint de perfil do utilizador autenticado com dados clínicos; o paciente vê os seus dados em «Dados clínicos».
