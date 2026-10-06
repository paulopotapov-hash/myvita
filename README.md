- `src/assets/myvita-logo-transparent.png` — logótipo oficial.
# MyVita

Protótipo frontend de uma plataforma digital de saúde que pretende conectar pacientes e clínicas através de uma experiência simples para marcações, resultados e mensagens.

## Overview

A MyVita explora uma forma mais organizada de gerir a relação entre pacientes e clínicas. O projeto inclui páginas institucionais e uma demonstração funcional das áreas do paciente e da clínica.

## Features

- Páginas institucionais para produto, clínicas, pacientes e visão.
- Protótipo navegável das áreas do paciente e da clínica.
- Fluxos conceptuais para marcações, resultados e mensagens.
- Formulários de contacto e candidatura a clínica piloto com validação básica.
- Envio dos formulários através do Formspree.

## Tech Stack

- React
- Vite
- JavaScript
- React Router
- CSS
- Lucide React
- Formspree
- Vercel

## Live Demo

[https://my-vita-rho.vercel.app/](https://my-vita-rho.vercel.app/)

## Getting Started

```bash
git clone <repository-url>
cd MyVita-
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Project Structure

```text
src/
├── App.jsx
├── main.jsx
├── components/
│   └── SiteChrome.jsx
├── pages/
│   ├── MarketingPages.jsx
│   ├── PilotClinic.jsx
│   └── Prototype.jsx
├── assets/
└── styles.css
public/
├── robots.txt
└── sitemap.xml
```

## Important Note

This project is a frontend prototype using fictional data. It does not store or process real patient information.

## Deployment

The project is deployed on Vercel. The `vercel.json` rewrite keeps direct access to React Router routes working as a single-page application.
