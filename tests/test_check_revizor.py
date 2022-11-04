import datetime

import pytest
import requests
from PIL import Image

import time

import check_revizor as crz
import responses


@pytest.mark.parametrize('min_t,max_t', [
    (0.5, 1.5),
    (0.01, 0.04),
    (0.75, 1.0),
])
def test_sleep_rand_s(min_t: float, max_t: float):
    t0 = time.time()
    crz.sleep_rand_s(min_t, max_t)
    td = time.time() - t0
    assert min_t <= td <= max_t


def test_check_el():
    with pytest.raises(crz.ElementNotFound):
        crz.check_el(None)
    try:
        crz.check_el('not None')
    except crz.ElementNotFound:
        assert False
    assert True


fake_url = 'https://fake-url'


@pytest.fixture
def resp():
    with responses.RequestsMock() as r:
        yield r


def read_file(file_path: str) -> str:
    with open(file_path, 'r') as fd:
        return fd.read()


def read_file_b(file_path: str) -> bytes:
    with open(file_path, 'rb') as fd:
        return fd.read()


def test_get_captcha_id_n_url(resp):
    resp.get(f'{fake_url}/login/', status=200,
             body=read_file('tests/data/login.html.dump'))
    sess, cap_id, cap_url = crz.get_captcha_id_n_url(fake_url)
    assert isinstance(sess, requests.Session)
    assert cap_id == 822915
    assert cap_url == f'{fake_url}/captcha/822915'


def test_get_captcha_img(resp):
    resp.get(f'{fake_url}/captcha/822915', status=200,
             body=read_file_b('tests/data/c_822915_o_1.png'))
    s = requests.Session()
    img_load = Image.open('tests/data/c_822915_o_1.png')
    img_got = crz.get_captcha_img(s, f'{fake_url}/captcha/822915')

    assert img_load.tobytes() == img_got.tobytes()


def test_clean_img():
    img_origin = Image.open('tests/data/c_822915_o_1.png')
    img_clean = Image.open('tests/data/c_822915_a_1.png')
    assert crz.clean_img(img_origin).tobytes() == img_clean.tobytes()


def test_recognize():
    img_clean = Image.open('tests/data/c_822915_a_1.png')
    assert crz.recognize(img_clean) == '3352'


def test_grab_captcha(resp):
    resp.get(f'{fake_url}/login/', status=200,
             body=read_file('tests/data/login.html.dump'))
    resp.get(f'{fake_url}/captcha/822915', status=200,
             body=read_file_b('tests/data/c_822915_o_1.png'))
    sess, cap_id, winner = crz.grab_captcha(fake_url)
    assert isinstance(sess, requests.Session)
    assert cap_id == 822915
    assert winner == 3352


def test_login(resp):
    resp.get(f'{fake_url}/login/', status=200,
             body=read_file('tests/data/login.html.dump'))
    resp.post(f'{fake_url}/login/', status=200,
              body=read_file('tests/data/claims.html.dump'))
    resp.get(f'{fake_url}/captcha/822915', status=200,
             body=read_file_b('tests/data/c_822915_o_1.png'))
    sess = crz.login('user', 'password', fake_url)
    assert isinstance(sess, requests.Session)


def test_parse_new_order_dt(resp):
    resp.post(f'{fake_url}/cabinet/myclaims-reports/create', status=200,
              body=read_file('tests/data/create.html.dump'))
    order_date = crz.order_new_report(
        requests.Session(), fake_url, datetime.date(2022, 11, 4))
    assert order_date == '04.11.2022 22:10'


def test_get_orders_table(resp):
    resp.get(f'{fake_url}/cabinet/myclaims-reports/', status=200,
             body=read_file_b('tests/data/create.html.dump'))
    assert read_file_b('tests/data/create.html.dump') == \
           crz.get_orders_table(requests.Session(), fake_url)


@pytest.mark.parametrize('dt,href', [
    ('03.11.2022 13:10', '/11056042.zip'),
    ('02.11.2022 13:08', '/11046982.zip'),
    ('01.11.2022 13:12', '/11037965.zip'),
])
def test_parse_order_href(dt, href):
    parsed = crz.parse_order_href(
        read_file_b('tests/data/create.html.dump'), dt)
    assert parsed.endswith(href)


def test_order_new_report(resp):
    resp.post(f'{fake_url}/cabinet/myclaims-reports/create', status=200,
              body=read_file('tests/data/create.html.dump'))
    order_date = crz.order_new_report(
        requests.Session(), fake_url, datetime.date(2048, 1, 10))
    assert order_date == '04.11.2022 22:10'


def test_get_report_archive(resp):
    resp.get(f'{fake_url}/-/download/report-orig.zip', status=200,
             body=read_file_b('tests/data/report-orig.zip'))
    crz.get_report_archive(
        requests.Session(),
        fake_url + '/-/download/report-orig.zip',
        'tests/data/report-copied.zip'
    )
    assert read_file_b('tests/data/report-orig.zip') == \
           read_file_b('tests/data/report-copied.zip')


def test_unpack_archive():
    crz.unpack_archive(
        'tests/data/report-orig.zip',
        'tests/data/unpacked-test'
    )
    assert read_file_b('tests/data/unpacked-test/report.csv') == \
           read_file_b('tests/data/unpacked-orig/report.csv')
