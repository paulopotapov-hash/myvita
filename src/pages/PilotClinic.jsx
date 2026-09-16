import React, { useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { Link } from "react-router-dom";
import { SiteFooter, SiteNavbar } from "../components/SiteChrome.jsx";

const FORMSPREE_ENDPOINT = "https://formspree.io/f/meaojzoo";

const initialForm = {
  clinicName: "",
  city: "",
  professionals: "",
  healthAreas: "",
  website: "",
  contactName: "",
  role: "",
  email: "",
  phone: "",
  appointments: "",
  results: "",
  patientCommunication: "",
  currentSoftware: "",
  callVolume: "",
  patientRelationship: "",
  importantFeatures: "",
  interest: "",
};

const requiredFields = {
  clinicName: "Indique o nome da clínica.",
  city: "Indique a cidade.",
  professionals: "Indique o número aproximado de profissionais.",
  healthAreas: "Indique a área de saúde.",
  contactName: "Indique o seu nome.",
  role: "Indique o seu cargo ou função.",
  email: "Indique um email profissional válido.",
  phone: "Indique um telefone.",
  appointments: "Descreva como fazem atualmente as marcações.",
  results: "Descreva como comunicam resultados.",
  patientCommunication: "Descreva como comunicam com pacientes.",
  currentSoftware: "Indique o software utilizado atualmente.",
  patientRelationship: "Indique o que gostaria de melhorar.",
  importantFeatures: "Indique as funcionalidades mais importantes.",
  interest: "Indique o seu interesse no piloto.",
};

function Field({ label, name, value, onChange, error, required = false, type = "text", children, rows }) {
  return (
    <label className="pilot-field">
      <span>{label}{required && <b aria-hidden="true"> *</b>}</span>
      {children || (rows ? <textarea name={name} rows={rows} value={value} onChange={onChange} aria-invalid={!!error} required={required} /> : <input name={name} type={type} value={value} onChange={onChange} aria-invalid={!!error} required={required} />)}
      {error && <small>{error}</small>}
    </label>
  );
}

function PilotSection({ number, title, children }) {
  return <section className="pilot-form-section"><div className="pilot-section-title"><span>{number}</span><h2>{title}</h2></div>{children}</section>;
}

export default function PilotClinic() {
  const [form, setForm] = useState(initialForm);
  const [errors, setErrors] = useState({});
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const update = e => setForm({ ...form, [e.target.name]: e.target.value });

  const submit = async e => {
    e.preventDefault();
    setSent(false);
    setFormError("");
    const nextErrors = {};
    Object.entries(requiredFields).forEach(([name, message]) => {
      if (!form[name].trim()) nextErrors[name] = message;
    });
    if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      nextErrors.email = "Indique um email profissional válido.";
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;

    setSubmitting(true);
    try {
      const response = await fetch(FORMSPREE_ENDPOINT, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, _subject: "MyVita — Candidatura de clínica piloto" }),
      });
      if (!response.ok) throw new Error("Formspree rejected the submission");
      setErrors({});
      setForm(initialForm);
      setSent(true);
    } catch {
      setFormError("Não foi possível enviar a candidatura. Tente novamente ou contacte-nos através de PRTLABS.OFFICIAL@GMAIL.COM.");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="pilot-page">
    <SiteNavbar />
    <main>
      <section className="pilot-hero"><div className="container pilot-hero-inner"><span className="eyebrow">Programa de validação</span><h1>Quero ser clínica piloto</h1><p>Estamos a selecionar as primeiras clínicas para testar e desenvolver a MyVita em conjunto com profissionais de saúde.</p><p className="pilot-intro">Participar no programa piloto significa conhecer a plataforma numa fase inicial, partilhar a experiência da sua equipa e ajudar a definir as funcionalidades que podem tornar a relação com os pacientes mais simples.</p></div></section>
      <section className="pilot-benefits"><div className="container"><div className="pilot-benefits-head"><span className="eyebrow">Uma construção conjunta</span><h2>O que significa ser clínica piloto?</h2></div><div className="benefit-grid">{["Acesso antecipado à plataforma", "Participação no desenvolvimento do produto", "Feedback direto com a equipa MyVita", "Teste de funcionalidades em contexto real"].map(item => <div className="benefit-item" key={item}><Check size={17} /><span>{item}</span></div>)}</div></div></section>
      <section className="pilot-form-wrap"><div className="container pilot-form-layout"><div className="pilot-form-aside"><span className="eyebrow">Candidatura</span><h2>Conte-nos como trabalha hoje.</h2><p>As suas respostas ajudam-nos a perceber o contexto da sua clínica e onde a MyVita pode criar valor real.</p><p className="required-note"><b>*</b> Campos obrigatórios</p></div><form className="pilot-form" onSubmit={submit} noValidate>
        <PilotSection number="01" title="Sobre a clínica"><div className="pilot-fields two"><Field label="Nome da clínica" name="clinicName" value={form.clinicName} onChange={update} error={errors.clinicName} required /><Field label="Cidade" name="city" value={form.city} onChange={update} error={errors.city} required /><Field label="Número aproximado de profissionais" name="professionals" value={form.professionals} onChange={update} error={errors.professionals} required><select name="professionals" value={form.professionals} onChange={update} aria-invalid={!!errors.professionals} required><option value="">Selecionar</option><option>1–5 profissionais</option><option>6–20 profissionais</option><option>21–50 profissionais</option><option>Mais de 50 profissionais</option></select></Field><Field label="Área(s) de saúde" name="healthAreas" value={form.healthAreas} onChange={update} error={errors.healthAreas} required /><Field label="Website" name="website" value={form.website} onChange={update} type="url" /></div></PilotSection>
        <PilotSection number="02" title="Contacto"><div className="pilot-fields two"><Field label="Nome" name="contactName" value={form.contactName} onChange={update} error={errors.contactName} required /><Field label="Cargo / função" name="role" value={form.role} onChange={update} error={errors.role} required /><Field label="Email profissional" name="email" value={form.email} onChange={update} error={errors.email} required type="email" /><Field label="Telefone" name="phone" value={form.phone} onChange={update} error={errors.phone} required type="tel" /></div></PilotSection>
        <PilotSection number="03" title="Processos atuais"><div className="pilot-fields"><Field label="Como fazem atualmente as marcações?" name="appointments" value={form.appointments} onChange={update} error={errors.appointments} required rows="3" /><Field label="Como comunicam resultados?" name="results" value={form.results} onChange={update} error={errors.results} required rows="3" /><Field label="Como comunicam com pacientes?" name="patientCommunication" value={form.patientCommunication} onChange={update} error={errors.patientCommunication} required rows="3" /><Field label="Que software utilizam atualmente?" name="currentSoftware" value={form.currentSoftware} onChange={update} error={errors.currentSoftware} required /><Field label="Volume aproximado de chamadas recebidas" name="callVolume" value={form.callVolume} onChange={update}><select name="callVolume" value={form.callVolume} onChange={update}><option value="">Selecionar (opcional)</option><option>Até 20 por dia</option><option>21–50 por dia</option><option>51–100 por dia</option><option>Mais de 100 por dia</option></select></Field></div></PilotSection>
        <PilotSection number="04" title="Interesse na MyVita"><div className="pilot-fields"><Field label="O que gostaria de melhorar na relação com os pacientes?" name="patientRelationship" value={form.patientRelationship} onChange={update} error={errors.patientRelationship} required rows="4" /><Field label="Que funcionalidades seriam mais importantes?" name="importantFeatures" value={form.importantFeatures} onChange={update} error={errors.importantFeatures} required rows="4" /><Field label="Teria interesse em participar num piloto?" name="interest" value={form.interest} onChange={update} error={errors.interest} required><select name="interest" value={form.interest} onChange={update} aria-invalid={!!errors.interest} required><option value="">Selecionar</option><option>Sim, tenho interesse</option><option>Gostaria de saber mais primeiro</option><option>Não neste momento</option></select></Field></div></PilotSection>
        <PilotSection number="05" title="Submissão"><div className="pilot-submit"><p>Ao enviar, a sua candidatura será encaminhada para a equipa MyVita através do Formspree.</p><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? "A enviar..." : "Enviar candidatura"} {!submitting && <ArrowRight size={16} />}</button>{sent && <p className="form-note success" role="status">Obrigado. Recebemos a sua candidatura e entraremos em contacto consigo.</p>}{formError && <p className="form-note error" role="alert">{formError}</p>}</div></PilotSection>
      </form></div></section>
    </main>
    <SiteFooter />
  </div>;
}
