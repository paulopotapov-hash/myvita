import React, { useState } from "react";
import { Routes, Route, Link } from "react-router-dom";
import {
  ArrowRight, Calendar, Check, CheckCircle2, ChevronRight, Clock,
  FileText, MessageCircle, Menu, Send, ShieldCheck, User, X, Zap
} from "lucide-react";
import Prototype from "./pages/Prototype.jsx";
import PilotClinic from "./pages/PilotClinic.jsx";
import { SiteNavbar, SiteFooter } from "./components/SiteChrome.jsx";
import { ClinicsPage, ContactPage, CurrentStatePage, FaqPage, PatientsPage, ProductPage, VisionPage } from "./pages/MarketingPages.jsx";
import logo from "./assets/myvita-logo-transparent.png";
import "./styles.css";

const FORMSPREE_ENDPOINT = "https://formspree.io/f/meaojzoo";

function Navbar() {
  return <SiteNavbar />;
}

function Mockup({ clinic = false }) {
  return (
    <div className={`product-mockup ${clinic ? "clinic" : "patient"}`}>
      <div className="mock-top"><span className="mock-dot" /><span className="mock-dot" /><span className="mock-dot" /><span className="mock-title">{clinic ? "Área da Clínica" : "Área do Paciente"}</span><span className="mock-perspective">{clinic ? "CLÍNICA" : "PACIENTE"}</span></div>
      <div className="mock-body">
        <div className="mock-sidebar">
          <div className="mock-logo">myVita</div>
          <div className="mock-nav active">{clinic ? <Clock /> : <Calendar />}<span>{clinic ? "Pedidos" : "Consultas"}</span></div>
          <div className="mock-nav">{clinic ? <User /> : <FileText />}<span>{clinic ? "Pacientes" : "Resultados"}</span></div>
          <div className="mock-nav"><MessageCircle /><span>Mensagens</span></div>
        </div>
        <div className="mock-content">
          <div className="mock-heading">{clinic ? "Pedidos de marcação" : "Olá, Maria"}<span className="mock-badge">{clinic ? "3 novos" : "1 novo"}</span></div>
          <div className="mock-card"><div><strong>{clinic ? "João Costa · Cardiologia" : "Próxima consulta"}</strong><small>{clinic ? "Pedido de marcação" : "Clínica Geral · Dr. Rui Mendes"}</small></div><span className="mock-status">{clinic ? "Pendente" : "Confirmada"}</span></div>
          <div className="mock-card"><div><strong>{clinic ? "Ana Pereira · Dermatologia" : "Resultados de exames"}</strong><small>{clinic ? "Pedido recente" : "Análises ao sangue · 10 ago."}</small></div><span className="mock-status soft">{clinic ? "Confirmado" : "Novo"}</span></div>
          <div className="mock-card"><div><strong>Mensagens</strong><small>Comunicação com a clínica</small></div><MessageCircle size={16} /></div>
        </div>
      </div>
    </div>
  );
}

function SectionHead({ eyebrow, title, children, dark = false }) {
  return <div className={`section-head ${dark ? "dark" : ""}`}><span className="eyebrow">{eyebrow}</span><h2>{title}</h2>{children && <p>{children}</p>}</div>;
}

