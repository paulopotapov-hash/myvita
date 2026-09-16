import React, { useState } from "react";
import { ArrowRight, Calendar, Check, FileText, MessageCircle, ShieldCheck } from "lucide-react";
import { SiteFooter, SiteNavbar } from "../components/SiteChrome.jsx";

const FORMSPREE_ENDPOINT = "https://formspree.io/f/meaojzoo";

const initialForm = {
  name: "",
  clinic: "",
  role: "",
  email: "",
  phone: "",
  specialties: "",
  patientsPerMonth: "",
  appointments: "",
  communication: "",
  improvement: "",
  notes: "",
  consent: false,
};

const requiredMessages = {
  name: "Indique o seu nome.",
  clinic: "Indique o nome da clínica.",
  role: "Indique o seu cargo ou função.",
  email: "Indique um email profissional válido.",
  phone: "Indique um telefone.",
  specialties: "Indique as especialidades da clínica.",
  patientsPerMonth: "Selecione uma estimativa.",
  appointments: "Explique como fazem atualmente as marcações.",
  communication: "Explique como comunicam atualmente com os pacientes.",
  improvement: "Indique o que gostariam de melhorar.",
  consent: "É necessário aceitar esta autorização para enviar a candidatura.",
};

function Field({ label, name, value, onChange, error, required = false, type = "text", children, rows = 0 }) {
  return <label className="pilot-field">
    <span>{label}{required && <b aria-hidden="true"> *</b>}</span>
    {children || (rows ? <textarea name={name} rows={rows} value={value} onChange={onChange} aria-invalid={!!error} required={required} /> : <input name={name} type={type} value={value} onChange={onChange} aria-invalid={!!error} required={required} />)}
    {error && <small>{error}</small>}
  </label>;
}

function ValidationCard({ icon: Icon, title, text }) {
  return <article className="pilot-validation-card"><Icon size={21} /><span>{title}</span><p>{text}</p></article>;
}

