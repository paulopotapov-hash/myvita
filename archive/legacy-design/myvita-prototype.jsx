import React, { useState } from "react";
import {
  Calendar, FileText, MessageCircle, User, Check, X, Plus, Send,
  Stethoscope, ChevronDown, Clock, ArrowLeft, CheckCircle2, AlertCircle
} from "lucide-react";

// ---------------------------------------------------------------------------
// SEED DATA — simulates what would live in a real database
// ---------------------------------------------------------------------------
const initialData = {
  clinicName: "Clínica Bem-Estar",
  patients: [
    {
      id: "p1",
      name: "Maria Silva",
      birthDate: "1987-04-12",
      appointments: [
        { id: "a1", specialty: "Clínica Geral", doctor: "Dr. Rui Mendes", date: "2026-08-28", time: "10:30" },
      ],
      requests: [],
      results: [
        { id: "r1", title: "Análises ao sangue", date: "2026-08-10", summary: "Valores dentro da normalidade. Colesterol ligeiramente elevado.", seen: false },
      ],
      messages: [
        { id: "m1", from: "clinic", text: "Olá Maria, os resultados das análises já estão disponíveis.", date: "2026-08-11" },
      ],
    },
    {
      id: "p2",
      name: "João Costa",
      birthDate: "1979-11-02",
      appointments: [],
      requests: [
        { id: "req1", specialty: "Cardiologia", preferredDate: "2026-09-02", reason: "Dores no peito ocasionais", status: "pending" },
      ],
      results: [],
      messages: [],
    },
    {
      id: "p3",
      name: "Ana Pereira",
      birthDate: "1995-06-23",
      appointments: [
        { id: "a2", specialty: "Dermatologia", doctor: "Dra. Sofia Nunes", date: "2026-09-05", time: "15:00" },
      ],
      requests: [],
      results: [
        { id: "r2", title: "Exame de pele", date: "2026-08-15", summary: "Sem sinais de preocupação. Repetir controlo em 6 meses.", seen: true },
      ],
      messages: [],
    },
  ],
};

const SPECIALTIES = ["Clínica Geral", "Cardiologia", "Dermatologia", "Ortopedia", "Ginecologia", "Pediatria"];

