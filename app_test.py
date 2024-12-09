# from app import process_query
#
#
# def test_knows_about_dinosaurs():
#     assert process_query("dinosaurs") == "Dinosaurs ruled the \
# Earth 200 million years ago"

import app


#
#
# def client():
#     # Set up the Flask test client
#     app.config['TESTING'] = True
#     # If your app relies on session, database, or other envs,
#     # you might need to mock them here
#     with app.test_client() as client:
#         yield client
#
#
# def test_index_page(client):
#     response = client.get('/')
#     assert response.status_code == 200
#     # Check if a keyword from your homepage template is present
#     # For example, if your index page shows "Home" or "Add new text here"
#     assert b'Home' in response.data
#
#
# def test_login_page(client):
#     response = client.get('/login')
#     assert response.status_code == 200
#     # assuming login page has a field 'username'
#     assert b'username' in response.data
#
#
# def test_signin_page(client):
#     response = client.get('/signin')
#     assert response.status_code == 200
#     assert b'User already exists' not in response.data  # Just a random check
def check_namespace():
    assert app.namespaces == "namespaces = " \
                             "{'ns': 'http://musicbrainz.org/ns/mmd-2.0#'}"
