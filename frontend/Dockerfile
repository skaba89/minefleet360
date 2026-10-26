# Interface web MINEFLEET 360 : build Vite puis service statique par Caddy (non root, port 8080).
FROM node:22.23.4-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2.11.6-alpine AS runtime
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
# Aucun état à conserver : admin désactivée, données Caddy en mémoire/tmp.
ENV XDG_DATA_HOME=/tmp XDG_CONFIG_HOME=/tmp
USER nobody
EXPOSE 8080
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