function Home() {
  const [tab, setTab] = useState("patient");
  const emptyForm = { name: "", email: "", clinic: "", role: "", phone: "", professionals: "", current_process: "", main_problem: "", interest: "" };
  const [form, setForm] = useState(emptyForm);
  const [errors, setErrors] = useState({});
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSent(false);
    setFormError("");
    const er = {};
    if (!form.name.trim()) er.name = "Indique o seu nome.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) er.email = "Indique um email profissional válido.";
    if (!form.role.trim()) er.role = "Indique a sua função.";
    if (!form.current_process.trim()) er.current_process = "Explique brevemente o processo atual.";
    if (!form.main_problem.trim()) er.main_problem = "Indique a principal dificuldade.";
    if (!form.interest.trim()) er.interest = "Selecione o seu interesse.";
    setErrors(er);
    if (Object.keys(er).length) return;
    const subject = "MyVita — Interesse de clínica";
    const payload = { ...form, _subject: subject };
    setSubmitting(true);
    try {
      const response = await fetch(FORMSPREE_ENDPOINT, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Formspree rejected the submission");
      setErrors({});
      setSent(true);
      setForm(emptyForm);
    } catch {
      setFormError("Não foi possível enviar a mensagem. Tente novamente ou contacte-nos através de PRTLABS.OFFICIAL@GMAIL.COM.");
    } finally {
      setSubmitting(false);
    }
  };

  return <>
    <Navbar />
    <main>
      <header className="hero">
        <div className="container hero-grid">
          <div className="hero-copy">
            <span className="status-pill"><i /> Protótipo funcional · Em fase de validação</span>
            <h1>A relação entre pacientes e clínicas, <em>finalmente digital.</em></h1>
            <p className="hero-tagline">Marcações. Resultados. Mensagens. Sem telefonemas.</p>
            <p className="hero-text">A MyVita simplifica as interações mais frequentes entre pacientes e prestadores de saúde, substituindo processos dispersos por uma experiência digital simples e centralizada.</p>
            <div className="hero-actions">
              <Link className="btn btn-primary" to="/clinica-piloto">Quero ser clínica piloto <ArrowRight size={17} /></Link>
              <Link className="btn btn-ghost" to="/prototipo">Ver como funciona <ArrowRight size={17} /></Link>
            </div>
            <div className="hero-note"><ShieldCheck size={15} /> Demonstração com dados fictícios</div>
          </div>
          <div className="hero-visual">
            <Mockup />
            <div className="floating-card"><span className="floating-icon"><CheckCircle2 size={17} /></span><div><strong>Pedido confirmado</strong><small>Sem uma chamada</small></div></div>
          </div>
        </div>
        <div className="container trust-strip" aria-label="Princípios da MyVita">
          <span><Check size={14} /> Simples para o paciente</span>
          <span><Check size={14} /> Útil para a clínica</span>
          <span><ShieldCheck size={14} /> Pensada com segurança desde o início</span>
        </div>
      </header>

      <section id="problema" className="section soft">
        <div className="container">
          <SectionHead eyebrow="O problema" title="A saúde continua demasiado dependente do telefone.">Do lado do paciente e do lado da clínica, o mesmo processo gera fricção todos os dias.</SectionHead>
          <div className="problem-grid">
            <article><span className="who">Paciente</span><h3>Uma relação fragmentada</h3><ul><li>Telefonemas para marcar consultas</li><li>Tempos de espera e chamadas repetidas</li><li>Resultados que exigem contacto direto</li><li>Informação espalhada por vários canais</li></ul></article>
            <div className="problem-eq">↔</div>
            <article><span className="who">Clínica</span><h3>Demasiado trabalho administrativo</h3><ul><li>Volume de chamadas e pedidos</li><li>Gestão manual de marcações</li><li>Confirmações feitas uma a uma</li><li>Comunicação dispersa pela equipa</li></ul></article>
          </div>
          <div className="problem-result">A clínica perde eficiência. O paciente perde tempo.</div>
        </div>
      </section>

      <section id="solucao" className="section">
        <div className="container">
          <SectionHead eyebrow="A solução" title="Uma relação digital entre paciente e clínica.">Começamos por resolver três interações frequentes — a visão é digitalizar progressivamente toda a relação.</SectionHead>
          <div className="flow"><span>Paciente</span><ChevronRight /><b>MyVita</b><ChevronRight /><span>Clínica</span></div>
          <div className="pillars">
            {[[Calendar, "Marcações", "Pedir e gerir marcações", "Pedido → aprovação → confirmação, sem depender de uma chamada."], [FileText, "Resultados", "Consultar resultados", "Publicação → notificação → consulta, tudo no mesmo lugar."], [MessageCircle, "Mensagens", "Comunicar com a clínica", "Mensagem → resposta → histórico, com contexto sempre disponível."]].map(([Icon, label, title, text]) => <article key={label}><Icon /><small>{label}</small><h3>{title}</h3><p>{text}</p></article>)}
          </div>
        </div>
      </section>

      <section id="como-funciona" className="section dark-section">
        <div className="container"><SectionHead dark eyebrow="Como funciona" title="Uma relação mais simples, passo a passo.">O protótipo organiza as interações essenciais entre paciente e clínica num único espaço.</SectionHead>
          <div className="steps">{[["01", "O paciente pede ou consulta.", "Marcações e resultados começam no espaço do paciente."], ["02", "A clínica gere e responde.", "A equipa recebe pedidos, publica resultados e acompanha cada conversa."], ["03", "Ambos mantêm a comunicação.", "Mensagens, respostas e contexto ficam centralizados na MyVita."]].map(([number, title, text]) => <div className="step" key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></div>)}</div>
        </div>
      </section>

      <section id="clinicas" className="section">
        <div className="container two-col">
          <div><SectionHead eyebrow="Para clínicas" title="Menos chamadas. Mais tempo para a clínica.">A MyVita centraliza pedidos de marcação, resultados e comunicação com pacientes numa experiência digital simples.</SectionHead>
            <div className="value-list">{[["01", "Menos chamadas e tarefas repetitivas", "Pode ajudar a reduzir a dependência de chamadas para interações administrativas frequentes."], ["02", "Comunicação mais organizada", "Permite centralizar pedidos, respostas e contexto numa relação paciente-clínica mais clara."], ["03", "Uma experiência digital contínua", "O objetivo é tornar mais simples a passagem entre marcações, resultados e mensagens." ]].map(x => <div className="value-item" key={x[0]}><b>{x[0]}</b><div><h3>{x[1]}</h3><p>{x[2]}</p></div></div>)}</div>
          </div>
          <aside className="clinic-cta"><span className="eyebrow">Validação</span><h3>Faz sentido explorar um piloto?</h3><p>Estamos a procurar clínicas interessadas em conhecer o conceito e testar o que pode ser mais útil na sua operação.</p><div className="clinic-actions"><Link className="btn btn-primary full" to="/clinica-piloto">Quero ser clínica piloto <ArrowRight size={17} /></Link><Link className="btn btn-ghost full" to="/contacto">Falar connosco</Link></div></aside>
        </div>
      </section>

      <section id="piloto" className="section soft"><div className="container pilot-section"><SectionHead eyebrow="Como funciona o piloto" title="Uma proposta para aprender em conjunto.">O piloto é uma possibilidade futura, a definir com cada clínica. O âmbito e os critérios serão ajustados durante a validação.</SectionHead><div className="pilot-steps">{[["01", "Conhecemos o processo atual", "Percebemos como a clínica gere hoje marcações, comunicação e resultados."], ["02", "Configuramos o piloto", "Definimos o âmbito inicial e acompanhamos a implementação."], ["03", "Medimos e aprendemos", "Recolhemos feedback da equipa e dos pacientes para melhorar o produto."]].map(([number, title, text]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div><Link className="btn btn-primary" to="/clinica-piloto">Quero falar sobre um piloto <ArrowRight size={17} /></Link></div></section>

      <section id="paciente" className="section soft"><div className="container two-col patient-section"><div><SectionHead eyebrow="Experiência do paciente" title="Tudo o que precisa, num só lugar.">Sem sistemas complexos para aprender — só o que já sabe fazer, mas mais simples.</SectionHead><div className="feature-stack">{[["Marcações", "Pedir uma consulta e acompanhar o estado do pedido."], ["Resultados", "Consultar resultados assim que a clínica os disponibiliza."], ["Mensagens", "Falar diretamente com a clínica, com o histórico sempre à mão."]].map(x => <div key={x[0]}><i /><h3>{x[0]}</h3><p>{x[1]}</p></div>)}</div></div><div className="patient-phone"><Mockup /></div></div></section>

      <section id="porque" className="section"><div className="container"><SectionHead eyebrow="Porque MyVita?" title="Uma base simples para uma relação mais próxima.">A MyVita parte de interações concretas e de uma ideia clara: tornar a comunicação entre pacientes e clínicas mais organizada.</SectionHead><div className="why-grid">{[["01", "Começar pelo essencial", "Marcações, resultados e mensagens num protótipo focado no que acontece com frequência."], ["02", "Pensar nos dois lados", "Uma experiência para o paciente e uma operação pensada para a equipa clínica."], ["03", "Construir com validação", "Cada próxima decisão deve ser aprendida com clínicas, parceiros e utilizadores."], ["04", "Avançar com responsabilidade", "A infraestrutura, a segurança e as integrações fazem parte do caminho a construir."]].map(([number, title, text]) => <article className="why-item" key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div><div className="center-actions why-cta"><Link className="btn btn-primary" to="/contacto">Falar com a equipa <ArrowRight size={17} /></Link></div></div></section>

      <section id="produto" className="section"><div className="container"><SectionHead eyebrow="Produto" title="O produto já existe — em protótipo.">Uma experiência pensada para dois lados: quem pede e quem responde.</SectionHead>
        <div className="tabs"><button className={tab === "patient" ? "active" : ""} onClick={() => setTab("patient")}>Área do Paciente</button><button className={tab === "clinic" ? "active" : ""} onClick={() => setTab("clinic")}>Área da Clínica</button></div>
        <div className="product-gallery"><Mockup clinic={tab === "clinic"} /><div className="product-copy"><span className="eyebrow">{tab === "clinic" ? "Clínica" : "Paciente"}</span><h3>{tab === "clinic" ? "Uma operação mais organizada." : "Uma experiência mais simples."}</h3><p>{tab === "clinic" ? "Pedidos, pacientes, resultados e mensagens num painel pensado para a equipa clínica." : "Marcações, resultados e mensagens num espaço centralizado, sem depender de telefonemas."}</p><ul>{(tab === "clinic" ? ["Pedidos de marcação", "Gestão de pacientes", "Publicação de resultados", "Mensagens com pacientes"] : ["Consultar marcações", "Pedir novas marcações", "Consultar resultados", "Mensagens com a clínica"]).map(x => <li key={x}><Check size={16} />{x}</li>)}</ul><Link className="btn btn-primary" to="/prototipo">Explorar protótipo <ArrowRight size={17} /></Link></div></div>
        <p className="product-note"><i /> Dados fictícios. Demonstração conceptual. O protótipo funciona em React e mantém o estado em memória.</p>
      </div></section>

      <section id="visao" className="section dark-section"><div className="container"><SectionHead dark eyebrow="Visão" title="Uma relação digital entre pacientes e prestadores de saúde.">A visão da MyVita é tornar mais simples, contínua e próxima a relação entre quem procura cuidados e quem os presta em Portugal.</SectionHead><div className="vision-list">{[["Agora", "Começar pelas interações essenciais", "Marcações, resultados e mensagens como base para validar o produto."], ["Depois", "Expandir com responsabilidade", "Alargar progressivamente a relação digital à medida que aprendemos com clínicas e pacientes."], ["A longo prazo", "Uma plataforma de relação em saúde", "Construir uma infraestrutura digital de confiança para pacientes e prestadores em Portugal."]].map(x => <div key={x[0]}><span>{x[0]}</span><div><h3>{x[1]}</h3><p>{x[2]}</p></div></div>)}</div></div></section>

      <section id="estado" className="section"><div className="container"><SectionHead eyebrow="Estado atual" title="Ambição na visão. Rigor nos factos.">A MyVita está numa fase inicial de validação. Este é o ponto de partida, com clareza sobre o que existe e o que falta construir.</SectionHead><div className="status-grid">{[["Já temos", "Protótipo funcional", ["Experiência de paciente", "Experiência de clínica", "Conceito validável"]], ["Estamos a construir", "A base para os primeiros pilotos", ["MVP e infraestrutura", "Backend e segurança", "Integrações e preparação de pilotos"]], ["Queremos alcançar", "Uma relação digital contínua", ["Pacientes e prestadores em Portugal", "Mais funcionalidades e integrações", "Expansão progressiva da plataforma"]]].map(([label, title, items]) => <article className="status-panel" key={label}><span className="eyebrow">{label}</span><h3>{title}</h3><ul>{items.map(item => <li key={item}><Check size={15} />{item}</li>)}</ul></article>)}</div></div></section>

      <section id="faq" className="section soft"><div className="container faq-layout"><SectionHead eyebrow="Perguntas frequentes" title="Clareza antes do próximo passo.">As respostas essenciais sobre o produto e o momento atual da MyVita.</SectionHead><div className="faq-list">{[["Para que tipo de clínicas é a MyVita?", "Nesta fase, procuramos conhecer diferentes operações clínicas para perceber onde o conceito pode criar mais valor."], ["A MyVita substitui o software clínico da clínica?", "Não. A proposta atual é organizar a relação e a comunicação com pacientes, sem apresentar a MyVita como substituto do software clínico."], ["A MyVita já está disponível?", "Existe atualmente um protótipo funcional. Estamos a preparar o MVP e a fase de validação com clínicas."], ["Como funciona um piloto?", "É uma proposta futura: conhecemos o processo atual, definimos um âmbito inicial e aprendemos com o feedback da equipa e dos pacientes."], ["Os dados apresentados no protótipo são reais?", "Não. A demonstração usa exclusivamente dados fictícios e estado mantido em memória."]].map(([question, answer]) => <details key={question}><summary>{question}<ChevronRight size={17} /></summary><p>{answer}</p></details>)}</div></div></section>

      <section id="cta-final" className="section dark-section cta-section"><div className="container"><SectionHead dark title="Vamos perceber se a MyVita faz sentido para a sua clínica.">Estamos a procurar clínicas interessadas em conhecer o conceito e conversar sobre um possível piloto.</SectionHead><div className="center-actions"><Link className="btn btn-gold" to="/clinica-piloto">Quero falar sobre um piloto <ArrowRight size={17} /></Link><Link className="btn btn-on-dark" to="/contacto">Falar connosco</Link></div></div></section>

      <section id="contacto" className="section"><div className="container contact-grid"><div><SectionHead eyebrow="Falar connosco" title="Vamos validar a próxima fase juntos.">Se representa uma clínica, um parceiro ou um investidor, estamos disponíveis para apresentar o protótipo e ouvir os desafios da sua operação.</SectionHead><div className="contact-details"><p><strong>Email</strong><a href="mailto:PRTLABS.OFFICIAL@GMAIL.COM">PRTLABS.OFFICIAL@GMAIL.COM</a></p><p><strong>Sede</strong>Coimbra, Portugal</p><p><strong>Fase</strong>Protótipo funcional · Em validação</p></div></div>
          <form onSubmit={submit} method="POST" action={FORMSPREE_ENDPOINT} className="contact-form" noValidate>
          <div className="form-row">{[["name", "Nome", "text", true], ["email", "Email profissional", "email", true], ["clinic", "Clínica / Empresa", "text", false], ["role", "Cargo / função", "text", true], ["phone", "Telefone (opcional)", "tel", false]].map(([key, label, type, required]) => <label key={key}>{label}<input name={key} type={type} value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} aria-invalid={!!errors[key]} required={required} />{errors[key] && <small>{errors[key]}</small>}</label>)}</div>
           <label>Número aproximado de profissionais<select name="professionals" value={form.professionals} onChange={e => setForm({ ...form, professionals: e.target.value })}><option value="">Selecionar (opcional)</option><option>1–5 profissionais</option><option>6–20 profissionais</option><option>21–50 profissionais</option><option>Mais de 50 profissionais</option></select></label>
           <label>Como gerem atualmente a comunicação com pacientes?<textarea name="current_process" rows="4" value={form.current_process} onChange={e => setForm({ ...form, current_process: e.target.value })} aria-invalid={!!errors.current_process} required />{errors.current_process && <small>{errors.current_process}</small>}</label>
           <label>Qual é a principal dificuldade que gostariam de resolver?<textarea name="main_problem" rows="4" value={form.main_problem} onChange={e => setForm({ ...form, main_problem: e.target.value })} aria-invalid={!!errors.main_problem} required />{errors.main_problem && <small>{errors.main_problem}</small>}</label>
           <label>Interesse<select name="interest" value={form.interest} onChange={e => setForm({ ...form, interest: e.target.value })} required aria-invalid={!!errors.interest}><option value="">Selecionar interesse</option><option>Tenho interesse em conhecer a MyVita</option><option>Tenho interesse em participar num piloto</option><option>Quero apenas saber mais</option></select>{errors.interest && <small>{errors.interest}</small>}</label>
           <button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? "A enviar…" : "Enviar mensagem"} {!submitting && <Send size={16} />}</button>
           {sent && <p className="form-note success">Obrigado pelo interesse na MyVita. Recebemos os seus dados e entraremos em contacto consigo.</p>}
           {formError && <p className="form-note error" role="alert">{formError}</p>}
           <p className="form-note">Os dados são enviados através do Formspree para PRTLABS.OFFICIAL@GMAIL.COM.</p>
          </form>
      </div></section>
      <section className="section soft legal-section"><div className="container legal-grid"><article id="privacidade"><span className="eyebrow">Privacidade</span><h3>Política de Privacidade</h3><p>Estrutura inicial para revisão jurídica antes do lançamento público. O protótipo usa dados fictícios e o formulário não guarda dados numa base de dados.</p></article><article id="termos"><span className="eyebrow">Termos</span><h3>Termos de Utilização</h3><p>Estrutura inicial para definir as condições de utilização do website e do protótipo, sujeita a revisão jurídica.</p></article></div></section>
    </main>
    <SiteFooter />
  </>;
}

export default function App() {
  return <Routes>
    <Route path="/" element={<Home />} />
    <Route path="/produto" element={<ProductPage />} />
    <Route path="/clinicas" element={<ClinicsPage />} />
    <Route path="/pacientes" element={<PatientsPage />} />
    <Route path="/visao" element={<VisionPage />} />
    <Route path="/estado-atual" element={<CurrentStatePage />} />
    <Route path="/faq" element={<FaqPage />} />
    <Route path="/contacto" element={<ContactPage />} />
    <Route path="/clinica-piloto" element={<PilotClinic />} />
    <Route path="/prototipo" element={<Prototype />} />
    <Route path="*" element={<Home />} />
  </Routes>;
}
