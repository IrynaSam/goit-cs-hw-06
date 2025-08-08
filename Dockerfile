FROM python:3.12-slim

WORKDIR /app

# ставимо залежності з requirements.txt
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# копіюємо код
COPY project-root/ /app/

ENV PYTHONUNBUFFERED=1
EXPOSE 3000 5000

CMD ["python", "src/main.py"]