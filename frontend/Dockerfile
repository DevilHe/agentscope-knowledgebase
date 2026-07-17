FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_PASSWORD_ENCRYPT_KEY
ARG VITE_REGISTRATION_ENABLED=false
ARG VITE_ICP_BEIAN=
ENV VITE_PASSWORD_ENCRYPT_KEY=$VITE_PASSWORD_ENCRYPT_KEY
ENV VITE_REGISTRATION_ENABLED=$VITE_REGISTRATION_ENABLED
ENV VITE_ICP_BEIAN=$VITE_ICP_BEIAN
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

FROM nginx:alpine
RUN apk add --no-cache gettext
COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80 443
ENTRYPOINT ["/docker-entrypoint.sh"]
