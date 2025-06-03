FROM python:3.12-slim

WORKDIR /app

COPY ./fleet_analyzer/a2a_requirements.txt /app/requirements.txt
COPY ./a2a_common-0.1.0-py3-none-any.whl /app/a2a_common-0.1.0-py3-none-any.whl
RUN pip install --no-cache-dir -r requirements.txt

COPY ./fleet_analyzer /app/agents/fleet_analyzer

ENV PYTHONPATH=/app/agents

EXPOSE 8080

CMD ["python", "-m", "fleet_analyzer.a2a_server"]
