## RKN reports getting automation

### What this script does:

 - login to "revizor" portal
 - resolve a captcha
 - request a report
 - wait for it
 - get the report files
 - check it for a "bad" content
___
### Install

#### to Virtualenv

> Note: For captcha resolving uses Tesseract OCR ([Installation](https://tesseract-ocr.github.io/tessdoc/Installation.html))

```bash
virtualenv venv
source ./venv/bin/activate
pip install -r requirements.txt
```
#### or build a Docker image

| build-arg | meaning           | default  |
|-----------|-------------------|----------|
| UID       | running user ID   | 1000     |
| GID       | running group ID  | 1000     |
| OUT       | report saving dir | /app/out |

```bash
docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) . -t rkn-reports
```
___
### Config

Env variables

| variable          | meaning                                |
|-------------------|----------------------------------------|
| RKN_REP_URL       | report portal host                     |
| RKN_REP_WAIT      | how long to wait for report generation |
| RKN_REP_EMAIL     | report portal account email            |
| RKN_REP_PASSWORD  | report portal account password         |
| RKN_REP_YESTERDAY | make the report for yesterday's date   |
| RKN_REP_OUT       | where to store unpacked report         |

___
### Test

```bash
python -m pytest
```
___
### Run

#### Standalone

```bash
python check_revizor.py
```
#### or Docker container (variables are in the `.env` file here)

```bash
docker run --rm -it --env-file .env -v ${PWD}/out:/app/out  rkn-reports
```
