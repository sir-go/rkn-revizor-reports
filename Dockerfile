FROM python:3.10-alpine3.16
WORKDIR /app
RUN apk add tesseract-ocr
COPY requirements.txt requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

COPY check_revizor.py check_revizor.py

ARG UID=1000
ARG GID=1000
ARG OUT=/app/out

RUN addgroup -g $GID non-root-group &&  \
    adduser -S -H -u $UID non-root-user non-root-group && \
    chown -R non-root-user:non-root-group .

USER non-root-user

RUN mkdir $OUT

CMD [ "python", "check_revizor.py"]