// ---------------------------------------------------------------------------
// STYLE — design tokens, embedded so the artifact needs no build step
// ---------------------------------------------------------------------------
const Style = () => (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

    .mv-root {
      --bg: #F2F5F2;
      --surface: #FFFFFF;
      --ink: #16232B;
      --ink-soft: #56666C;
      --primary: #16324F;
      --primary-soft: #E7EEF1;
      --accent: #C98A2C;
      --accent-soft: #FBF0DD;
      --success: #3F7A63;
      --success-soft: #E7F2EC;
      --danger: #B3432E;
      --danger-soft: #F7E9E5;
      --border: #DCE3DD;

      background: var(--bg);
      color: var(--ink);
      font-family: 'IBM Plex Sans', sans-serif;
      min-height: 100%;
      width: 100%;
    }
    .mv-root * { box-sizing: border-box; }
    .mv-display { font-family: 'Fraunces', serif; }
    .mv-mono { font-family: 'IBM Plex Mono', monospace; }

    .mv-tiles {
      background-image:
        linear-gradient(45deg, var(--primary) 25%, transparent 25%),
        linear-gradient(-45deg, var(--primary) 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, var(--primary) 75%),
        linear-gradient(-45deg, transparent 75%, var(--primary) 75%);
      background-size: 24px 24px;
      background-position: 0 0, 0 12px, 12px -12px, -12px 0px;
      opacity: 0.06;
    }

    .mv-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
    }
    .mv-btn {
      font-family: 'IBM Plex Sans', sans-serif;
      font-weight: 500;
      border-radius: 10px;
      padding: 9px 16px;
      cursor: pointer;
      border: 1px solid transparent;
      transition: transform 0.05s ease, opacity 0.15s ease;
      display: inline-flex; align-items: center; gap: 8px;
      font-size: 14px;
    }
    .mv-btn:active { transform: scale(0.98); }
    .mv-btn-primary { background: var(--primary); color: white; }
    .mv-btn-primary:hover { opacity: 0.9; }
    .mv-btn-accent { background: var(--accent); color: white; }
    .mv-btn-accent:hover { opacity: 0.9; }
    .mv-btn-ghost { background: transparent; color: var(--primary); border-color: var(--border); }
    .mv-btn-ghost:hover { background: var(--primary-soft); }
    .mv-btn-danger { background: var(--danger-soft); color: var(--danger); }
    .mv-btn-danger:hover { opacity: 0.85; }
    .mv-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    .mv-input, .mv-select, .mv-textarea {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 12px;
      font-family: 'IBM Plex Sans', sans-serif;
      font-size: 14px;
      color: var(--ink);
      background: white;
    }
    .mv-input:focus, .mv-select:focus, .mv-textarea:focus {
      outline: 2px solid var(--primary);
      outline-offset: 1px;
    }
    .mv-label {
      font-size: 12px;
      font-weight: 500;
      color: var(--ink-soft);
      margin-bottom: 4px;
      display: block;
    }
    .mv-badge {
      font-size: 11px;
      font-weight: 500;
      padding: 3px 9px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .mv-nav-item {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px;
      border-radius: 10px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      color: var(--ink-soft);
    }
    .mv-nav-item:hover { background: var(--primary-soft); }
    .mv-nav-item.active { background: var(--primary); color: white; }

    .mv-scroll::-webkit-scrollbar { width: 6px; }
    .mv-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
  `}</style>
);

// ---------------------------------------------------------------------------
// SMALL PRESENTATIONAL HELPERS
// ---------------------------------------------------------------------------
function Badge({ tone = "primary", children, icon: Icon }) {
  const map = {
    primary: { bg: "var(--primary-soft)", color: "var(--primary)" },
    success: { bg: "var(--success-soft)", color: "var(--success)" },
    accent: { bg: "var(--accent-soft)", color: "var(--accent)" },
    danger: { bg: "var(--danger-soft)", color: "var(--danger)" },
  }[tone];
  return (
    <span className="mv-badge" style={{ background: map.bg, color: map.color }}>
      {Icon && <Icon size={12} />}
      {children}
    </span>
  );
}

function fmtDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-PT", { day: "2-digit", month: "short", year: "numeric" });
}

// ---------------------------------------------------------------------------
// LOGIN / ROLE SELECTOR
// ---------------------------------------------------------------------------
function LoginScreen({ patients, onEnter }) {
  const [role, setRole] = useState("patient");
  const [patientId, setPatientId] = useState(patients[0].id);

  return (
    <div className="mv-root" style={{ minHeight: "600px", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ width: "100%", maxWidth: 420 }}>
        <div className="mv-card" style={{ overflow: "hidden" }}>
          <div style={{ position: "relative", background: "var(--primary)", padding: "28px 28px 22px", color: "white" }}>
            <div className="mv-tiles" style={{ position: "absolute", inset: 0 }} />
            <div style={{ position: "relative" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                <Stethoscope size={22} />
                <span className="mv-mono" style={{ fontSize: 12, letterSpacing: 1, opacity: 0.85 }}>PROTÓTIPO</span>
              </div>
              <h1 className="mv-display" style={{ fontSize: 30, margin: 0, fontWeight: 600 }}>myVita</h1>
              <p style={{ margin: "4px 0 0", fontSize: 13, opacity: 0.85 }}>Marcações, resultados e mensagens, sem telefonemas.</p>
            </div>
          </div>

          <div style={{ padding: 28 }}>
            <label className="mv-label">Entrar como</label>
            <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
              <button
                className={`mv-btn ${role === "patient" ? "mv-btn-primary" : "mv-btn-ghost"}`}
                style={{ flex: 1, justifyContent: "center" }}
                onClick={() => setRole("patient")}
              >
                <User size={15} /> Paciente
              </button>
              <button
                className={`mv-btn ${role === "clinic" ? "mv-btn-primary" : "mv-btn-ghost"}`}
                style={{ flex: 1, justifyContent: "center" }}
                onClick={() => setRole("clinic")}
              >
                <Stethoscope size={15} /> Clínica
              </button>
            </div>

            {role === "patient" && (
              <div style={{ marginBottom: 18 }}>
                <label className="mv-label">Escolher paciente de demonstração</label>
                <select className="mv-select" value={patientId} onChange={(e) => setPatientId(e.target.value)}>
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}

            {role === "clinic" && (
              <div style={{ marginBottom: 18, fontSize: 13, color: "var(--ink-soft)" }}>
                Vai entrar como equipa da <strong>Clínica Bem-Estar</strong>, com acesso a todos os pacientes.
              </div>
            )}

            <button
              className="mv-btn mv-btn-accent"
              style={{ width: "100%", justifyContent: "center", padding: "11px 16px" }}
              onClick={() => onEnter(role, role === "patient" ? patientId : null)}
            >
              Entrar <ChevronDown size={14} style={{ transform: "rotate(-90deg)" }} />
            </button>
          </div>
        </div>
        <p style={{ textAlign: "center", fontSize: 12, color: "var(--ink-soft)", marginTop: 14 }}>
          Dados fictícios para demonstração. Nenhuma informação real de saúde é usada.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SHELL — shared layout for both roles
// ---------------------------------------------------------------------------
function Shell({ title, subtitle, nav, activeTab, setActiveTab, onLogout, children }) {
  return (
    <div className="mv-root" style={{ minHeight: "600px", display: "flex" }}>
      <aside style={{ width: 220, borderRight: "1px solid var(--border)", padding: 20, display: "flex", flexDirection: "column", background: "var(--surface)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 28, padding: "0 6px" }}>
          <Stethoscope size={20} color="var(--primary)" />
          <span className="mv-display" style={{ fontWeight: 600, fontSize: 19, color: "var(--primary)" }}>myVita</span>
        </div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
          {nav.map((item) => (
            <div
              key={item.key}
              className={`mv-nav-item ${activeTab === item.key ? "active" : ""}`}
              onClick={() => setActiveTab(item.key)}
            >
              <item.icon size={16} />
              {item.label}
              {item.count > 0 && (
                <span style={{
                  marginLeft: "auto", fontSize: 11, fontWeight: 600,
                  background: activeTab === item.key ? "rgba(255,255,255,0.25)" : "var(--accent-soft)",
                  color: activeTab === item.key ? "white" : "var(--accent)",
                  borderRadius: 999, padding: "1px 7px",
                }}>{item.count}</span>
              )}
            </div>
          ))}
        </nav>
        <button className="mv-btn mv-btn-ghost" style={{ justifyContent: "center" }} onClick={onLogout}>
          <ArrowLeft size={14} /> Trocar utilizador
        </button>
      </aside>

      <main style={{ flex: 1, padding: "28px 36px", overflowY: "auto" }} className="mv-scroll">
        <div style={{ marginBottom: 24 }}>
          <h2 className="mv-display" style={{ fontSize: 24, margin: 0, fontWeight: 600 }}>{title}</h2>
          {subtitle && <p style={{ margin: "4px 0 0", color: "var(--ink-soft)", fontSize: 14 }}>{subtitle}</p>}
        </div>
        {children}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PATIENT VIEW
// ---------------------------------------------------------------------------
function PatientView({ patient, onLogout, actions }) {
  const [tab, setTab] = useState("appointments");
  const [showRequestForm, setShowRequestForm] = useState(false);
  const [form, setForm] = useState({ specialty: SPECIALTIES[0], preferredDate: "", reason: "" });
  const [messageText, setMessageText] = useState("");

  const nav = [
    { key: "appointments", label: "Consultas", icon: Calendar, count: patient.requests.filter(r => r.status === "pending").length },
    { key: "results", label: "Resultados", icon: FileText, count: patient.results.filter(r => !r.seen).length },
    { key: "messages", label: "Mensagens", icon: MessageCircle, count: 0 },
  ];

  const submitRequest = () => {
    if (!form.preferredDate || !form.reason.trim()) return;
    actions.requestAppointment(patient.id, form);
    setForm({ specialty: SPECIALTIES[0], preferredDate: "", reason: "" });
    setShowRequestForm(false);
  };

  return (
    <Shell
      title={`Olá, ${patient.name.split(" ")[0]}`}
      subtitle="O seu espaço pessoal na Clínica Bem-Estar"
      nav={nav}
      activeTab={tab}
      setActiveTab={setTab}
      onLogout={onLogout}
    >
      {tab === "appointments" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="mv-card" style={{ padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Próximas consultas</h3>
              <button className="mv-btn mv-btn-accent" onClick={() => setShowRequestForm(!showRequestForm)}>
                <Plus size={14} /> Pedir consulta
              </button>
            </div>

            {showRequestForm && (
              <div style={{ background: "var(--bg)", borderRadius: 10, padding: 16, marginBottom: 14, display: "flex", flexDirection: "column", gap: 10 }}>
                <div>
                  <label className="mv-label">Especialidade</label>
                  <select className="mv-select" value={form.specialty} onChange={(e) => setForm({ ...form, specialty: e.target.value })}>
                    {SPECIALTIES.map((s) => <option key={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mv-label">Data preferida</label>
                  <input type="date" className="mv-input" value={form.preferredDate} onChange={(e) => setForm({ ...form, preferredDate: e.target.value })} />
                </div>
                <div>
                  <label className="mv-label">Motivo</label>
                  <textarea className="mv-textarea" rows={2} placeholder="Descreva brevemente o motivo da consulta"
                    value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
                </div>
                <button className="mv-btn mv-btn-primary" style={{ alignSelf: "flex-start" }} onClick={submitRequest}>
                  Enviar pedido
                </button>
              </div>
            )}

            {patient.appointments.length === 0 && patient.requests.length === 0 && (
              <p style={{ color: "var(--ink-soft)", fontSize: 14 }}>Sem consultas agendadas.</p>
            )}

            {patient.appointments.map((a) => (
              <div key={a.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderTop: "1px solid var(--border)" }}>
                <div>
                  <div style={{ fontWeight: 500, fontSize: 14 }}>{a.specialty}</div>
                  <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>{a.doctor}</div>
                </div>
                <Badge tone="success" icon={CheckCircle2}>{fmtDate(a.date)} · {a.time}</Badge>
              </div>
            ))}

            {patient.requests.map((r) => (
              <div key={r.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderTop: "1px solid var(--border)" }}>
                <div>
                  <div style={{ fontWeight: 500, fontSize: 14 }}>{r.specialty}</div>
                  <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>{r.reason}</div>
                </div>
                <Badge tone={r.status === "pending" ? "accent" : "danger"} icon={r.status === "pending" ? Clock : X}>
                  {r.status === "pending" ? "Pedido enviado" : "Recusado"}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "results" && (
        <div className="mv-card" style={{ padding: 20 }}>
          <h3 style={{ margin: "0 0 14px", fontSize: 15, fontWeight: 600 }}>Resultados de exames</h3>
          {patient.results.length === 0 && <p style={{ color: "var(--ink-soft)", fontSize: 14 }}>Ainda sem resultados.</p>}
          {patient.results.map((r) => (
            <div key={r.id} style={{ padding: "14px 0", borderTop: "1px solid var(--border)" }}
              onClick={() => actions.markResultSeen(patient.id, r.id)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontWeight: 500, fontSize: 14 }}>{r.title}</span>
                {!r.seen && <Badge tone="accent">Novo</Badge>}
              </div>
              <div className="mv-mono" style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 6 }}>{fmtDate(r.date)}</div>
              <div style={{ fontSize: 13, color: "var(--ink)" }}>{r.summary}</div>
            </div>
          ))}
        </div>
      )}

      {tab === "messages" && (
        <div className="mv-card" style={{ padding: 20, display: "flex", flexDirection: "column", height: 440 }}>
          <h3 style={{ margin: "0 0 14px", fontSize: 15, fontWeight: 600 }}>Mensagens com a clínica</h3>
          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }} className="mv-scroll">
            {patient.messages.length === 0 && <p style={{ color: "var(--ink-soft)", fontSize: 14 }}>Sem mensagens ainda.</p>}
            {patient.messages.map((m) => (
              <div key={m.id} style={{
                alignSelf: m.from === "patient" ? "flex-end" : "flex-start",
                background: m.from === "patient" ? "var(--primary)" : "var(--bg)",
                color: m.from === "patient" ? "white" : "var(--ink)",
                borderRadius: 12, padding: "9px 13px", maxWidth: "75%", fontSize: 14,
              }}>
                {m.text}
                <div className="mv-mono" style={{ fontSize: 10, opacity: 0.7, marginTop: 4 }}>{fmtDate(m.date)}</div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <input className="mv-input" placeholder="Escreva uma mensagem…" value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && messageText.trim()) { actions.sendMessage(patient.id, "patient", messageText); setMessageText(""); } }} />
            <button className="mv-btn mv-btn-primary" onClick={() => { if (messageText.trim()) { actions.sendMessage(patient.id, "patient", messageText); setMessageText(""); } }}>
              <Send size={14} />
            </button>
          </div>
        </div>
      )}
    </Shell>
  );
}

// ---------------------------------------------------------------------------
// CLINIC VIEW
// ---------------------------------------------------------------------------
function ClinicView({ patients, onLogout, actions }) {
  const [tab, setTab] = useState("requests");
  const [selectedPatientId, setSelectedPatientId] = useState(patients[0].id);
  const [resultForm, setResultForm] = useState({ title: "", summary: "" });
  const [messageText, setMessageText] = useState("");

  const pendingCount = patients.reduce((n, p) => n + p.requests.filter(r => r.status === "pending").length, 0);
  const selectedPatient = patients.find((p) => p.id === selectedPatientId);

  const nav = [
    { key: "requests", label: "Pedidos", icon: Clock, count: pendingCount },
    { key: "patients", label: "Pacientes", icon: User, count: 0 },
  ];

  const submitResult = () => {
    if (!resultForm.title.trim() || !resultForm.summary.trim()) return;
    actions.addResult(selectedPatientId, resultForm);
    setResultForm({ title: "", summary: "" });
  };

  return (
    <Shell
      title="Clínica Bem-Estar"
      subtitle="Painel da equipa clínica"
      nav={nav}
      activeTab={tab}
      setActiveTab={setTab}
      onLogout={onLogout}
    >
      {tab === "requests" && (
        <div className="mv-card" style={{ padding: 20 }}>
          <h3 style={{ margin: "0 0 14px", fontSize: 15, fontWeight: 600 }}>Pedidos de marcação</h3>
          {patients.flatMap(p => p.requests.filter(r => r.status === "pending").map(r => ({ ...r, patient: p }))).length === 0 && (
            <p style={{ color: "var(--ink-soft)", fontSize: 14 }}>Sem pedidos pendentes. Tudo tratado.</p>
          )}
          {patients.flatMap(p => p.requests.filter(r => r.status === "pending").map(r => ({ ...r, patient: p }))).map((r) => (
            <div key={r.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 0", borderTop: "1px solid var(--border)" }}>
              <div>
                <div style={{ fontWeight: 500, fontSize: 14 }}>{r.patient.name} <span style={{ color: "var(--ink-soft)", fontWeight: 400 }}>· {r.specialty}</span></div>
                <div style={{ fontSize: 13, color: "var(--ink-soft)" }}>{r.reason}</div>
                <div className="mv-mono" style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 2 }}>Preferência: {fmtDate(r.preferredDate)}</div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="mv-btn mv-btn-danger" onClick={() => actions.rejectRequest(r.patient.id, r.id)}><X size={14} /> Recusar</button>
                <button className="mv-btn mv-btn-primary" onClick={() => actions.approveRequest(r.patient.id, r.id)}><Check size={14} /> Confirmar</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "patients" && (
        <div style={{ display: "flex", gap: 20 }}>
          <div className="mv-card" style={{ padding: 12, width: 220, flexShrink: 0, height: "fit-content" }}>
            {patients.map((p) => (
              <div key={p.id} onClick={() => setSelectedPatientId(p.id)}
                className="mv-nav-item"
                style={{
                  background: selectedPatientId === p.id ? "var(--primary-soft)" : "transparent",
                  color: selectedPatientId === p.id ? "var(--primary)" : "var(--ink-soft)",
                  marginBottom: 2,
                }}>
                <User size={14} /> {p.name}
              </div>
            ))}
          </div>

          {selectedPatient && (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
              <div className="mv-card" style={{ padding: 20 }}>
                <h3 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 600 }}>{selectedPatient.name}</h3>
                <p className="mv-mono" style={{ margin: 0, fontSize: 12, color: "var(--ink-soft)" }}>Nascimento: {fmtDate(selectedPatient.birthDate)}</p>
              </div>

              <div className="mv-card" style={{ padding: 20 }}>
                <h4 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 600 }}>Adicionar resultado de exame</h4>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <input className="mv-input" placeholder="Título (ex: Análises ao sangue)"
                    value={resultForm.title} onChange={(e) => setResultForm({ ...resultForm, title: e.target.value })} />
                  <textarea className="mv-textarea" rows={2} placeholder="Resumo para o paciente"
                    value={resultForm.summary} onChange={(e) => setResultForm({ ...resultForm, summary: e.target.value })} />
                  <button className="mv-btn mv-btn-primary" style={{ alignSelf: "flex-start" }} onClick={submitResult}>
                    <Plus size={14} /> Publicar resultado
                  </button>
                </div>
                {selectedPatient.results.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    {selectedPatient.results.map(r => (
                      <div key={r.id} style={{ fontSize: 13, color: "var(--ink-soft)", padding: "8px 0", borderTop: "1px solid var(--border)" }}>
                        {r.title} — <span className="mv-mono">{fmtDate(r.date)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="mv-card" style={{ padding: 20, display: "flex", flexDirection: "column", height: 320 }}>
                <h4 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 600 }}>Mensagens</h4>
                <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }} className="mv-scroll">
                  {selectedPatient.messages.length === 0 && <p style={{ color: "var(--ink-soft)", fontSize: 14 }}>Sem mensagens.</p>}
                  {selectedPatient.messages.map((m) => (
                    <div key={m.id} style={{
                      alignSelf: m.from === "clinic" ? "flex-end" : "flex-start",
                      background: m.from === "clinic" ? "var(--primary)" : "var(--bg)",
                      color: m.from === "clinic" ? "white" : "var(--ink)",
                      borderRadius: 12, padding: "9px 13px", maxWidth: "75%", fontSize: 14,
                    }}>
                      {m.text}
                      <div className="mv-mono" style={{ fontSize: 10, opacity: 0.7, marginTop: 4 }}>{fmtDate(m.date)}</div>
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <input className="mv-input" placeholder="Responder ao paciente…" value={messageText}
                    onChange={(e) => setMessageText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && messageText.trim()) { actions.sendMessage(selectedPatientId, "clinic", messageText); setMessageText(""); } }} />
                  <button className="mv-btn mv-btn-primary" onClick={() => { if (messageText.trim()) { actions.sendMessage(selectedPatientId, "clinic", messageText); setMessageText(""); } }}>
                    <Send size={14} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}

// ---------------------------------------------------------------------------
// ROOT APP — owns the "database" (in-memory) and wires both views to it
// ---------------------------------------------------------------------------
export default function App() {
  const [data, setData] = useState(initialData);
  const [viewer, setViewer] = useState(null); // { role, patientId }

  const updatePatient = (patientId, updater) => {
    setData((prev) => ({
      ...prev,
      patients: prev.patients.map((p) => (p.id === patientId ? updater(p) : p)),
    }));
  };

  const actions = {
    requestAppointment: (patientId, form) => {
      updatePatient(patientId, (p) => ({
        ...p,
        requests: [...p.requests, { id: "req_" + Date.now(), status: "pending", ...form }],
      }));
    },
    approveRequest: (patientId, requestId) => {
      updatePatient(patientId, (p) => {
        const req = p.requests.find((r) => r.id === requestId);
        return {
          ...p,
          requests: p.requests.filter((r) => r.id !== requestId),
          appointments: [...p.appointments, {
            id: "a_" + Date.now(), specialty: req.specialty, doctor: "A atribuir",
            date: req.preferredDate, time: "A confirmar",
          }],
        };
      });
    },
    rejectRequest: (patientId, requestId) => {
      updatePatient(patientId, (p) => ({
        ...p,
        requests: p.requests.map((r) => (r.id === requestId ? { ...r, status: "rejected" } : r)),
      }));
    },
    markResultSeen: (patientId, resultId) => {
      updatePatient(patientId, (p) => ({
        ...p,
        results: p.results.map((r) => (r.id === resultId ? { ...r, seen: true } : r)),
      }));
    },
    addResult: (patientId, form) => {
      updatePatient(patientId, (p) => ({
        ...p,
        results: [...p.results, { id: "r_" + Date.now(), date: new Date().toISOString().slice(0, 10), seen: false, ...form }],
      }));
    },
    sendMessage: (patientId, from, text) => {
      updatePatient(patientId, (p) => ({
        ...p,
        messages: [...p.messages, { id: "m_" + Date.now(), from, text, date: new Date().toISOString().slice(0, 10) }],
      }));
    },
  };

  if (!viewer) {
    return (
      <>
        <Style />
        <LoginScreen patients={data.patients} onEnter={(role, patientId) => setViewer({ role, patientId })} />
      </>
    );
  }

  if (viewer.role === "patient") {
    const patient = data.patients.find((p) => p.id === viewer.patientId);
    return (
      <>
        <Style />
        <PatientView patient={patient} onLogout={() => setViewer(null)} actions={actions} />
      </>
    );
  }

  return (
    <>
      <Style />
      <ClinicView patients={data.patients} onLogout={() => setViewer(null)} actions={actions} />
    </>
  );
}
