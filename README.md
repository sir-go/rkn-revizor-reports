## RKN reports getting automation

What this script does:
 - login to "revizor" portal
 - resolve a captcha
 - request a report
 - wait for it
 - get the report files
 - check it for a "bad" content

## Install

```bash
virtualenv venv
source ./venv/bin/activate
pip install -r requirements.txt
```
For captcha resolving uses Tesseract OCR ([Installation](https://tesseract-ocr.github.io/tessdoc/Installation.html))

## Config

`config.py` contains params

| param            | type | descr                                                |
|------------------|------|------------------------------------------------------|
| portal_url       | str  | revizor portal URL                                   |
| wait_report_done | int  | how long to wait report making (in seconds)          |
| auth_email       | str  | portal auth login                                    |
| auth_password    | str  | portal auth password                                 |
| yesterday        | bool | get yesterday's report instead of making the new one |

## Run

```bash
python check_revizor.py
```
