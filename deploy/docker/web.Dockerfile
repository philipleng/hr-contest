FROM node:22-alpine AS h5-build
WORKDIR /src
ARG VITE_FB_PAGE_USERNAME=
ENV VITE_FB_PAGE_USERNAME=$VITE_FB_PAGE_USERNAME
COPY h5/package.json h5/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY h5/ ./
RUN npm run build

FROM node:22-alpine AS admin-build
WORKDIR /src
ARG VITE_OSS_DOMAIN=
ENV VITE_OSS_DOMAIN=$VITE_OSS_DOMAIN
COPY admin/package.json admin/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY admin/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/nginx.docker.conf /etc/nginx/conf.d/default.conf
COPY --from=h5-build /src/dist /usr/share/nginx/html
COPY --from=admin-build /src/dist /usr/share/nginx/html/admin

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
