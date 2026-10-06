# Development image: runs Vite's own dev server (HMR, fast rebuilds).
# See README.md#production for why this is NOT what production should run
# (a dev server is not a production web server) — the recommended
# production approach is documented there instead of implemented here, to
# avoid adding a second, untested build pipeline (nginx config, multi-stage
# build) before the app itself has had a real production deployment.
FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host: without this, Vite only binds to localhost inside the container,
# unreachable from the host even with the port published.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
