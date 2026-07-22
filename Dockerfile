# Container for hosting the dashboard on Hugging Face Spaces (or any Docker
# host). HF runs containers as uid 1000 and serves port 7860.
FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

ENV PORT=7860
EXPOSE 7860
CMD ["python", "dashboard.py"]
