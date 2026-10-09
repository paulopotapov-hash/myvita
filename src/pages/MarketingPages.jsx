import React, { useState } from "react";
import { ArrowRight, Calendar, Check, FileText, MessageCircle, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { SiteLayout } from "../components/SiteChrome.jsx";

const endpoint = "https://formspree.io/f/meaojzoo";

function PageHero({ eyebrow, title, intro, dark = false }) {
  return <section className={`page-hero ${dark ? "page-hero-dark" : ""}`}><div className="container page-hero-inner"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{intro}</p></div></section>;
}

function ContentPage({ eyebrow, title, intro, children, cta = { label: "Explorar o protótipo", to: "/prototipo" }, darkHero = false }) {
  return <SiteLayout><PageHero eyebrow={eyebrow} title={title} intro={intro} dark={darkHero} />{children}<section className="section dark-section page-cta"><div className="container"><h2>Conheça a MyVita em funcionamento.</h2><p>Explore uma demonstração conceptual com dados fictícios e perceba como a experiência pode ser mais simples.</p><Link className="btn btn-gold" to={cta.to}>{cta.label} <ArrowRight size={17} /></Link></div></section></SiteLayout>;
}

function IconGrid({ items }) {
  return <div className="icon-grid">{items.map(({ icon: Icon, title, text }) => <article key={title}><Icon size={22} /><h3>{title}</h3><p>{text}</p></article>)}</div>;
}

export function ProductPage() {
  return <ContentPage eyebrow="Produto" title="Uma relação digital entre paciente e clínica." intro="A MyVita organiza marcações, resultados e mensagens num único espaço, pensado para quem procura cuidados e para quem os presta.">
    <section className="section"><div className="container"><div className="section-head"><span className="eyebrow">Como funciona</span><h2>Três interações essenciais, num só lugar.</h2><p>O produto está em fase de protótipo e validação. A experiência é desenhada para reduzir processos dispersos sem apresentar a MyVita como software clínico de produção.</p></div><IconGrid items={[{ icon: Calendar, title: "Marcações", text: "Pedir, acompanhar e gerir marcações com menos dependência de telefonemas." }, { icon: FileText, title: "Resultados", text: "Publicar e consultar resultados com contexto e notificações no mesmo espaço." }, { icon: MessageCircle, title: "Mensagens", text: "Manter a comunicação entre paciente e clínica organizada e acessível." }]} /></div></section>
    <section className="section soft"><div className="container two-col product-audience"><div><span className="eyebrow">Área do paciente</span><h2>Uma experiência simples e centralizada.</h2><p>O paciente pode consultar as suas marcações, pedir uma nova consulta, acompanhar resultados e falar com a clínica.</p><ul className="check-list"><li><Check size={16} />Consultar marcações</li><li><Check size={16} />Pedir novas marcações</li><li><Check size={16} />Consultar resultados</li><li><Check size={16} />Enviar mensagens</li></ul></div><div><span className="eyebrow">Área da clínica</span><h2>Uma operação mais organizada.</h2><p>A equipa clínica encontra pedidos, pacientes, resultados e mensagens numa experiência conceptual focada no essencial.</p><ul className="check-list"><li><Check size={16} />Gerir pedidos de marcação</li><li><Check size={16} />Acompanhar pacientes</li><li><Check size={16} />Publicar resultados</li><li><Check size={16} />Responder a mensagens</li></ul></div></div></section>
  </ContentPage>;
}

export function ClinicsPage() {
  return <ContentPage eyebrow="Para clínicas" title="Menos chamadas. Mais tempo para a clínica." intro="A MyVita procura tornar mais simples a relação diária com os pacientes, começando pelos processos que mais consomem tempo às equipas.
" cta={{ label: "Quero ser clínica piloto", to: "/clinica-piloto" }}>
    <section className="section"><div className="container"><div className="section-head"><span className="eyebrow">O desafio</span><h2>Processos importantes ainda estão espalhados por vários canais.</h2></div><div className="number-grid">{[["01", "Volume de chamadas", "Pedidos, confirmações e dúvidas ocupam tempo da equipa todos os dias."], ["02", "Gestão manual", "A informação pode ficar distribuída entre telefone, email e diferentes sistemas."], ["03", "Comunicação sem contexto", "Cada contacto exige recuperar o histórico e voltar a explicar o processo."]].map(([number, title, text]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>
    <section className="section soft"><div className="container"><div className="section-head"><span className="eyebrow">Como a MyVita ajuda</span><h2>Um fluxo mais claro entre clínica e paciente.</h2></div><div className="flow-line"><span>Paciente pede</span><b>MyVita organiza</b><span>Clínica responde</span></div><div className="value-list wide-list"><div className="value-item"><b>01</b><div><h3>Menos tarefas repetitivas</h3><p>Centralizar interações frequentes pode ajudar a libertar tempo para a equipa.</p></div></div><div className="value-item"><b>02</b><div><h3>Comunicação mais organizada</h3><p>Pedidos, respostas e histórico ficam pensados numa relação contínua.</p></div></div><div className="value-item"><b>03</b><div><h3>Construção com validação</h3><p>O produto evolui com feedback de clínicas e testes em contexto real.</p></div></div></div></div></section>
    <section className="section"><div className="container split-callout"><div><span className="eyebrow">Participação no piloto</span><h2>Construir com clínicas desde o início.</h2><p>Estamos a selecionar as primeiras clínicas para conhecer processos reais, testar hipóteses e aprender em conjunto.</p></div><Link className="btn btn-primary" to="/clinica-piloto">Quero ser clínica piloto <ArrowRight size={17} /></Link></div></section>
  </ContentPage>;
}

export function PatientsPage() {
  return <ContentPage eyebrow="Para pacientes" title="Tudo o que precisa, num só lugar." intro="Uma experiência digital simples para acompanhar a relação com a clínica, sem depender de telefonemas para cada interação.">
    <section className="section"><div className="container"><div className="section-head"><span className="eyebrow">Experiência do paciente</span><h2>Da marcação à mensagem, com menos fricção.</h2></div><IconGrid items={[{ icon: Calendar, title: "Consultar marcações", text: "Ver consultas confirmadas e acompanhar pedidos no mesmo espaço." }, { icon: Calendar, title: "Pedir marcações", text: "Enviar um pedido à clínica e acompanhar o seu estado." }, { icon: FileText, title: "Consultar resultados", text: "Encontrar resultados disponibilizados pela clínica quando estiverem prontos." }, { icon: MessageCircle, title: "Mensagens", text: "Comunicar diretamente com a clínica, mantendo o histórico acessível." }]} /></div></section>
    <section className="section soft"><div className="container patient-principles"><div><span className="eyebrow">Uma experiência contínua</span><h2>Menos canais. Mais clareza.</h2><p>A proposta da MyVita é reunir as interações frequentes num espaço que o paciente consiga compreender e usar sem complexidade.</p></div><div className="principle-panel"><ShieldCheck size={22} /><strong>Dados fictícios na demonstração</strong><p>O protótipo atual é conceptual e não utiliza dados reais de saúde.</p></div></div></section>
  </ContentPage>;
}

export function VisionPage() {
  return <ContentPage eyebrow="Visão" title="Uma relação digital contínua em saúde." intro="A MyVita ambiciona tornar mais simples, próxima e organizada a relação entre pacientes e prestadores de saúde em Portugal." darkHero>
    <section className="section"><div className="container"><div className="section-head"><span className="eyebrow">O caminho</span><h2>Uma visão de longo prazo, construída com responsabilidade.</h2><p>A visão futura não deve ser confundida com o que existe hoje. O produto atual é um protótipo funcional em fase de validação.</p></div><div className="vision-list vision-list-light"><div><span>Hoje</span><div><h3>Validar interações essenciais</h3><p>Marcações, resultados e mensagens são a base conceptual do protótipo atual.</p></div></div><div><span>Depois</span><div><h3>Aprender com clínicas e pacientes</h3><p>O feedback deve orientar o âmbito, as prioridades e a evolução responsável do produto.</p></div></div><div><span>Futuro</span><div><h3>Uma relação digital contínua</h3><p>A ambição é criar uma infraestrutura de confiança para a relação em saúde em Portugal.</p></div></div></div></div></section>
  </ContentPage>;
}

export function CurrentStatePage() {
  return <ContentPage eyebrow="Estado atual" title="Ambição na visão. Rigor nos factos." intro="A MyVita está numa fase inicial de validação. O que existe é um protótipo funcional; o produto de produção ainda está por construir." cta={{ label: "Ver demonstração", to: "/prototipo" }}>
    <section className="section"><div className="container"><div className="status-grid status-page-grid"><article className="status-panel"><span className="eyebrow">Já existe</span><h3>Protótipo funcional</h3><ul><li><Check size={15} />Experiência de paciente</li><li><Check size={15} />Experiência de clínica</li><li><Check size={15} />Demonstração em React</li></ul></article><article className="status-panel"><span className="eyebrow">Em construção</span><h3>Base para validação</h3><ul><li><Check size={15} />MVP e infraestrutura</li><li><Check size={15} />Backend e segurança</li><li><Check size={15} />Preparação dos primeiros pilotos</li></ul></article><article className="status-panel"><span className="eyebrow">Falta validar</span><h3>Utilidade em contexto real</h3><ul><li><Check size={15} />Processos prioritários das clínicas</li><li><Check size={15} />Adoção por equipas e pacientes</li><li><Check size={15} />Âmbito e métricas do piloto</li></ul></article></div><p className="product-note state-note"><i /> A demonstração usa exclusivamente dados fictícios e não representa uma plataforma já implementada em clínicas.</p></div></section>
  </ContentPage>;
}

const faqs = [["Para que tipo de clínicas é a MyVita?", "Nesta fase, procuramos conhecer diferentes operações clínicas para perceber onde o conceito pode criar mais valor."], ["A MyVita substitui o software clínico?", "Não. A proposta atual é organizar a relação e a comunicação com pacientes, sem apresentar a MyVita como substituto do software clínico."], ["A MyVita já está disponível?", "Existe atualmente um protótipo funcional. Estamos a preparar o MVP e a fase de validação com clínicas."], ["Como funciona um piloto?", "É uma proposta futura: conhecemos o processo atual, definimos um âmbito inicial e aprendemos com o feedback da equipa e dos pacientes."], ["Os dados apresentados no protótipo são reais?", "Não. A demonstração usa exclusivamente dados fictícios e estado mantido em memória."]];

export function FaqPage() {
  return <ContentPage eyebrow="Perguntas frequentes" title="Clareza antes do próximo passo." intro="As respostas essenciais sobre o produto, a demonstração e o momento atual da MyVita." cta={{ label: "Falar sobre um piloto", to: "/clinica-piloto" }}><section className="section"><div className="container faq-page-list">{faqs.map(([question, answer]) => <details key={question}><summary>{question}<ArrowRight size={17} /></summary><p>{answer}</p></details>)}</div></section></ContentPage>;
}

export function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", message: "" });
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submit = async event => {
    event.preventDefault();
    setSent(false);
    setError("");
    if (!form.name.trim() || !form.message.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      setError("Preencha o nome, um email válido e a mensagem.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch(endpoint, { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify({ ...form, _subject: "MyVita — Contacto" }) });
      if (!response.ok) throw new Error();
      setSent(true);
      setForm({ name: "", email: "", message: "" });
    } catch {
      setError("Não foi possível enviar a mensagem. Tente novamente ou contacte PRTLABS.OFFICIAL@GMAIL.COM.");
    } finally {
      setSubmitting(false);
    }
  };
  return <SiteLayout><PageHero eyebrow="Falar connosco" title="Vamos validar a próxima fase juntos." intro="Se representa uma clínica, um parceiro ou um investidor, estamos disponíveis para apresentar o protótipo e ouvir os desafios da sua operação." /><section className="section"><div className="container contact-grid"><div><div className="contact-details"><p><strong>Email</strong><a href="mailto:PRTLABS.OFFICIAL@GMAIL.COM">PRTLABS.OFFICIAL@GMAIL.COM</a></p><p><strong>Sede</strong>Coimbra, Portugal</p><p><strong>Fase</strong>Protótipo funcional · Em validação</p></div></div><form className="contact-form" onSubmit={submit} noValidate><label>Nome<input name="name" required value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} /></label><label>Email profissional<input name="email" required type="email" value={form.email} onChange={event => setForm({ ...form, email: event.target.value })} /></label><label>Mensagem<textarea name="message" required rows="6" value={form.message} onChange={event => setForm({ ...form, message: event.target.value })} /></label><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? "A enviar..." : "Enviar mensagem"} {!submitting && <ArrowRight size={16} />}</button>{sent && <p className="form-note success" role="status">Obrigado. Recebemos a sua mensagem.</p>}{error && <p className="form-note error" role="alert">{error}</p>}</form></div></section></SiteLayout>;
}
