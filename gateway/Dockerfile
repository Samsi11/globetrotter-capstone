FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY templates/index.html /usr/share/nginx/html/index.html
COPY static /usr/share/nginx/html/static
EXPOSE 80
