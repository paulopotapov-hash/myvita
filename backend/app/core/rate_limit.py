"""
Rate limiting for public, unauthenticated write endpoints.

Nothing in this codebase throttled brute-force login attempts or endpoint
abuse (account enumeration via registration, mass clinic/staff creation)
before this. We key by client IP: these endpoints (login, patient
self-registration, clinic onboarding) have no session yet, so IP is the
only identity available.

In-memory storage is fine for the current single-process deployment. If/when
myVita runs multiple backend replicas, point `storage_uri` at Redis so all
replicas share the same counters — see slowapi/limits docs. That's a
deployment-time config change, not a code change.
"""
from slowapi import Limiter

from app.core.client_ip import get_client_ip

# NOT slowapi's default get_remote_address: that reads request.client.host
# directly, which — behind the reverse proxy docker-compose.prod.yml
# assumes — would be the proxy's own IP on every single request, collapsing
# rate limiting into one shared bucket for every real user. get_client_ip
# only trusts X-Forwarded-For from configured TRUSTED_PROXIES (see
# app/core/client_ip.py), so this stays correct with or without a proxy.
limiter = Limiter(key_func=get_client_ip)

# Deliberately generous enough not to bother a real user who mistypes a
# password a couple of times, tight enough to make credential-stuffing /
# brute force and registration-spam scripts impractical.
LOGIN_RATE_LIMIT = "10/minute"
REGISTRATION_RATE_LIMIT = "5/minute"

# Looser limit for authenticated admin actions (e.g. staff creation): the
# caller already proved who they are, so this is about capping the blast
# radius of a compromised/malicious admin session, not brute force.
AUTHENTICATED_WRITE_RATE_LIMIT = "20/minute"
