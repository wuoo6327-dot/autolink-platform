FROM python:3.12.15-alpine3.24@sha256:2055081c860db8c842b663415b795b026e7e5cc63b59c5193fcc9997713ea5b8 AS dependencies
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN apk add --no-cache zlib=1.3.2-r1 \
    && pip install --no-cache-dir --upgrade pip==26.2.0 \
    && pip install --no-cache-dir --only-binary=:all: -r requirements.lock \
    && pip check \
    && pip uninstall --yes pip
# Copy the resulting official Python filesystem into one runtime layer.
# This keeps the interpreter/libs but does not ship removed installer/vendor
# bytes in inherited lower layers. Build tools remain in the build stage only.
FROM scratch
COPY --from=dependencies / /
WORKDIR /app
COPY app.py seo_service.py membership_payments.py reconcile_membership.py ./
COPY buyer_service.py catalog_service.py catalog.json ./
COPY email_auth.py mail_service.py business_mail.py mail_templates.py mail_translations.json ./
COPY trade_service.py platform_service.py image_service.py price_review_service.py verification_service.py team_service.py pagination.py ./
COPY supplier_agreement_service.py supplier-agreement.json ./
RUN addgroup -g 10001 -S autolink && adduser -u 10001 -G autolink -S -D -H autolink && mkdir -p /data && chown autolink:autolink /data
USER 10001:10001
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
CMD ["python", "app.py"]
