# ---- Build stage ----
FROM python:3.12-alpine AS builder

WORKDIR /app

RUN apk add --no-cache postgresql-dev gcc musl-dev

COPY app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Final stage ----
FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache postgresql-libs

# Copy only the installed Python packages from the build stage
COPY --from=builder /install /usr/local

COPY app/ .

RUN adduser -D -u 1000 appuser
USER 1000

EXPOSE 5000

CMD ["python", "app.py"]
