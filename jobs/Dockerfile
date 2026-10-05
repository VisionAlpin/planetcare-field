# PlanetCare Field Nachtjob (Render Cron, Build Kontext = Projektwurzel)
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY jobs/requirements.txt /app/jobs/requirements.txt
RUN pip install --no-cache-dir -r /app/jobs/requirements.txt
# Bewertungslogik wird mit der API geteilt
COPY api/app /app/api/app
COPY jobs /app/jobs
WORKDIR /app/jobs
CMD ["python", "-m", "pcf_jobs.run_nightly"]
