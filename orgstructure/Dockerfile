FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt && cp requirements.txt .venv/.requirements
COPY app app
COPY static static
COPY data data
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["python", "-m", "app"]
