// External staging acceptance check using only synthetic seed identities (backend/scripts/seed_staging.py).
// BASE_URL=https://staging.example SEED_PASSWORD=... node scripts/staging_acceptance.mjs
const base = (process.env.BASE_URL ?? '').replace(/\/$/, '')
const password = process.env.SEED_PASSWORD
const domain = process.env.EMAIL_DOMAIN ?? 'staging.example'
if (!base || !password) {
  console.error('BASE_URL and SEED_PASSWORD are required')
  process.exit(2)
}

const results = []
const runId = Date.now().toString(36)
const slot = new Date(Date.UTC(2041, 0, 1) + (Date.now() % 86_400_000) * 60_000).toISOString()
const check = (name, ok, detail = '') => {
  results.push(ok)
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : `  -> ${detail}`}`)
}

class Session {
  jar = new Map()
  async request(method, path, body, { csrf = true, headers = {} } = {}) {
    const sent = { cookie: [...this.jar].map(([k, v]) => `${k}=${v}`).join('; '), ...headers }
    if (body !== undefined) sent['content-type'] = 'application/json'
    if (csrf && method !== 'GET' && this.jar.has('myvita_csrf')) sent['x-csrf-token'] = this.jar.get('myvita_csrf')
    const response = await fetch(base + path, { method, headers: sent, body: body === undefined ? undefined : JSON.stringify(body), redirect: 'manual' })
    this.lastSetCookie = response.headers.getSetCookie()
    for (const line of this.lastSetCookie) {
      const [pair] = line.split(';')
      const index = pair.indexOf('=')
      const [name, value] = [pair.slice(0, index), pair.slice(index + 1)]
      if (/max-age=0/i.test(line) || value === '') this.jar.delete(name)
      else this.jar.set(name, value)
    }
    const text = await response.text()
    let json = null
    try { json = JSON.parse(text) } catch { /* non-JSON body */ }
    return { status: response.status, json, text, headers: response.headers }
  }
  async login(email) {
    const response = await this.request('POST', '/api/v1/auth/login', { email, password }, { csrf: false })
    return response
  }
}

const who = async (name) => {
  const session = new Session()
  const response = await session.login(`${name}@${domain}`)
  check(`login ${name}`, response.status === 200, `${response.status} ${response.text.slice(0, 80)}`)
  session.loginCookies = session.lastSetCookie
  session.me = (await session.request('GET', '/api/v1/auth/me')).json
  return session
}

const home = await fetch(base + '/')
check('frontend served over the target origin', home.status === 200 && (home.headers.get('content-type') ?? '').includes('text/html'))
const refresh = await fetch(base + '/app/consultas')
check('SPA deep link refresh', refresh.status === 200 && (refresh.headers.get('content-type') ?? '').includes('text/html'))
check('API schema not exposed', !((await fetch(base + '/openapi.json')).headers.get('content-type') ?? '').includes('json'))
check('/health', (await fetch(base + '/health')).status === 200)
check('/ready', (await fetch(base + '/ready')).status === 200)
if (base.startsWith('https://')) {
  const plain = await fetch(base.replace('https://', 'http://') + '/', { redirect: 'manual' })
  check('HTTP redirects to HTTPS', [301, 302, 307, 308].includes(plain.status), String(plain.status))
}

const adminA = await who('admin-a')
const doctorA = await who('doctor-a')
const nurseA = await who('nurse-a')
const patientA = await who('patient-a')
const adminB = await who('admin-b')
const doctorB = await who('doctor-b')
const patientB = await who('patient-b')

const cookieLines = doctorA.loginCookies
const sessionCookie = cookieLines.find((line) => line.startsWith('myvita_session='))
if (base.startsWith('https://')) check('session cookie is Secure + HttpOnly', /;\s*secure/i.test(sessionCookie ?? '') && /;\s*httponly/i.test(sessionCookie ?? ''))
else check('session cookie is HttpOnly', /;\s*httponly/i.test(sessionCookie ?? ''))
check('CSRF cookie issued and not HttpOnly', cookieLines.some((l) => l.startsWith('myvita_csrf=') && !/httponly/i.test(l)))

check('identity roles', adminA.me.role === 'clinic_admin' && doctorA.me.role === 'staff' && patientA.me.role === 'patient')
check('tenant ids differ', adminA.me.clinic_id !== adminB.me.clinic_id)

const staffList = (await doctorA.request('GET', '/api/v1/staff')).json
const doctorStaff = staffList.find((s) => s.full_name.startsWith('Doctor A'))
const appointment = await doctorA.request('POST', '/api/v1/appointments', {
  patient_id: patientA.me.patient_id, staff_id: doctorStaff.id, scheduled_at: slot, reason: 'staging check',
})
check('doctor creates appointment', appointment.status === 201, appointment.text.slice(0, 120))
const noCsrf = await doctorA.request('POST', '/api/v1/appointments', {}, { csrf: false })
check('missing CSRF token rejected', noCsrf.status === 403, String(noCsrf.status))
const record = await doctorA.request('POST', `/api/v1/patients/${patientA.me.patient_id}/medical-records`, { title: 'Synthetic', content: 'synthetic staging content' })
check('doctor creates medical record', record.status === 201, record.text.slice(0, 120))
const medication = await nurseA.request('POST', `/api/v1/patients/${patientA.me.patient_id}/medications`, { name: 'Synthetol', dosage: '5 mg', start_date: '2041-02-01' })
check('nurse creates medication', medication.status === 201, medication.text.slice(0, 120))
const consent = await patientA.request('POST', `/api/v1/patients/${patientA.me.patient_id}/consents`, { consent_type: 'treatment', purpose: `staging check ${runId}` })
check('patient grants consent', consent.status === 201, consent.text.slice(0, 120))
const myAppointments = (await patientA.request('GET', '/api/v1/appointments')).json
check('patient sees own appointment', myAppointments.some((a) => a.id === appointment.json.id))
const notifications = (await patientA.request('GET', '/api/v1/notifications')).json
check('patient has notifications', notifications.length > 0)
if (notifications.length) check('patient marks notification read', (await patientA.request('POST', `/api/v1/notifications/${notifications[0].id}/read`)).status === 200)

check('patient cannot list patients', (await patientA.request('GET', '/api/v1/patients')).status === 403)
check('nurse cannot create staff', (await nurseA.request('POST', '/api/v1/staff', {})).status === 403)
check('A cannot read B patient', (await doctorA.request('GET', `/api/v1/patients/${patientB.me.patient_id}`)).status === 404)
check('A cannot read B record list', (await doctorA.request('GET', `/api/v1/patients/${patientB.me.patient_id}/medical-records`)).status === 404)
check('B cannot read A record', (await doctorB.request('GET', `/api/v1/medical-records/${record.json.id}`)).status === 404)
check('B cannot read A appointment', (await adminB.request('GET', `/api/v1/appointments/${appointment.json.id}`)).status === 404)
check('patient A cannot read patient B', (await patientA.request('GET', `/api/v1/patients/${patientB.me.patient_id}`)).status === 404)

// Logout bumps token_epoch, so every earlier session of this user must die too.
const staleCookies = new Map(patientA.jar)
check('logout succeeds', (await patientA.request('POST', '/api/v1/auth/logout')).status === 204)
const replay = new Session()
replay.jar = staleCookies
check('old session rejected after logout', (await replay.request('GET', '/api/v1/auth/me')).status === 401)

const bad = await new Session().request('POST', '/api/v1/auth/login', { email: `doctor-a@${domain}`, password: `${password}x` }, { csrf: false })
check('wrong password rejected without detail', bad.status === 401 && !/traceback|sql/i.test(bad.text), String(bad.status))

const failed = results.filter((ok) => !ok).length
console.log(`\n${results.length - failed}/${results.length} checks passed`)
process.exit(failed ? 1 : 0)
