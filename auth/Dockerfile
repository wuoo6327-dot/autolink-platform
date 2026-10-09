FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY buyer_service.py catalog_service.py catalog.json ./
COPY seo_service.py ./
COPY email_auth.py mail_service.py business_mail.py mail_templates.py mail_translations.json ./
COPY trade_service.py platform_service.py image_service.py price_review_service.py verification_service.py team_service.py pagination.py ./
COPY supplier_agreement_service.py supplier-agreement.json ./
RUN groupadd --gid 10001 autolink && useradd --uid 10001 --gid 10001 --no-create-home autolink && mkdir -p /data && chown autolink:autolink /data
USER 10001:10001
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "app.py"]
