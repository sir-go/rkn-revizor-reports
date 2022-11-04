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


class ElementNotFound(Exception):
    pass


class LoginFailed(Exception):
    pass


class GetFailed(Exception):
    pass


class TimedOut(Exception):
    pass


def init_logging() -> logging.Logger:
    _log = logging.getLogger('revizor')
    _log.setLevel(logging.DEBUG)
    # noinspection SpellCheckingInspection
    formatter = logging.Formatter("%(asctime)s: %(message)s")

    if __name__ == '__main__':
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        _log.addHandler(ch)

    return _log


log = init_logging()


def sleep_rand_s(min_t: float = 0.05, max_t: float = 0.5):
    timeout = randint(int(min_t * 1000), int(max_t * 1000)) / 1000
    log.debug('sleep for {}s'.format(timeout))
    sleep(timeout)


def check_el(el):
    if el is None:
        raise ElementNotFound


# noinspection SpellCheckingInspection
def get_captcha_id_n_url(url: str) -> (Session, int, str):
    s = Session()
    s.verify = False

    href = url + '/login/'

    log.debug('get page ' + href)
    page = s.get(href)
    page.raise_for_status()

    log.debug('parse page')
    dom = html.document_fromstring(page.content)
    c_el = dom.xpath('//*[@name="secretcodeId"]')

    check_el(c_el)

    c_val = c_el[0].attrib['value']
    return s, int(c_val), '{u}/captcha/{v}'.format(u=url, v=c_val)


def get_captcha_img(s: Session, captcha_url: str) -> Image:
    log.debug('get an image ' + captcha_url)
    img_resp = s.get(captcha_url)
    img_resp.raise_for_status()

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


def grab_captcha(url: str, save_images: str = None) -> (Session, int, int):
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
            c_img.save(
                os.path.join(save_images, f'c_{c_id}_o_{attempt}.png'))
            c_img_clean.save(
                os.path.join(save_images, f'c_{c_id}_a_{attempt}.png'))

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


# noinspection SpellCheckingInspection
def login(username: str, password: str, url: str, retries: int = 5) -> Session:
    try_num = 0
    while try_num <= retries:
        try_num += 1

        log.debug('try {}/{}'.format(try_num, retries))

        s, captcha_id, captcha_value = grab_captcha(url)

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
        post_res.raise_for_status()

        if post_res.content.find(b'user-menu-link') > -1:
            return s

    raise LoginFailed


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

    raise ElementNotFound


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
    orders_table.raise_for_status()

    return orders_table.content


def parse_order_href(get_result: bytes, dt: str) -> str:
    dom = html.document_fromstring(get_result)
    table_el = dom.xpath("//*[@class='watching list-table']")

    if not table_el:
        raise ElementNotFound

    rep_done_a = table_el[0].xpath(f"tbody/tr/td[text()='{dt}']/../td/a")
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
    post_res.raise_for_status()
    return parse_new_order_dt(post_res.content)


def get_report_archive(s: Session, url: str, save_to: str):
    log.debug('get report file ' + url)
    get_res = s.get(url, stream=True)
    get_res.raise_for_status()

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


def get_and_analyze_report(
        url: str,
        wait: int,
        email: str,
        password: str,
        yesterday: bool,
        unpack_path: str) -> bool:
    os.makedirs(unpack_path, exist_ok=True)
    os.makedirs('tmp/captcha_img', exist_ok=True)

    log.debug('logging in ' + url)
    session = login(email, password, url)

    log.debug('order new report')
    today = date.today()
    report_dt = order_new_report(
        session, url, today - timedelta(days=1) if yesterday else today)

    log.debug('got new order report datetime ' + report_dt)

    report_href = ''

    log.debug('wait till report is made')
    t0 = time()
    while time() - t0 < wait:
        log.debug('check report status')
        report_href = parse_order_href(
            get_orders_table(session, url), report_dt)
        if report_href:
            log.debug('report is done, href: ' + report_href)
            break
        log.debug('not done yet')
        sleep_rand_s(15, 60)

    if not report_href:
        log.error('timed out {}s'.format(wait))
        raise TimedOut

    get_report_archive(session, url + report_href, 'tmp/rep_arch.zip')
    unpack_archive('tmp/rep_arch.zip', unpack_path)

    if os.path.getsize(os.path.join(unpack_path, 'report.csv')) > 270:
        log.warning('report is not good')
        return True

    log.debug('report is clean')
    return False


if __name__ == '__main__':
    log.debug('-------- start --------')
    conf = dict(
        url=os.environ.get('RKN_REP_URL'),
        wait=int(os.environ.get('RKN_REP_WAIT', 300)),
        email=os.environ.get('RKN_REP_EMAIL'),
        password=os.environ.get('RKN_REP_PASSWORD'),
        yesterday=os.environ.get('RKN_REP_YESTERDAY', True) in [
            True, 1, 'yes', 'y', 'True', 'true', 'on'],
        unpack_path=os.environ.get('RKN_REP_OUT', 'tmp/unpacked/')
    )
    exit(int(get_and_analyze_report(**conf)))
