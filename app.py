import requests
import configparser
from flask import Flask, redirect, request, session, url_for, render_template, send_file
from io import BytesIO
from datetime import timedelta

# Путь к файлу конфигурации
CONFIG_PATH = '.config'

# Чтение конфигурационного файла или его создание
config = configparser.ConfigParser()
config.read(CONFIG_PATH)

# Инициализация переменных из конфигурационного файла
CLIENT_ID = config['OAuth']['client_id']
CLIENT_SECRET = config['OAuth']['client_secret']
REDIRECT_URI = config['OAuth']['redirect_uri']
SECRET_KEY = config['Flask']['secret_key']

# Создание приложения Flask
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Делаем сессию постоянной, устанавливаем срок жизни сессии
app.permanent_session_lifetime = timedelta(minutes=30)

### Реализация маршрутов для авторизации и работы с файлами

# Эндпоинт для входа в приложение через Яндекс OAuth
@app.route('/login')
def login():
    yandex_oauth_url = (
        "https://oauth.yandex.ru/authorize?"
        f"response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
    )
    return redirect(yandex_oauth_url)

# Обработка перенаправления после авторизации
@app.route('/oauth/callback')
def callback():
    code = request.args.get('code')
    if code:
        session.permanent = True  # Делаем сессию постоянной, чтобы данные сохранялись на более длительный срок
        token_url = "https://oauth.yandex.ru/token"
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'redirect_uri': REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(token_url, data=data, headers=headers)
        if response.status_code == 200:
            token_data = response.json()
            session['access_token'] = token_data['access_token']
            return redirect(url_for('dashboard'))
        else:
            return "Ошибка при получении токена", 400
    else:
        return "Отсутствует код авторизации", 400

# Получение списка файлов с поддержкой навигации по папкам, фильтрации и скачивания
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    access_token = session.get('access_token')
    if not access_token:
        return redirect(url_for('login'))

    # public_key получаем из формы
    public_key = request.args.get('public_key') or request.form.get('public_key')
    path = request.args.get('path', '')
    file_type = request.form.get('file_type') if request.method == 'POST' else None

    if public_key:
        url = f'https://cloud-api.yandex.net/v1/disk/public/resources?public_key={public_key}&path={path}'
        headers = {'Authorization': f'OAuth {access_token}'}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            items = data.get('_embedded', {}).get('items', [])
            current_path = data.get('path', '')

            # Добавляем ссылку для скачивания для каждого файла
            for item in items:
                if item['type'] == 'file':
                    item['download_url'] = url_for('download_file', public_key=public_key, path=item['path'])

            # Фильтрация файлов по типу с проверкой наличия ключа 'mime_type'
            if file_type:
                items = [item for item in items if 'mime_type' in item and item['mime_type'].startswith(file_type)]

            return render_template('files.html', items=items, public_key=public_key, current_path=current_path)
        else:
            return f"Ошибка при получении файлов: {response.text}", 400
    else:
        return render_template('index.html')

# Маршрут для скачивания файлов
@app.route('/download')
def download_file():
    access_token = session.get('access_token')
    if not access_token:
        return redirect(url_for('login'))

    public_key = request.args.get('public_key')
    path = request.args.get('path')

    if public_key and path:
        url = f'https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={public_key}&path={path}'
        headers = {'Authorization': f'OAuth {access_token}'}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            download_info = response.json()
            download_url = download_info.get('href')

            if download_url:
                file_response = requests.get(download_url)
                if file_response.status_code == 200:
                    return send_file(BytesIO(file_response.content), download_info.get('filename', 'downloaded_file'))
                else:
                    return f"Ошибка при скачивании файла: {file_response.status_code}", 400
        return f"Ошибка при получении ссылки для скачивания: {response.status_code}", 400

    return "Недопустимый запрос на скачивание", 400

# Главная страница
@app.route('/')
def index():
    return render_template('index.html')

# Маршрут для выхода (очистки сессии)
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
