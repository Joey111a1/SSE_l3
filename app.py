from flask import Flask, render_template, request, redirect, url_for, session
import os
import polars as pl
import configparser
from adbc_driver_postgresql import dbapi
import secrets
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Below are local configuration -- sadly cannot use them online
config = configparser.ConfigParser()
config.read('config.ini')
db_host = config.get('database', 'host')
db_port = config.get('database', 'port')
db_user = config.get('database', 'user')
db_password = config.get('database', 'password')
db_name = config.get('database', 'database')
conn = dbapi.connect(f"postgresql://{db_user}:{db_password}"
                     f"@{db_host}:{db_port}/{db_name}")
# # online configuration
# DATABASE_URL = os.environ.get('DATABASE_URL')
# conn = dbapi.connect(DATABASE_URL)

cur = conn.cursor()

create_users_table = """
CREATE TABLE IF NOT EXISTS users (
    username VARCHAR(255) NOT NULL PRIMARY KEY,
    password VARCHAR(255) NOT NULL
);
"""
cur.execute(create_users_table)

create_texts_table = """
CREATE TABLE IF NOT EXISTS texts (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users (username)
);
"""
cur.execute(create_texts_table)
conn.commit()

# deal with the special data structure on musicbrainz
namespaces = {'ns': 'http://musicbrainz.org/ns/mmd-2.0#'}


def escape_sql_value(value: str) -> str:
    return value.replace("'", "''")


def user_exists(username):
    safe_username = escape_sql_value(username)
    query = f"SELECT username FROM users WHERE username = '{safe_username}';"
    df = pl.read_database(query, conn)
    return df.shape[0] > 0


def verify_user(username, password):
    safe_username = escape_sql_value(username)
    safe_password = escape_sql_value(password)
    query = f"SELECT username FROM users WHERE username = '{safe_username}' " \
            f"AND password = '{safe_password}';"
    df = pl.read_database(query, conn)
    return df.shape[0] > 0


def create_user(username, password):
    safe_username = escape_sql_value(username)
    safe_password = escape_sql_value(password)
    insert_query = f"INSERT INTO users (username, password) VALUES " \
                   f"('{safe_username}', '{safe_password}');"
    cur.execute(insert_query)
    conn.commit()


def update_password(username, new_password):
    safe_username = escape_sql_value(username)
    safe_password = escape_sql_value(new_password)
    update_query = f"UPDATE users SET password = '{safe_password}' " \
                   f"WHERE username = '{safe_username}';"
    cur.execute(update_query)
    conn.commit()


def get_works(artist_name):
    artist_url = f'https://musicbrainz.org/ws/2/artist?' \
                 f'query={artist_name}&fmt=xml'
    request_body = requests.get(artist_url).text
    root = ET.fromstring(request_body)

    artist_element = root.find('.//ns:artist', namespaces)
    title_list = []
    work_id_list = []

    if artist_element is not None:
        artist_id = artist_element.get('id')
        print(f"Artist ID: {artist_id}")

        work_url = f'https://musicbrainz.org/ws/2/work?' \
                   f'artist={artist_id}&limit=100&fmt=xml'
        request_body_work = requests.get(work_url).text
        root_2 = ET.fromstring(request_body_work)

        works = root_2.findall('.//ns:work', namespaces)

        for w in works:
            title_elem = w.find('ns:title', namespaces)
            if title_elem is not None:
                title_list.append(title_elem.text)
            work_id_list.append(w.get('id'))

    return title_list, work_id_list


