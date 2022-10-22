# coding:utf8

from requests import Session
from lxml import html
from PIL import Image
from io import BytesIO
from pytesseract.pytesseract import image_to_string
from string import digits
from time import sleep, time
from random import randint
import glob
import os
from datetime import date, timedelta
import shutil
import zipfile
import logging
import json
import sys


class ElementNotFound(Exception):
    pass


class LoginFailed(Exception):
    pass


class GetFailed(Exception):
    pass


class TimedOut(Exception):
    pass


log = logging.getLogger('revizor')
log.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s: %(message)s")

# log to file
fh = logging.FileHandler('tmp/revizor.log')
fh.setFormatter(formatter)
log.addHandler(fh)

# log to console
ch = logging.StreamHandler()
ch.setFormatter(formatter)
log.addHandler(ch)


def clear_log():
    with open('tmp/revizor.log', 'w') as logfile:
        logfile.truncate()


def sleep_rand_s(min_t: float = 0.05, max_t: float = 0.5):
    timeout = randint(int(min_t * 1000), int(max_t * 1000)) / 1000
    log.debug('sleep for {}s'.format(timeout))
    sleep(timeout)


def check_response(resp):
    if not (resp and resp.ok):
        raise GetFailed()


def check_el(el):
    if el is None:
        raise ElementNotFound()


def get_captcha_id_n_url(url: str) -> (Session, int, str):
    s = Session()
    s.verify = 'rfc-revizorru.crt'

    href = url + '/login/'

    log.debug('get page ' + href)
    page = s.get(href)

    check_response(page)

    log.debug('parse page')
    dom = html.document_fromstring(page.content)
    c_el = dom.xpath('//*[@name="secretcodeId"]')

    check_el(c_el)

    c_val = c_el[0].attrib['value']
    return s, int(c_val), '{u}/captcha/{v}'.format(u=url, v=c_val)


def get_captcha_img(s: Session, captcha_url: str) -> Image:
    log.debug('get an image ' + captcha_url)
    img_resp = s.get(captcha_url)

    check_response(img_resp)

    return Image.open(BytesIO(img_resp.content))


def clean_img(img: Image, chop: int = 1) -> Image:
    bw_img = img.convert('1')
    w, h = bw_img.size
    img_data = bw_img.load()

    log.debug('clean image noise')

    for y in range(h):
        for x in range(w):
            if img_data[x, y] > 128:
                continue
            total = 0
            for c in range(x, w):
                if img_data[c, y] < 128:
                    total += 1
                else:
                    break
            if total <= chop:
                for c in range(total):
                    img_data[x + c, y] = 255
            x += total

    for x in range(w):
        for y in range(h):
            if img_data[x, y] > 128:
                continue
            total = 0
            for c in range(y, h):
                if img_data[x, c] < 128:
                    total += 1
                else:
                    break
            if total <= chop:
                for c in range(total):
                    img_data[x, y + c] = 255
            y += total

    return bw_img


def recognize(cl_img: Image) -> str:
    log.debug('solve image')
    tess_result = image_to_string(cl_img, config='digits')
    return ''.join([c for c in tess_result if c in digits])


def grab_captcha(url: str, save_images=None) -> (Session, int, int):
    results = dict()
    winner = None
    winner_condition = 5
    attempts_max = 20
    attempt = 0

    log.debug('grab captcha')
    s, c_id, c_url = get_captcha_id_n_url(url)

    log.debug('got captcha id: {}'.format(c_id))

    if save_images is not None:
        log.debug('clean directory ' + save_images)
        for f in glob.glob(os.path.join(save_images, 'c_*.png')):
            os.remove(f)

    log.debug('start captcha solving tries')
    while attempt <= attempts_max:
        attempt += 1

        log.debug('try {}/{}'.format(attempt, attempts_max))

        c_img = get_captcha_img(s, c_url)

        log.debug('got captcha image')

        c_img_clean = clean_img(c_img)

        if save_images is not None:
            filename = os.path.join(
                save_images,
                'c_{}_a_{}.png'.format(c_id, attempt)
            )
            log.debug('save image to ' + filename)
            c_img_clean.save(filename)

        recognized = recognize(c_img_clean)

        log.debug('recognized ' + recognized)

        if not len(recognized) in (3, 4):
            log.debug('bad result - ignore')
            continue

        if recognized in results:
            results[recognized] += 1
        else:
            results[recognized] = 1

        winner = max(results, key=results.get)

        log.debug('results: ' + json.dumps(results))

        if results[winner] >= winner_condition:
            log.debug('we have a winner: {}'.format(winner))
            break
        else:
            sleep_rand_s()

    return s, int(c_id), int(winner)


