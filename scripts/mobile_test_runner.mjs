import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium, devices } = require('../frontend/node_modules/@playwright/test');
import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

const SCREENSHOTS_DIR = '/Users/paulopotapov/.gemini/antigravity/brain/65042991-decd-49cb-823d-c8f54b7264db/mobile_screenshots';
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const BASE_URL = 'http://localhost:5173';

function getUserTotp(email) {
  try {
    const cmd = `docker compose exec -T backend python3 -c "
from app.core.database import SessionLocal
from app.models.user import User
from app.models.account_security import UserMfa
from app.core.mfa import decrypt_secret, totp
with SessionLocal() as db:
    u = db.query(User).filter(User.email == '${email}').first()
    if u:
        m = db.query(UserMfa).filter(UserMfa.user_id == u.id).first()
        if m and m.secret_ciphertext:
            print(totp(decrypt_secret(m.secret_ciphertext, u.id)))
"`;
    const res = execSync(cmd, { cwd: '/Users/paulopotapov/myvita-integration', encoding: 'utf-8' }).trim();
    return res || null;
  } catch (e) {
    return null;
  }
}

const auditLog = {
  testedAt: new Date().toISOString(),
  runs: [],
  findings: [],
  performance: []
};

function addFinding({ id, area, checklistItem, page, action, device, orientation, network, issue, severity, screenshot }) {
  const existing = auditLog.findings.find(f => f.issue === issue && f.device === device && f.orientation === orientation);
  if (existing) return;

  const item = {
    id,
    area,
    checklistItem,
    page,
    action,
    device,
    orientation,
    network,
    issue,
    severity,
    screenshot
  };
  auditLog.findings.push(item);
  console.log(`[FINDING][${severity}] ${area} | ${device} ${orientation} | ${page}: ${issue}`);
}

async function checkOverflow(page, label, ctx, checklistItem) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    const scrollWidth = Math.max(doc.scrollWidth, body.scrollWidth);
    const clientWidth = doc.clientWidth;
    const diff = scrollWidth - clientWidth;
    
    const overflowingElements = [];
    const elements = document.querySelectorAll('*');
    for (const el of elements) {
      const rect = el.getBoundingClientRect();
      if (rect.right > clientWidth + 3) {
        overflowingElements.push({
          tag: el.tagName.toLowerCase(),
          id: el.id || undefined,
          className: el.className ? String(el.className).slice(0, 60) : undefined,
          text: (el.textContent || '').trim().slice(0, 30),
          width: Math.round(rect.width),
          right: Math.round(rect.right)
        });
      }
    }
    return {
      scrollWidth,
      clientWidth,
      diff,
      hasOverflow: diff > 2,
      overflowingElements: overflowingElements.slice(0, 4)
    };
  });

  if (overflow.hasOverflow) {
    const shotName = `overflow_${ctx.device.replace(/\s+/g, '_')}_${ctx.orientation}_${label.replace(/[^a-zA-Z0-9]/g, '_')}.png`;
    const shotPath = path.join(SCREENSHOTS_DIR, shotName);
    await page.screenshot({ path: shotPath, fullPage: true });

    addFinding({
      id: `OF-${ctx.device}-${label}`,
      area: ctx.area,
      checklistItem,
      page: label,
      action: 'Renderizar página',
      device: ctx.device,
      orientation: ctx.orientation,
      network: ctx.network,
      issue: `Overflow horizontal de ${overflow.diff}px (largura total ${overflow.scrollWidth}px vs ecrã ${overflow.clientWidth}px). Elementos salientes: ${JSON.stringify(overflow.overflowingElements)}`,
      severity: overflow.diff > 15 ? 'HIGH' : 'MEDIUM',
      screenshot: shotName
    });
  }
  return overflow;
}

