#!/bin/sh
sed "s|__MINECRAFT_DOMAIN__|$MINECRAFT_DOMAIN|g" /templates/index.html > /usr/share/nginx/html/index.html
exec nginx -g 'daemon off;'