def login(username: str, password: str, url: str, retries: int = 5) -> Session:
    try_num = 0
    while try_num <= retries:
        try_num += 1

        log.debug('try {}/{}'.format(try_num, retries))

        s, captcha_id, captcha_value = grab_captcha(url, 'tmp/captcha_img')

        href = url + '/login/'

        log.debug('try to enter ' + href)

        post_res = s.post(
            href,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla / 5.0 Gecko / 20100101 Firefox / 52.0',
                'Referer': href
            },
            data={
                'email': username,
                'password': password,
                'secretcodeId': captcha_id,
                'secretcodestatus': captcha_value
            }
        )

        check_response(post_res)

        if post_res.content.find(b'user-menu-link') > -1:
            return s

    raise LoginFailed()


def parse_new_order_dt(post_result: bytes) -> str:
    log.debug('parse new order datetime')
    dom = html.document_fromstring(post_result)
    table_el = dom.xpath("//*[@class='watching list-table']")

    check_el(table_el)

    for tr in table_el[0].xpath("tbody/tr/td[text()='новый']"):
        check_el(tr)

        first_td = tr.getparent().find('td').text
        check_el(first_td)

        return first_td

    raise ElementNotFound()


def get_orders_table(s: Session, url: str) -> bytes:
    href = url + '/cabinet/myclaims-reports/'
    log.debug('get orders table ' + href)
    orders_table = s.get(
        href,
        headers={
            'User-Agent': 'Mozilla / 5.0 Gecko / 20100101 Firefox / 52.0',
            'Referer': href
        }
    )

    check_response(orders_table)

    return orders_table.content


def parse_order_href(get_result: bytes, dt: str) -> str:
    dom = html.document_fromstring(get_result)
    table_el = dom.xpath("//*[@class='watching list-table']")

    if not table_el:
        raise ElementNotFound()

    rep_done_a = table_el[0].xpath("tbody/tr/td[text()='{}']/../td/a".format(dt))
    if not rep_done_a:
        return ''

    return rep_done_a[0].get('href')


def order_new_report(s: Session, url: str, day: date) -> str:
    href = url + '/cabinet/myclaims-reports/create'
    log.debug('send new order request ' + href)
    post_res = s.post(
        href,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla / 5.0 Gecko / 20100101 Firefox / 52.0',
            'Referer': href
        },
        data={'reportDate': day.strftime('%d.%m.%Y')}
    )
    check_response(post_res)
    return parse_new_order_dt(post_res.content)


def get_report_archive(s: Session, url: str, save_to: str):
    log.debug('get report file ' + url)
    get_res = s.get(url, stream=True)

    check_response(get_res)

    log.debug('save report archive file to ' + save_to)
    with open(save_to, 'wb') as report_archive_file:
        get_res.raw.decode_content = True
        shutil.copyfileobj(get_res.raw, report_archive_file)


def unpack_archive(arch_file: str, unpack_to: str):
    log.debug('clean directory ' + unpack_to)
    for f in glob.glob(unpack_to + '*'):
        if os.path.isfile(f):
            os.remove(f)

    log.debug('extract report archive to ' + unpack_to)
    zip_ref = zipfile.ZipFile(arch_file, 'r')
    zip_ref.extractall(unpack_to)
    zip_ref.close()


if __name__ == '__main__':

    portal_url = 'https://portal.rfc-revizor.ru'
    wait_report_done = 300
    clear_log()

    log.debug('-------- start --------')

    log.debug('logging in ' + portal_url)
    session = login('//@//.//', '//', portal_url)

    log.debug('order new report')
    today = date.today()
    yesterday = today - timedelta(days=1)
    report_dt = order_new_report(
        session, portal_url, yesterday if len(sys.argv) > 1 and sys.argv[1] == 'yesterday' else today)

    log.debug('got new order report datetime ' + report_dt)

    report_href = ''

    log.debug('wait till report is made')
    t0 = time()
    while time() - t0 < wait_report_done:
        log.debug('check report status')
        report_href = parse_order_href(get_orders_table(session, portal_url), report_dt)
        if report_href:
            log.debug('report is done, href: ' + report_href)
            break
        log.debug('not done yet')
        sleep_rand_s(15, 60)

    if not report_href:
        log.error('timed out {}s'.format(wait_report_done))
        raise TimedOut()

    get_report_archive(session, portal_url + report_href, 'tmp/rep_arch.zip')
    unpack_archive('tmp/rep_arch.zip', 'tmp/unpacked/')

    if os.path.getsize('tmp/unpacked/report.csv') > 270:
        log.warning('report is not good')
        exit(1)
    else:
        log.debug('report is clean')
        exit(0)
