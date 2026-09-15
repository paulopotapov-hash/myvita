- `src/assets/myvita-logo-transparent.png` — logótipo oficial.
# MyVita

Website institucional + protótipo funcional demonstrável.

## Estado
- Website: React + Vite.
- Protótipo: `/prototipo`.
- Dados do protótipo: fictícios e mantidos em memória.
- Formulário: validação local + `mailto`; sem backend.
- Domínio previsto: `https://myvita.pt`.

## Desenvolvimento
```bash
npm install
npm run dev
```

## Build
```bash
npm run build
npm run preview
```

## Estrutura
- `src/App.jsx` — website e rotas.
- `src/pages/Prototype.jsx` — protótipo funcional.
- `src/styles.css` — design system/estilos.
- `public/robots.txt` e `public/sitemap.xml` — SEO técnico.

## Próximos passos
1. Validar website e protótipo com utilizadores.
2. Ligar formulário a backend/serviço de email.
3. Criar autenticação e backend do MVP quando houver validação.
4. Definir requisitos de segurança, RGPD, auditoria e infraestrutura antes de dados reais.
