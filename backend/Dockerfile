FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY psb_engine.py ./
COPY psb_data/knowledge-base ./psb_data/knowledge-base
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
