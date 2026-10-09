# P7 — Servidor do piloto (Hetzner Cloud, host único)

Estado: **ficheiros prontos; execução depende de conta, domínio e decisões humanas.**
Nada aqui prova conformidade — cada passo gera evidência que tem de ser guardada (ver `p7-go-live-checklist.md`).

Ficheiros: `deploy/host/` (cloud-init, encriptação do volume, TLS, wrapper `myvita-compose`).

## Decisões já tomadas neste desenho

- Um único servidor, Ubuntu 24.04, região UE (Falkenstein/Nuremberg — Alemanha).
- Dados de pacientes **só** num Volume encriptado com LUKS (o Hetzner não encripta volumes do lado do fornecedor). Consequência: depois de cada reboot alguém tem de correr `unlock_and_start.sh` e escrever a passphrase. Não há reboot automático.
- HTTPS com Let's Encrypt; renovação automática às 04:17 UTC com ~15–30 s de indisponibilidade a cada ~60 dias.
- Firewall do Hetzner Cloud como perímetro principal (o Docker contorna o `ufw` nas portas publicadas).

## O que só tu (humano) podes fazer

1. **Conta Hetzner Cloud** em nome da empresa (ou dos fundadores até existir empresa). Activar 2FA. Confirmar preços actuais na consola — subiram em 2026.
2. **Domínio** (ex.: `myvita.pt`) e escolher o hostname da app (ex.: `app.myvita.pt`).
3. **Chave SSH** própria (`ssh-keygen -t ed25519`), só a parte pública vai para o cloud-init.
4. **Passphrase LUKS** gerada e guardada num gestor de passwords partilhado pelos dois fundadores.
5. **Bucket de backups off-site** (Hetzner Object Storage noutra localização, ou outro fornecedor S3 na UE) com credenciais limitadas a esse bucket.
6. **Chaves de encriptação dos backups**: cada fundador corre `age-keygen -o myvita-backup-<nome>.key` no seu portátil, guarda o ficheiro no gestor de passwords e põe as chaves públicas (`age-keygen -y …`) em `OFFSITE_AGE_RECIPIENT`. A chave privada nunca vai para o servidor. Sem nenhuma chave privada, os backups off-site são irrecuperáveis.
7. **Destino de alertas** (email ou webhook) e quem responde — ver `alertmanager.yml` (`pending-human-destination`).

## Passos

1. Consola Hetzner → criar **Firewall**: entrada TCP 443 e 80 de qualquer lado; TCP 22 só do teu IP (ou fechado e abrir quando precisas). Tudo o resto negado.
2. Criar **servidor**: Ubuntu 24.04, mínimo 4 vCPU / 8 GB RAM (baseline em `p7-production-host.md`), IPv4+IPv6, a firewall acima, e colar `deploy/host/cloud-init.yaml` (com a tua chave) em *Cloud config*.
3. Criar **Volume** (ex.: 50 GB) ligado ao servidor, **sem** montagem automática.
4. `ssh myvita-ops@<ip>` e:
   ```sh
   sudo cloud-init status --wait
   ls /dev/disk/by-id/            # encontrar scsi-0HC_Volume_<id>
   sudo /opt/myvita/deploy/host/setup_encrypted_storage.sh /dev/disk/by-id/scsi-0HC_Volume_<id>
   ```
   Se o `git clone` do cloud-init falhou (repo privado), clonar com um deploy key só de leitura e voltar a instalar `myvita-compose`.
5. Criar `/srv/myvita-data/config/.env.production` a partir de `.env.production.example` (`chmod 600`). Gerar segredos com `openssl rand -base64 48`.
6. `sudo /opt/myvita/deploy/host/unlock_and_start.sh`
7. DNS: registo A (e AAAA) de `app.<domínio>` → IP do servidor. Esperar que resolva.
8. TLS: `sudo /opt/myvita/deploy/host/tls/issue_certificate.sh app.<domínio> <email> --staging` (teste), depois sem `--staging`. Confirmar `sudo certbot renew --dry-run`.
9. Seguir `p7-deployment-runbook.md` a partir do passo 7: `scripts/production_preflight.sh`, `myvita-compose up -d`, `/health`, `/ready`, `scripts/production_smoke.sh`.
10. **Teste de restauro real** a partir do off-site (`scripts/test_offsite_recovery.sh`) e registar o tempo.
11. Reboot de teste: `sudo reboot` → `unlock_and_start.sh` → confirmar que tudo volta.

## Riscos conhecidos (não resolvidos aqui)

- ~~Backups off-site sem encriptação do lado do cliente~~ — resolvido: cifrados com `age` antes do upload (`docs/p7-backup-and-restore.md#client-side-encryption-age`).
- **Disco raiz não encriptado** (SO e imagens apenas; nenhum dado de paciente deve ir para lá — verificar com `docker info | grep "Docker Root Dir"`).
- **Reboot = indisponibilidade até desbloqueio manual.** Aceitável para um piloto; não para escala.
- `sudo` sem password para `myvita-ops` (acesso só por chave SSH). Rever quando houver mais operadores.
- A configuração Compose deste overlay não foi renderizada com Docker neste ambiente; validar com `myvita-compose config --quiet` no servidor.
