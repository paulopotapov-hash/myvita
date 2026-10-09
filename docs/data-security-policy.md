# Política técnica de dados e segurança do piloto

## Controlos verificados no código

Sessão em cookie HttpOnly, Argon2, CSRF double-submit/origin, rate limiting, TrustedHost, CORS explícito, token epoch, RBAC e tenant derivado da sessão estão implementados. Recursos cross-tenant são filtrados/ocultados no backend; visibilidade frontend não é controlo de segurança. Configuração de produção recusa cookies inseguros, hosts/origens wildcard, hosts locais, segredo fraco e criação direta de staff.

## Consentimentos

Cada concessão preserva clínica, paciente, tipo, finalidade, timestamps, ator, estado e eventual revogação. A API suporta agora um snapshot opcional e inseparável de `policy_version` + `policy_text`; concessões antigas continuam legíveis. Tornar o snapshot obrigatório depende de existir conteúdo aprovado e de uma estratégia de migração.

**DECISÃO NECESSÁRIA:** texto, versão oficial, finalidade, base aplicável, informação apresentada, idiomas, efeitos da revogação e tratamento de consentimentos anteriores. Responsáveis: clínica, privacidade/jurídico e produto. Impacto técnico: catálogo de políticas aprovado, UI sem texto livre e validação obrigatória da versão publicada.

## Auditoria

O código audita login/logout e falhas relevantes, mudanças de password, visualização/alteração de pacientes, consultas, registos clínicos, medicamentos, consentimentos, convites e desativação. O writer usa transação independente para preservar recusas e falhas mesmo quando a transação principal reverte.

Persistência da auditoria hoje é best-effort: uma falha é escrita no log da aplicação e não cancela a operação. **DECISÃO NECESSÁRIA:** classificar operações que devem falhar fechadas, ou definir alerta/contingência equivalente. Responsáveis: segurança, clínica e privacidade. Impacto técnico: política por ação, monitorização de falhas e eventual transactional outbox/serviço durável. Não se deve converter automaticamente todo log técnico em evento clínico.

## Ciclo de vida e conta

Há desativação de contas e revogação de sessões; não há workflow completo de acesso/exportação, portabilidade, retenção, restrição, eliminação/anonimização ou recuperação self-service. **DECISÃO NECESSÁRIA:** regras, responsáveis, prazos, exceções clínicas, efeito em auditoria e backups e processo de verificação de identidade. Só depois se deve implementar automação.

## Estado técnico residual

- A agenda usa lock transacional PostgreSQL por clínica antes de verificar/escrever conflitos.
- Registos clínicos exigem `expected_version` e devolvem 409 perante edição obsoleta.
- Pesquisa de pacientes é paginada, limitada a nome e sempre filtrada pela clínica autenticada.
- Transições permitidas: scheduled→confirmed; confirmed→completed/no_show; scheduled/confirmed→cancelled pelo endpoint de cancelamento. Alterações a esta máquina exigem **DECISÃO CLÍNICA NECESSÁRIA**.
