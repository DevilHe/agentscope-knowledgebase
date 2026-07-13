#!/bin/sh
set -e

export DOMAIN_NAME="${DOMAIN_NAME:-localhost}"

TEMPLATE="/etc/nginx/templates/nginx.conf.template"

if [ -f "/etc/letsencrypt/live/${DOMAIN_NAME}/fullchain.pem" ]; then
    MARK_BEGIN="#MARK:HTTP_SSL"
    MARK_END="#END:HTTP_SSL"
else
    MARK_BEGIN="#MARK:HTTP_NO_SSL"
    MARK_END="#END:HTTP_NO_SSL"
fi

awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
    $0 == begin { printit=1; next }
    $0 == end   { printit=0; next }
    printit
' "$TEMPLATE" | envsubst '${DOMAIN_NAME}' > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
