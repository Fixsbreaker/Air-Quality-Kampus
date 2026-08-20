FROM node:20-alpine AS build

WORKDIR /app

# Базовый путь приложения. На сервере КБТУ проект отдаётся по пути вида
# /air-quality/, локально — с корня. Значение попадает и в ссылки на статику,
# и в адрес API, поэтому префикс задаётся ровно одной переменной.
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=$VITE_BASE_PATH

# Переопределение адреса API. Обычно не нужно: по умолчанию запросы уходят
# относительно базового пути, а nginx проксирует их в backend. Задаётся только
# когда фронтенд обращается к API напрямую, минуя прокси.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