def get_work_information(work_id):
    work_url = f'https://musicbrainz.org/ws/2/work/' \
               f'{work_id}?inc=artist-rels&fmt=xml'
    response = requests.get(work_url)
    if response.status_code != 200:
        return {"error": "Failed to retrieve work information."}

    root = ET.fromstring(response.content)
    relations = []
    relation_list = root.findall('.//ns:relation-list/ns:relation', namespaces)
    for relation in relation_list:
        relation_type = relation.get('type', 'Unknown')  # relation-type
        artist = relation.find('ns:artist', namespaces)
        if artist is not None:
            name_elem = artist.find('ns:name', namespaces)
            sort_name_elem = artist.find('ns:sort-name', namespaces)
            name = name_elem.text \
                if name_elem is not None else 'No Name'
            sort_name = sort_name_elem.text if \
                sort_name_elem is not None else 'No Sort Name'

            relations.append({
                'relation_type': relation_type,
                'name': name,
                'sort_name': sort_name
            })
    return {"relations": relations}


# This is necessary since the api has different ids
# for a piece of work and its corresponding recordings
def get_recordings_for_work(work_id: str) -> str:
    recordings_url = f"https://musicbrainz.org/ws/2/" \
                     f"recording?work={work_id}&limit=1&fmt=xml"
    response = requests.get(recordings_url)
    if response.status_code == 200:
        return response.text
    return None


def get_first_recording_id(xml_data: str) -> str:
    root = ET.fromstring(xml_data)
    first_recording = root.find('.//ns:recording', namespaces)
    if first_recording is not None:
        return first_recording.get('id')
    return None


@app.route('/')
def index():
    if 'username' in session:
        username = session['username']
        query = f"SELECT id, content FROM texts WHERE " \
                f"username = '{escape_sql_value(username)}' ORDER BY id;"
        df = pl.read_database(query, conn)
        text_dicts = df.to_dicts()
        return render_template('index.html', logged_in=True,
                               username=username, texts=text_dicts)
    else:
        return render_template('index.html', logged_in=False)


@app.route('/add_text', methods=['GET', 'POST'])
def add_text():
    work_info = session.get('work_info', None)
    selected_work_id = session.get('selected_work_id', None)
    selected_artist = session.get('selected_artist', None)
    title_work_pairs = session.get('title_work_pairs', [])
    recording_id = session.get('recording_id', None)

    if request.method == "POST":
        if 'username' in session:
            username = session['username']
            content = request.form.get('content')
            if content.strip() == "":
                return render_template('add_text.html',
                                       error="Please put some words in!",
                                       titles=title_work_pairs,
                                       artist=selected_artist,
                                       work_info=work_info,
                                       selected_work_id=selected_work_id,
                                       recording_id=recording_id)
            safe_content = escape_sql_value(content)
            insert_query = f"INSERT INTO texts (username, content) VALUES " \
                           f"('{escape_sql_value(username)}', " \
                           f"'{safe_content}');"
            cur.execute(insert_query)
            conn.commit()
        return redirect(url_for('index'))

    return render_template('add_text.html', titles=title_work_pairs,
                           artist=selected_artist, work_info=work_info,
                           selected_work_id=selected_work_id,
                           recording_id=recording_id)


@app.route('/edit_text/<int:text_id>', methods=['GET', 'POST'])
def edit_text(text_id):
    if 'username' in session:
        username = session['username']

        # Retrieve the same data as in add_text
        work_info = session.get('work_info', None)
        selected_work_id = session.get('selected_work_id', None)
        selected_artist = session.get('selected_artist', None)
        title_work_pairs = session.get('title_work_pairs', [])
        recording_id = session.get('recording_id', None)

        if request.method == 'POST':
            new_content = request.form.get('content')
            safe_content = escape_sql_value(new_content)
            update_query = f"UPDATE texts SET content = '" \
                           f"{safe_content}' " \
                           f"WHERE id = {text_id} AND " \
                           f"username = '{escape_sql_value(username)}';"
            cur.execute(update_query)
            conn.commit()
            return redirect(url_for('index'))
        else:
            query = f"SELECT content FROM texts " \
                    f"WHERE id = {text_id} " \
                    f"AND username = '{escape_sql_value(username)}';"
            df = pl.read_database(query, conn)
            if df.shape[0] > 0:
                content = df[0, 'content']
                return render_template(
                    'edit_text.html',
                    text_id=text_id,
                    content=content,
                    titles=title_work_pairs,
                    artist=selected_artist,
                    work_info=work_info,
                    selected_work_id=selected_work_id,
                    recording_id=recording_id
                )
    return redirect(url_for('index'))


