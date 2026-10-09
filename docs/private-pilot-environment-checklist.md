# Checklist do ambiente privado de piloto

Tudo o que requer fornecedor, valor real ou responsável humano está marcado **CONFIGURAÇÃO EXTERNA NECESSÁRIA**. Não inserir segredos neste ficheiro ou no Git.

## Entrada e rede

- [ ] Domínio e DNS aprovados — **CONFIGURAÇÃO EXTERNA NECESSÁRIA**.
- [ ] Certificado válido, cadeia, chave fora do Git e renovação testada — **CONFIGURAÇÃO EXTERNA NECESSÁRIA**.
- [ ] 443 público; 80 apenas para redirect; BD/backend/monitorização sem portas públicas.
- [ ] Overlay TLS validado: TLS 1.2/1.3, HTTP→HTTPS, HSTS e `X-Forwarded-Proto=https`.
- [ ] `PUBLIC_DOMAIN`, `ALLOWED_HOSTS` e CORS HTTPS exatos; sem wildcards.
- [ ] `TRUSTED_PROXIES` corresponde apenas ao proxy; forwarded headers e IP de cliente testados.
- [ ] Cookies Secure/HttpOnly/SameSite e CSRF/origin testados no browser real.
- [ ] Firewall, acesso administrativo e host/storage cifrados — **CONFIGURAÇÃO EXTERNA NECESSÁRIA**.

## Segredos e dados

- [ ] Gestor de segredos, custodiantes e rotação — **CONFIGURAÇÃO EXTERNA NECESSÁRIA**.
- [ ] Credenciais dedicadas e não privilegiadas para PostgreSQL; `JWT_SECRET_KEY`, métricas e Grafana gerados fora do Git.
- [ ] `.env.production.example` usado apenas como esquema; `production_preflight.sh` passa sem imprimir valores.
- [ ] Volume PostgreSQL persistente e cifrado — **CONFIGURAÇÃO EXTERNA NECESSÁRIA**.
- [ ] Backup local atómico/checksum e off-site cifrado/imutável — fornecedor e credenciais são **CONFIGURAÇÃO EXTERNA NECESSÁRIA**.
- [ ] Restore isolado, cronometrado e verificado com dados sentinela; RPO/RTO aprovados — **DECISÃO NECESSÁRIA**.

## Release e containers

- [ ] Release revista, identificável e imutável; imagens construídas do commit aprovado.
- [ ] `docker-compose.prod.yml` e overlay TLS renderizam; sem mounts de código ou BD publicada.
- [ ] Backup válido antes da migração. O job `migrate` executa `alembic upgrade head`; backend/backup esperam conclusão e backend health antes de frontend/proxy.
- [ ] Migração validada numa cópia/restauro isolado; plano de rollback por imagem + restauração/migração compatível aprovado.
- [ ] `/health`, `/ready` e `/healthz` passam pelo caminho interno e externo; smoke test HTTPS passa.

## Operação

- [ ] Prometheus/Grafana/exporters/probes implantados; retenção e acesso aprovados.
- [ ] Alertmanager tem destinatário humano real e teste de entrega/resolução — **CONFIGURAÇÃO EXTERNA NECESSÁRIA**.
- [ ] Logs, request IDs e audit logs acessíveis apenas a responsáveis; ausência de payload clínico/segredos verificada.
- [ ] Donos de infraestrutura, base de dados, segurança, backup, incidentes, privacidade e suporte nomeados — **DECISÃO NECESSÁRIA**.
- [ ] Exercício de falha de backend, BD, autenticação, backup e incidente concluído.

## Evidência ainda impossível apenas no repositório

O template TLS contém redirect, HSTS e cabeçalhos forwarded, e produção força cookies seguros e hosts/CORS explícitos. Isso não prova certificado, renovação, firewall, cifragem, secret manager, off-site restore ou entrega humana. Esses testes têm de ser repetidos no ambiente real antes do go/no-go.