export default function PilotClinic() {
  const [form, setForm] = useState(initialForm);
  const [errors, setErrors] = useState({});
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const update = event => {
    const { name, type, checked, value } = event.target;
    setForm(current => ({ ...current, [name]: type === "checkbox" ? checked : value }));
    if (errors[name]) setErrors(current => ({ ...current, [name]: "" }));
  };

  const goToForm = event => {
    event.preventDefault();
    document.getElementById("candidatura")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const submit = async event => {
    event.preventDefault();
    setSent(false);
    setFormError("");
    const nextErrors = {};
    Object.entries(requiredMessages).forEach(([name, message]) => {
      if (name === "consent" ? !form.consent : !form[name].trim()) nextErrors[name] = message;
    });
    if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) nextErrors.email = "Indique um email profissional válido.";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    setSubmitting(true);
    try {
      const response = await fetch(FORMSPREE_ENDPOINT, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, consent: "Aceito ser contactado relativamente à MyVita.", _subject: "MyVita — Candidatura de clínica piloto" }),
      });
      if (!response.ok) throw new Error("Formspree rejected the submission");
      setForm(initialForm);
      setErrors({});
      setSent(true);
    } catch {
      setFormError("Não foi possível enviar a candidatura. Tente novamente ou contacte PRTLABS.OFFICIAL@GMAIL.COM.");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="pilot-page">
    <SiteNavbar />
    <main>
      <section className="pilot-hero"><div className="container pilot-hero-inner"><div className="pilot-hero-copy"><span className="eyebrow">Programa de validação</span><h1>Faça parte das primeiras clínicas a testar a MyVita.</h1><p>Estamos a selecionar clínicas para uma fase inicial de validação da plataforma. O objetivo é perceber como a MyVita pode simplificar a comunicação com os pacientes e reduzir processos dependentes do telefone.</p><span className="pilot-status">Fase de validação inicial <i /> Portugal</span></div></div></section>

      <section className="section pilot-validation"><div className="container"><div className="section-head"><span className="eyebrow">O que estamos a validar</span><h2>Começar pelos momentos que mais impactam a relação.</h2></div><div className="pilot-validation-grid"><ValidationCard icon={Calendar} title="MARCAÇÕES" text="Receber e gerir pedidos de marcação de forma digital." /><ValidationCard icon={FileText} title="RESULTADOS" text="Disponibilizar resultados ao paciente através de uma experiência centralizada." /><ValidationCard icon={MessageCircle} title="MENSAGENS" text="Criar um canal digital direto entre clínica e paciente." /><ValidationCard icon={ShieldCheck} title="EXPERIÊNCIA" text="Perceber onde a comunicação atual gera mais fricção e como pode ser simplificada." /></div></div></section>

      <section className="section soft"><div className="container pilot-looking"><div className="pilot-looking-copy"><span className="eyebrow">O que procuramos</span><h2>Procuramos clínicas interessadas em construir connosco.</h2><p>Estamos numa fase inicial e queremos trabalhar diretamente com clínicas para compreender os seus processos, recolher feedback e validar a solução em contexto real.</p></div><ul className="pilot-profile-list">{["Clínicas privadas", "Consultórios e grupos de saúde", "Diferentes especialidades", "Equipas abertas à inovação digital", "Clínicas interessadas em melhorar a comunicação com pacientes"].map(item => <li key={item}><Check size={16} />{item}</li>)}</ul></div></section>

      <section className="section"><div className="container"><div className="section-head"><span className="eyebrow">Como funciona</span><h2>Uma conversa antes de qualquer compromisso.</h2><p>O envio do formulário não garante participação num piloto. Serve para conhecermos melhor o seu contexto e percebermos se existe alinhamento.</p></div><div className="pilot-process-grid">{[["01", "Candidatura", "Partilhe algumas informações sobre a sua clínica e o atual processo de comunicação com pacientes."], ["02", "Conversa", "Falamos consigo para perceber os principais desafios e apresentar a MyVita."], ["03", "Validação", "Se existir alinhamento, exploramos a possibilidade de participação numa fase piloto."]].map(([number, title, text]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>

      <section className="pilot-form-wrap" id="candidatura"><div className="container pilot-form-layout"><div className="pilot-form-aside"><span className="eyebrow">Candidatura</span><h2>Conte-nos como trabalha hoje.</h2><p>As suas respostas ajudam-nos a perceber onde a MyVita pode criar valor real para a sua equipa e para os seus pacientes.</p><p className="required-note"><b>*</b> Campos obrigatórios</p></div><form className="pilot-form" onSubmit={submit} noValidate>
        <div className="pilot-form-section"><div className="pilot-section-title"><span>01</span><h2>Sobre si e a clínica</h2></div><div className="pilot-fields two"><Field label="Nome" name="name" value={form.name} onChange={update} error={errors.name} required /><Field label="Clínica" name="clinic" value={form.clinic} onChange={update} error={errors.clinic} required /><Field label="Cargo / Função" name="role" value={form.role} onChange={update} error={errors.role} required /><Field label="Email profissional" name="email" value={form.email} onChange={update} error={errors.email} required type="email" /><Field label="Telefone" name="phone" value={form.phone} onChange={update} error={errors.phone} required type="tel" /><Field label="Especialidades da clínica" name="specialties" value={form.specialties} onChange={update} error={errors.specialties} required /></div></div>
        <div className="pilot-form-section"><div className="pilot-section-title"><span>02</span><h2>Processos atuais</h2></div><div className="pilot-fields"><Field label="Número aproximado de pacientes por mês" name="patientsPerMonth" value={form.patientsPerMonth} onChange={update} error={errors.patientsPerMonth} required><select name="patientsPerMonth" value={form.patientsPerMonth} onChange={update} aria-invalid={!!errors.patientsPerMonth} required><option value="">Selecionar</option><option>Até 250 pacientes</option><option>251–500 pacientes</option><option>501–1.000 pacientes</option><option>Mais de 1.000 pacientes</option></select></Field><Field label="Como fazem atualmente as marcações?" name="appointments" value={form.appointments} onChange={update} error={errors.appointments} required rows={4} /><Field label="Como comunicam atualmente com os pacientes?" name="communication" value={form.communication} onChange={update} error={errors.communication} required rows={4} /><Field label="O que mais gostariam de melhorar?" name="improvement" value={form.improvement} onChange={update} error={errors.improvement} required rows={4} /><Field label="Observações adicionais (opcional)" name="notes" value={form.notes} onChange={update} rows={4} /></div></div>
        <div className="pilot-form-section pilot-submit-section"><div className="pilot-section-title"><span>03</span><h2>Autorização e envio</h2></div><label className={`pilot-consent ${errors.consent ? "has-error" : ""}`}><input type="checkbox" name="consent" checked={form.consent} onChange={update} /> <span>Li e aceito que os dados submetidos sejam utilizados para entrar em contacto comigo relativamente à MyVita.</span></label>{errors.consent && <small className="pilot-consent-error">{errors.consent}</small>}<button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? "A enviar..." : "Enviar candidatura"} {!submitting && <ArrowRight size={16} />}</button>{sent && <p className="form-note success" role="status">Obrigado pelo seu interesse na MyVita.<br />Recebemos a sua candidatura e entraremos em contacto consigo.</p>}{formError && <p className="form-note error" role="alert">{formError}</p>}</div>
      </form></div></section>

      <section className="section soft pilot-trust"><div className="container"><div className="pilot-trust-heading"><ShieldCheck size={22} /><h2>Estamos a construir a MyVita com uma prioridade desde o início: confiança.</h2></div><div className="pilot-principles">{["Privacidade", "Segurança", "Controlo de acessos", "Proteção de dados", "Arquitetura preparada para os requisitos do setor da saúde"].map(item => <span key={item}>{item}</span>)}</div></div></section>

      <section className="section dark-section pilot-final-cta"><div className="container"><span className="eyebrow">Próximo passo</span><h2>A próxima fase da MyVita começa com as primeiras clínicas.</h2><p>Se acredita que a relação entre clínicas e pacientes pode ser mais simples, queremos falar consigo.</p><a className="btn btn-gold" href="#candidatura" onClick={goToForm}>Quero ser clínica piloto <ArrowRight size={17} /></a></div></section>
    </main>
    <SiteFooter />
  </div>;
}
