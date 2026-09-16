import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Menu, X } from "lucide-react";
import logo from "../assets/myvita-logo-transparent.png";

const siteLinks = [
  ["Produto", "/produto"],
  ["Para Clínicas", "/clinicas"],
  ["Para Pacientes", "/pacientes"],
  ["Visão", "/visao"],
  ["Estado atual", "/estado-atual"],
  ["FAQ", "/faq"],
];

export function SiteNavbar() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const closeMenu = () => setOpen(false);

  return <nav className="navbar">
    <div className="container nav-inner">
      <Link className="brand-button" to="/" onClick={closeMenu} aria-label="Ir para a homepage">
        <img src={logo} alt="MyVita" className="brand-logo" />
        <span>MyVita</span>
      </Link>
      <div className={`nav-links ${open ? "open" : ""}`}>
        {siteLinks.map(([label, path]) => <Link key={path} to={path} className={location.pathname === path ? "active" : ""} onClick={closeMenu}>{label}</Link>)}
        <Link className="mobile-nav-action" to="/contacto" onClick={closeMenu}>Falar connosco</Link>
        <Link className="mobile-nav-action" to="/clinica-piloto" onClick={closeMenu}>Quero ser clínica piloto</Link>
      </div>
      <div className="nav-actions">
        <Link className="btn btn-ghost nav-contact" to="/contacto" onClick={closeMenu}>Falar connosco</Link>
        <Link className="btn btn-primary nav-pilot" to="/clinica-piloto" onClick={closeMenu}>Quero ser clínica piloto <ArrowRight size={15} /></Link>
        <button className="menu-btn" onClick={() => setOpen(!open)} aria-label={open ? "Fechar menu" : "Abrir menu"} aria-expanded={open}>
          {open ? <X size={21} /> : <Menu size={21} />}
        </button>
      </div>
    </div>
  </nav>;
}

export function SiteFooter() {
  return <footer><div className="container footer-inner">
    <div><Link to="/" className="footer-brand"><img src={logo} alt="" className="brand-logo" /><strong>MyVita</strong></Link><p>Marcações. Resultados. Mensagens. Sem telefonemas.</p></div>
    <div className="footer-links">{siteLinks.map(([label, path]) => <Link key={path} to={path}>{label}</Link>)}<Link to="/contacto">Contacto</Link></div>
    <small>© 2026 MyVita · Protótipo em fase de validação.</small>
  </div></footer>;
}

export function SiteLayout({ children }) {
  return <><SiteNavbar /><main className="site-page-content">{children}</main><SiteFooter /></>;
}