@app.route('/delete_text/<int:text_id>', methods=['POST'])
def delete_text(text_id):
    if 'username' in session:
        username = session['username']
        if request.method == 'POST':
            delete_query = f"DELETE FROM texts " \
                           f"WHERE id = {text_id} " \
                           f"AND username = '{escape_sql_value(username)}';"
            cur.execute(delete_query)
            conn.commit()
    return redirect(url_for('index'))


# This function and the one under it has to fit
# in both add and edit text page
# so there has to be a way to distinguish them
@app.route('/search_artist', methods=['POST'])
def search_artist():
    artist = request.form.get('artist', '').strip()
    page = request.form.get('page', '')
    titles = []
    works = []
    title_work_pairs = []

    if artist:
        titles, works = get_works(artist)
        title_work_pairs = list(zip(titles, works))
        session['title_work_pairs'] = title_work_pairs

    if page == 'add_text':
        # For add_text, content is not needed from the DB
        return render_template('add_text.html',
                               titles=title_work_pairs,
                               artist=artist, works=works)
    elif page.startswith('edit_text'):
        parts = page.split('/')
        if len(parts) == 2 and parts[0] == 'edit_text':
            try:
                text_id = int(parts[1])

                if 'username' in session:
                    username = session['username']
                    query = f"SELECT content " \
                            f"FROM texts " \
                            f"WHERE id = {text_id} " \
                            f"AND username = '{escape_sql_value(username)}';"
                    df = pl.read_database(query, conn)
                    if df.shape[0] > 0:
                        content = df[0, 'content']
                    else:
                        content = ""  # fallback if no content found
                else:
                    content = ""  # no user logged in

                work_info = session.get('work_info', None)
                selected_work_id = session.get('selected_work_id', None)
                selected_artist = artist
                recording_id = session.get('recording_id', None)

                return render_template(
                    'edit_text.html',
                    text_id=text_id,
                    content=content,
                    titles=title_work_pairs,
                    artist=selected_artist,
                    work_info=work_info,
                    selected_work_id=selected_work_id,
                    recording_id=recording_id
                )
            except (IndexError, ValueError):
                pass
    return redirect(url_for('index'))


@app.route('/get_work_info', methods=['POST'])
def get_work_info():
    if 'username' in session:
        work_id = request.form.get('work_id')
        artist = request.form.get('artist')
        page = request.form.get('page', '')

        if work_id:
            relations = get_work_information(work_id)
            session['work_info'] = relations
            session['selected_work_id'] = work_id
            session['selected_artist'] = artist

            recordings_xml = get_recordings_for_work(work_id)
            if recordings_xml:
                recording_id = get_first_recording_id(recordings_xml)
                if recording_id:
                    session['recording_id'] = recording_id

            if page == 'add_text':
                return redirect(url_for('add_text'))
            elif page.startswith('edit_text'):
                parts = page.split('/')
                if len(parts) == 2:
                    try:
                        text_id = int(parts[1])
                        return redirect(url_for('edit_text', text_id=text_id))
                    except ValueError:
                        pass
                # Fallback redirect
            return redirect(url_for('index'))

    return redirect(url_for('index'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if verify_user(username, password):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html',
                                   error="Invalid username or password.")
    return render_template('login.html')


@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if user_exists(username):
            return render_template('signin.html',
                                   error="User already exists, "
                                         "try a different username.")
        else:
            create_user(username, password)
            session['username'] = username
            return redirect(url_for('index'))
    return render_template('signin.html')


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form.get('username')
        new_password = request.form.get('new_password')
        if user_exists(username):
            update_password(username, new_password)
            return redirect(url_for('login'))
        else:
            return render_template('reset_password.html',
                                   error="User does not exist.")
    return render_template('reset_password.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
