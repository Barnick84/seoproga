import urllib.request
import urllib.parse
import hashlib

secret = 'S27rLR1n'
data = {
    'shop_id': '349EE138E59AC90ACA1BB7A17C61E7F6',
    'amount': '500',
    'currency': 'RUB',
    'order_id': 'test_123',
    'success_url': 'https://seoproga.ru/suceful/',
    'fail_url': 'https://seoproga.ru/errore/',
    'notify_url': 'https://seoproga.ru/payment-suceful/'
}

keys = ['shop_id', 'amount', 'currency', 'order_id']
sign_str = '&'.join([f'{k}={data[k]}' for k in sorted(keys)])
sign = hashlib.md5((sign_str + secret).encode()).hexdigest()

data['sign'] = sign
url = 'https://tegro.money/pay/?' + urllib.parse.urlencode(data)
print('URL:', url)

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        if 'Стоимость товара не сходится' in html:
            print('Error found: Стоимость товара не сходится с суммой оплаты')
        elif 'Неверная подпись' in html:
            print('Error found: Неверная подпись')
        else:
            print('Success? HTML len:', len(html))
except urllib.error.HTTPError as e:
    html = e.read().decode('utf-8')
    print('HTTP Error', e.code)
    if 'Стоимость товара не сходится' in html:
        print('Error found: Стоимость товара не сходится с суммой оплаты')
    elif 'Неверная подпись' in html:
        print('Error found: Неверная подпись')
    else:
        print(html[:500])
