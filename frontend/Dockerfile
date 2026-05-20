# syntax=docker/dockerfile:1

ARG NODE_VERSION=20
ARG NGINX_VERSION=1.27-alpine
ARG VITE_AMAP_JS_KEY=
ARG VITE_AMAP_SECURITY_JS_CODE=

FROM node:${NODE_VERSION}-alpine AS builder

WORKDIR /app

ARG VITE_AMAP_JS_KEY
ARG VITE_AMAP_SECURITY_JS_CODE
ENV VITE_AMAP_JS_KEY=${VITE_AMAP_JS_KEY} \
    VITE_AMAP_SECURITY_JS_CODE=${VITE_AMAP_SECURITY_JS_CODE}

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:${NGINX_VERSION} AS runtime

ENV BACKEND_ORIGIN=http://127.0.0.1:6688 \
    BACKEND_HOST=127.0.0.1:6688

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD sh -c "wget --no-check-certificate -qO- https://127.0.0.1/ >/dev/null || exit 1"
