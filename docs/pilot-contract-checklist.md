# Contrato técnico do piloto controlado

Este documento é uma estrutura de decisão. Não autoriza o uso de dados reais e não substitui aprovação clínica, jurídica, de privacidade ou contratual.

## Identificação e objetivo

- Clínica participante: **DECISÃO NECESSÁRIA** — a organização responsável deve identificar e aprovar a clínica.
- Objetivo mensurável do piloto: **DECISÃO NECESSÁRIA** — produto e clínica devem definir as tarefas a validar.
- Duração e datas: **DECISÃO NECESSÁRIA**.
- Número e perfil de utilizadores/pacientes: **DECISÃO NECESSÁRIA**.

## Âmbito técnico proposto

Incluído, sujeito aos gates deste documento: autenticação e logout; administrador de clínica; convites; profissionais doctor/nurse/admin; diretório e detalhe do paciente; consultas e estados `scheduled`, `confirmed`, `completed`, `cancelled`, `no_show`; registos clínicos versionados; registos de medicação; consentimentos e revogação; auditoria; health/readiness; backups e monitorização.

Explicitamente fora do âmbito: prescrição eletrónica; faturação; telemedicina; ficheiros/anexos; integrações laboratoriais/dispositivos; importação/exportação em massa; MFA e recuperação self-service; consentimento por representante; qualquer fluxo não incluído na matriz de acesso aprovada.

Alterar qualquer item incluído ou excluído exige **DECISÃO NECESSÁRIA** do responsável de produto e da clínica e nova avaliação técnica.

## Utilizadores e papéis

Os únicos papéis existentes são patient, clinic_admin e staff; staff tem doctor, nurse ou admin. A interpretação clínica e a atribuição nominal de cada papel são **DECISÃO CLÍNICA NECESSÁRIA**. A matriz técnica atual está em `pilot-access-matrix.md`.

## Dados e ambiente

- Uso inicial de dados sintéticos versus dados reais: **DECISÃO NECESSÁRIA** do responsável pelo tratamento/privacidade e da clínica.
- Categorias, minimização e origem dos dados: **DECISÃO NECESSÁRIA**.
- Finalidades, fundamentos, informação apresentada e textos/versionamento de consentimento: **DECISÃO NECESSÁRIA** com validação jurídica apropriada.
- Retenção, eliminação, restrição, acesso e portabilidade: **DECISÃO NECESSÁRIA**; a aplicação não implementa hoje um workflow completo destas solicitações.
- Ambiente: privado, HTTPS, acesso restrito e configuração conforme `private-pilot-environment-checklist.md`. Valores reais são **CONFIGURAÇÃO EXTERNA NECESSÁRIA**.

## Responsabilidades

Responsável técnico, substituto, segurança, backup, incidentes, privacidade, suporte e contactos: **DECISÃO NECESSÁRIA**. A clínica deve nomear administrador, profissionais autorizados, contacto clínico, responsável por validar acessos e canal de suporte. A equipa técnica deve operar deploy, migrações, monitorização, backup/restore, gestão de segredos e resposta técnica a incidentes. A repartição contratual final é **DECISÃO NECESSÁRIA**.

## Suporte e incidente

Horário, severidades, SLA, canal autorizado e escalação são **DECISÃO NECESSÁRIA**. O procedimento base está em `pilot-incident-response.md`. Critérios mínimos: preservar request IDs/auditoria sem copiar conteúdo clínico para tickets; conter acessos; nomear incident lead; avaliar integridade e impacto; recuperar apenas de backup validado; registar decisão de retorno ao serviço.

## Sucesso, interrupção e saída

Critérios de sucesso: **DECISÃO NECESSÁRIA**. Devem ser mensuráveis e incluir conclusão das tarefas críticas, ausência de acesso cross-tenant, integridade de agenda/notas, disponibilidade, suporte e feedback clínico.

Interrupção imediata mínima: suspeita de acesso indevido; perda/corrupção de dados; falha de isolamento; ausência de backup recuperável; TLS/segredo comprometido; auditoria crítica indisponível sem processo alternativo aprovado. Outros limiares são **DECISÃO NECESSÁRIA**.

Go/no-go exige todos os gates P0 da checklist do ambiente, matriz de acesso aprovada, restore e alertas demonstrados, testes E2E por papel/tenant e aceitação clínica/privacidade. Exceções e quem as pode aceitar são **DECISÃO NECESSÁRIA**.

Na saída: suspender novas entradas; exportar/devolver/reter/eliminar conforme decisão aprovada; revogar contas/segredos; preservar evidência e auditoria aplicáveis; confirmar destino de backups; produzir relatório e decisão sobre continuação. O tratamento concreto é **DECISÃO NECESSÁRIA**.