async function checkTouchTargets(page, label, ctx, checklistItem) {
  const smallTargets = await page.evaluate(() => {
    const clickable = Array.from(document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="tab"]'));
    const issues = [];
    for (const el of clickable) {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
      if (rect.width === 0 || rect.height === 0) continue;
      if (rect.width < 36 || rect.height < 36) {
        issues.push({
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute('role') || undefined,
          text: (el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || el.value || '').trim().slice(0, 25),
          w: Math.round(rect.width),
          h: Math.round(rect.height)
        });
      }
    }
    return issues.slice(0, 8);
  });

  if (smallTargets.length > 0) {
    addFinding({
      id: `TT-${ctx.device}-${label}`,
      area: ctx.area,
      checklistItem,
      page: label,
      action: 'Avaliação de alvos táteis (Touch Targets)',
      device: ctx.device,
      orientation: ctx.orientation,
      network: ctx.network,
      issue: `Botões/links táteis inferiores a 36px (recomendado mínimo 44x44px para mobile): ${JSON.stringify(smallTargets)}`,
      severity: 'LOW',
      screenshot: null
    });
  }
}

async function runDeviceAudit(deviceName, deviceConfig, orientation, networkType) {
  console.log(`\n======================================================`);
  console.log(`AUDIT: ${deviceName} | ${orientation.toUpperCase()} | NET: ${networkType}`);
  console.log(`======================================================`);

  const browser = await chromium.launch({ headless: true });
  
  let viewport = { ...deviceConfig.viewport };
  if (orientation === 'landscape') {
    viewport = {
      width: Math.max(deviceConfig.viewport.width, deviceConfig.viewport.height),
      height: Math.min(deviceConfig.viewport.width, deviceConfig.viewport.height)
    };
  } else {
    viewport = {
      width: Math.min(deviceConfig.viewport.width, deviceConfig.viewport.height),
      height: Math.max(deviceConfig.viewport.width, deviceConfig.viewport.height)
    };
  }

  const context = await browser.newContext({
    ...deviceConfig,
    viewport,
    screen: viewport,
    baseURL: BASE_URL,
    locale: 'pt-PT',
    timezoneId: 'Europe/Lisbon'
  });

  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);

  if (networkType === 'slow_network') {
    await cdp.send('Network.emulateNetworkConditions', {
      offline: false,
      latency: 250, // 250ms RTT
      downloadThroughput: 1.5 * 1024 * 1024 / 8, // ~190 KB/s (3G+/4G congestionada)
      uploadThroughput: 750 * 1024 / 8
    });
  }

  const prefix = `${deviceName.toLowerCase().replace(/[^a-z0-9]/g, '_')}_${orientation}_${networkType}`;
  const ctx = { device: deviceName, orientation, network: networkType, area: 'AUTENTICAÇÃO' };

  try {
    // -----------------------------------------------------------------
    // 1. AUTENTICAÇÃO
    // -----------------------------------------------------------------
    ctx.area = 'AUTENTICAÇÃO';
    console.log(`[1.1] Login (campos, keyboard, validação)`);
    await context.clearCookies();
    const t0 = Date.now();
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    const loadTimeLogin = Date.now() - t0;
    auditLog.performance.push({ page: '/login', device: deviceName, orientation, network: networkType, durationMs: loadTimeLogin });

    const shotLogin = `${prefix}_01_login.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotLogin), fullPage: true });

    await checkOverflow(page, '/login', ctx, 'login');
    await checkTouchTargets(page, '/login', ctx, 'login');

    // Validation check
    const submitBtn = page.locator('button[type="submit"]');
    await submitBtn.click();
    await page.waitForTimeout(400);
    const shotVal = `${prefix}_02_login_validacao.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotVal), fullPage: true });

    // Landscape vertical fit
    if (orientation === 'landscape') {
      const formBox = await page.locator('form').boundingBox();
      if (formBox && formBox.height > viewport.height - 40) {
        addFinding({
          id: `LANDSCAPE-LOGIN-${deviceName}`,
          area: 'AUTENTICAÇÃO',
          checklistItem: 'login',
          page: '/login',
          action: 'Visualização landscape',
          device: deviceName,
          orientation,
          network: networkType,
          issue: `Em landscape (${viewport.height}px altura), o formulário de login requer scroll vertical acentuado, botão "Entrar" fica cortado sem scroll.`,
          severity: 'MEDIUM',
          screenshot: shotLogin
        });
      }
    }

    // [1.2] MFA Challenge
    console.log(`[1.2] MFA (verificação com código TOTP)`);
    await page.fill('input[type="email"]', 'doctor@myvita.pt');
    await page.fill('input[type="password"]', 'SenhaForte123!');
    await submitBtn.click();
    await page.waitForTimeout(1000);

    const mfaVerifyH1 = await page.getByRole('heading', { name: 'Verificação em dois passos' }).isVisible().catch(() => false);
    if (mfaVerifyH1) {
      const shotVerify = `${prefix}_03_mfa_challenge.png`;
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotVerify), fullPage: true });
      await checkOverflow(page, '/login (mfa)', ctx, 'mfa');

      const codeInput = page.locator('input[autocomplete="one-time-code"], input[inputmode="numeric"]');
      const inputMode = await codeInput.getAttribute('inputmode').catch(() => null);
      if (inputMode !== 'numeric') {
        addFinding({
          id: `MFA-INPUTMODE-${deviceName}`,
          area: 'AUTENTICAÇÃO',
          checklistItem: 'mfa',
          page: '/login (MFA)',
          action: 'Inserção de código 2FA',
          device: deviceName,
          orientation,
          network: networkType,
          issue: 'Campo de código 2FA sem inputmode="numeric", dificultando a entrada de dígitos no teclado móvel.',
          severity: 'LOW',
          screenshot: shotVerify
        });
      }

      // Enter valid TOTP
      const totpVal = getUserTotp('doctor@myvita.pt');
      if (totpVal) {
        await codeInput.fill(totpVal);
        await page.click('button[type="submit"]');
        await page.waitForTimeout(1500);
      }
    }

    // [1.3] Logout
    console.log(`[1.3] Logout`);
    const header = page.locator('header');
    const logoutBtn = header.getByRole('button', { name: /Sair/i });
    if (await logoutBtn.isVisible()) {
      const box = await logoutBtn.boundingBox();
      if (box && (box.width < 44 || box.height < 44)) {
        addFinding({
          id: `LOGOUT-TOUCH-TARGET-${deviceName}`,
          area: 'AUTENTICAÇÃO',
          checklistItem: 'logout',
          page: 'Header (Layout autenticado)',
          action: 'Toque no botão Sair',
          device: deviceName,
          orientation,
          network: networkType,
          issue: `Botão "Sair" tem dimensão tátil de ${Math.round(box.width)}x${Math.round(box.height)}px, abaixo do padrão mobile WCAG de 44x44px.`,
          severity: 'LOW',
          screenshot: null
        });
      }
      await logoutBtn.click();
      await page.waitForTimeout(1000);
    }

    // -----------------------------------------------------------------
    // 2. PACIENTE AREA AUDIT
    // -----------------------------------------------------------------
    ctx.area = 'PACIENTE';
    console.log(`[2.1] Paciente Login & Dashboard`);
    await context.clearCookies();
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await page.fill('input[type="email"]', 'paciente@myvita.pt');
    await page.fill('input[type="password"]', 'SenhaForte123!');
    const tPatLogin = Date.now();
    await page.click('button[type="submit"]');
    await page.waitForURL('**/patient', { timeout: 15000 });
    const durPatLogin = Date.now() - tPatLogin;
    auditLog.performance.push({ page: '/patient (login)', device: deviceName, orientation, network: networkType, durationMs: durPatLogin });

    const shotPatDash = `${prefix}_06_paciente_dashboard.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotPatDash), fullPage: true });
    await checkOverflow(page, '/patient', ctx, 'dashboard');
    await checkTouchTargets(page, '/patient', ctx, 'dashboard');

    // [2.2] Consultas (Pedir marcação & Ver marcações)
    console.log(`[2.2] Paciente Consultas`);
    const tCons = Date.now();
    await page.goto('/patient/consultas', { waitUntil: 'domcontentloaded' });
    auditLog.performance.push({ page: '/patient/consultas', device: deviceName, orientation, network: networkType, durationMs: Date.now() - tCons });

    const shotPatConsultas = `${prefix}_07_paciente_consultas.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotPatConsultas), fullPage: true });
    await checkOverflow(page, '/patient/consultas', ctx, 'ver_marcacoes');

    // Form Pedir marcação
    const reqForm = page.locator('form:has(input[type="datetime-local"])');
    if (await reqForm.isVisible()) {
      const dtInput = reqForm.locator('input[type="datetime-local"]');
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 4);
      tomorrow.setHours(10, 30, 0, 0);
      await dtInput.fill(tomorrow.toISOString().slice(0, 16));

      const reasonInput = reqForm.locator('label:has-text("Motivo") input, input:not([type="datetime-local"])').first();
      if (await reasonInput.isVisible().catch(() => false)) {
        await reasonInput.fill('Consulta de rotina teste piloto');
      }

      const shotReqForm = `${prefix}_08_paciente_pedir_marcacao_form.png`;
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotReqForm), fullPage: true });

      const subBtn = reqForm.getByRole('button', { name: /Enviar pedido|Pedir marcação/i });
      if (await subBtn.isVisible().catch(() => false)) {
        await subBtn.click();
        await page.waitForTimeout(1000);
      }
    }

    // Appointment Details Dialog
    const detBtn = page.getByRole('button', { name: 'Detalhes' }).first();
    if (await detBtn.isVisible()) {
      await detBtn.click();
      await page.waitForTimeout(600);
      const dialog = page.getByRole('dialog');
      if (await dialog.isVisible()) {
        const shotDialog = `${prefix}_09_paciente_consulta_detalhes.png`;
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotDialog), fullPage: true });

        const dBox = await dialog.boundingBox();
        if (dBox && dBox.height > viewport.height - 20) {
          addFinding({
            id: `DIALOG-OVERFLOW-PATIENT-${deviceName}-${orientation}`,
            area: 'PACIENTE',
            checklistItem: 'ver_marcacoes',
            page: '/patient/consultas (Modal Detalhes)',
            action: 'Abertura do detalhe da consulta',
            device: deviceName,
            orientation,
            network: networkType,
            issue: `Modal de detalhes da consulta (${Math.round(dBox.height)}px altura) ultrapassa a altura útil do ecrã (${viewport.height}px) em ${orientation}, obrigando a scroll para alcançar botões de fechar.`,
            severity: orientation === 'landscape' ? 'HIGH' : 'MEDIUM',
            screenshot: shotDialog
          });
        }
        await page.getByRole('button', { name: /Fechar/i }).click();
        await page.waitForTimeout(400);
      }
    }

    // [2.3] Documentos
    console.log(`[2.3] Paciente Documentos`);
    await page.goto('/patient/documentos', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotPatDocs = `${prefix}_10_paciente_documentos.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotPatDocs), fullPage: true });
    await checkOverflow(page, '/patient/documentos', ctx, 'documentos');

    // [2.4] Mensagens
    console.log(`[2.4] Paciente Mensagens`);
    await page.goto('/patient/mensagens', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotPatMsgInbox = `${prefix}_11_paciente_mensagens_inbox.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotPatMsgInbox), fullPage: true });
    await checkOverflow(page, '/patient/mensagens', ctx, 'mensagens');

    // Open chat thread
    const openThreadLink = page.locator('ol a, ul a, section a').filter({ hasText: /Dr\. António Silva|Conversa/i }).first();
    if (await openThreadLink.isVisible()) {
      await openThreadLink.click();
      await page.waitForTimeout(1000);

      const shotPatThread = `${prefix}_12_paciente_mensagens_conversa.png`;
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotPatThread), fullPage: true });
      await checkOverflow(page, '/patient/mensagens/:id', ctx, 'mensagens');

      // Send message
      const composerArea = page.locator('#message-body');
      if (await composerArea.isVisible()) {
        await composerArea.fill(`Teste mobile paciente (${deviceName} ${orientation})`);
        await page.getByRole('button', { name: 'Enviar' }).click();
        await page.waitForTimeout(1000);

        const shotPatMsgSent = `${prefix}_13_paciente_mensagem_enviada.png`;
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotPatMsgSent), fullPage: true });
      }
    }

    // [2.5] Notificações
    console.log(`[2.5] Paciente Notificações`);
    await page.goto('/patient/notificacoes', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotPatNotif = `${prefix}_14_paciente_notificacoes.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotPatNotif), fullPage: true });
    await checkOverflow(page, '/patient/notificacoes', ctx, 'notificacoes');

    const nLinks = await page.locator('section li a').all();
    if (nLinks.length > 0) {
      await nLinks[0].click();
      await page.waitForTimeout(1000);
      const shotDeepLink = `${prefix}_15_paciente_notificacao_clicada.png`;
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotDeepLink), fullPage: true });
    }

    // [2.6] Perfil
    console.log(`[2.6] Paciente Perfil`);
    await page.goto('/patient/perfil', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotPatPerfil = `${prefix}_16_paciente_perfil.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotPatPerfil), fullPage: true });
    await checkOverflow(page, '/patient/perfil', ctx, 'perfil');

    // -----------------------------------------------------------------
    // 3. CLÍNICA AREA AUDIT (DOCTOR & ADMIN)
    // -----------------------------------------------------------------
    ctx.area = 'CLÍNICA';
    console.log(`[3.1] Login Doctor & Dashboard Clínica`);
    await context.clearCookies();
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await page.fill('input[type="email"]', 'doctor@myvita.pt');
    await page.fill('input[type="password"]', 'SenhaForte123!');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(1000);

    const docTotp = getUserTotp('doctor@myvita.pt');
    const mfaPrompt = page.locator('input[autocomplete="one-time-code"], input[inputmode="numeric"]');
    if (await mfaPrompt.isVisible().catch(() => false)) {
      if (docTotp) {
        await mfaPrompt.fill(docTotp);
        await page.click('button[type="submit"]');
        await page.waitForTimeout(1500);
      }
    }

    // [3.1] Clinic Dashboard
    await page.goto('/app', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotClinicaDash = `${prefix}_17_clinica_dashboard.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotClinicaDash), fullPage: true });
    await checkOverflow(page, '/app', ctx, 'dashboard');

    // [3.2] Pacientes (Search, Filter, Table on Mobile)
    console.log(`[3.2] Clínica Pacientes`);
    await page.goto('/app/pacientes', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotClinicaPacientes = `${prefix}_18_clinica_pacientes.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotClinicaPacientes), fullPage: true });
    await checkOverflow(page, '/app/pacientes', ctx, 'pacientes');

    // Search input
    const searchField = page.getByRole('searchbox', { name: 'Pesquisar por nome' });
    if (await searchField.isVisible()) {
      await searchField.fill('Maria');
      await page.waitForTimeout(600);
      const shotSearch = `${prefix}_19_clinica_pacientes_busca.png`;
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotSearch), fullPage: true });
    }

    // Open Patient Ficha
    const fichaLink = page.getByRole('link', { name: 'Abrir ficha' }).first();
    let patientDetailUrl = '';
    if (await fichaLink.isVisible()) {
      await fichaLink.click();
      await page.waitForTimeout(1000);
      patientDetailUrl = page.url();

      const shotFicha = `${prefix}_20_clinica_paciente_ficha_tabs.png`;
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotFicha), fullPage: true });
      await checkOverflow(page, '/app/pacientes/:id', ctx, 'pacientes');

      // Check Tabs wrap on small screens
      const tabsNav = page.locator('nav[role="tablist"]');
      const tabsBox = await tabsNav.boundingBox();
      if (tabsBox && tabsBox.height > 65) {
        addFinding({
          id: `TABS-MULTIROW-${deviceName}`,
          area: 'CLÍNICA',
          checklistItem: 'pacientes',
          page: '/app/pacientes/:id (Ficha do Paciente)',
          action: 'Renderização dos separadores/tabs da ficha',
          device: deviceName,
          orientation,
          network: networkType,
          issue: `Separadores da ficha clínica partem em múltiplas linhas (${Math.round(tabsBox.height)}px de altura) em mobile, empurrando os dados clínicos para baixo.`,
          severity: 'MEDIUM',
          screenshot: shotFicha
        });
      }

      // Test switching to Documentos tab
      const docTab = page.getByRole('tab', { name: 'Documentos' });
      if (await docTab.isVisible()) {
        await docTab.click();
        await page.waitForTimeout(500);
        const shotFichaDoc = `${prefix}_20b_clinica_paciente_tab_documentos.png`;
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotFichaDoc), fullPage: true });
      }
    }

    // [3.3] Consultas & Aceitar Pedidos
    console.log(`[3.3] Clínica Consultas`);
    await page.goto('/app/consultas', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotClinicaAppts = `${prefix}_21_clinica_consultas.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotClinicaAppts), fullPage: true });
    await checkOverflow(page, '/app/consultas', ctx, 'marcacoes');

    // Click Aceitar pedido
    const acceptBtn = page.getByRole('button', { name: /Aceitar/i }).first();
    if (await acceptBtn.isVisible().catch(() => false)) {
      await acceptBtn.click();
      await page.waitForTimeout(600);
      const shotAccept = `${prefix}_22_clinica_aceitar_pedido_form.png`;
      await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotAccept), fullPage: true });

      const acceptForm = page.locator('form[aria-label*="Marcar consulta"]');
      if (await acceptForm.isVisible().catch(() => false)) {
        const fBox = await acceptForm.boundingBox();
        console.log(`Accept request inline form box: width=${fBox?.width}px, height=${fBox?.height}px`);
      }
    }

    // [3.4] Mensagens Clínica
    console.log(`[3.4] Clínica Mensagens`);
    await page.goto('/app/mensagens', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotClinicaMsg = `${prefix}_23_clinica_mensagens.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotClinicaMsg), fullPage: true });
    await checkOverflow(page, '/app/mensagens', ctx, 'mensagens');

    // [3.5] Contas & Audit Log (via Admin)
    console.log(`[3.5] Contas & Audit Log`);
    await context.clearCookies();
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await page.fill('input[type="email"]', 'admin@myvita.pt');
    await page.fill('input[type="password"]', 'SenhaForte123!');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(1000);

    const adminTotp = getUserTotp('admin@myvita.pt');
    const adminMfaInput = page.locator('input[autocomplete="one-time-code"], input[inputmode="numeric"]');
    if (await adminMfaInput.isVisible().catch(() => false)) {
      if (adminTotp) {
        await adminMfaInput.fill(adminTotp);
        await page.click('button[type="submit"]');
        await page.waitForTimeout(1500);
      }
    }

    await page.goto('/app/contas', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(800);
    const shotClinicaContas = `${prefix}_24_clinica_contas_audit.png`;
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, shotClinicaContas), fullPage: true });
    await checkOverflow(page, '/app/contas', ctx, 'audit_log');

  } catch (err) {
    console.error(`Audit run error on ${deviceName} ${orientation}:`, err);
    addFinding({
      id: `CRASH-${deviceName}-${orientation}`,
      area: ctx.area,
      checklistItem: 'crashes',
      page: page.url(),
      action: 'Execução do teste',
      device: deviceName,
      orientation,
      network: networkType,
      issue: `Exceção não tratada durante teste: ${err.message}`,
      severity: 'CRITICAL',
      screenshot: null
    });
  } finally {
    await browser.close();
  }
}

async function main() {
  console.log('=== INICIANDO AUDITORIA MOBILE COMPLETA - MYVITA PILOT ===');

  const configs = [
    { name: 'iPhone 14', config: devices['iPhone 14'], orientations: ['portrait', 'landscape'], networks: ['normal', 'slow_network'] },
    { name: 'Android 13', config: devices['Pixel 7'], orientations: ['portrait', 'landscape'], networks: ['normal', 'slow_network'] }
  ];

  for (const item of configs) {
    for (const orient of item.orientations) {
      for (const net of item.networks) {
        await runDeviceAudit(item.name, item.config, orient, net);
      }
    }
  }

  const outJson = path.join(SCREENSHOTS_DIR, 'mobile_audit_results.json');
  fs.writeFileSync(outJson, JSON.stringify(auditLog, null, 2));
  console.log(`\nAuditoria concluída com sucesso! Resultados em ${outJson}`);
  console.log(`Total de problemas identificados: ${auditLog.findings.length}`);
}

main().catch(console.error);
