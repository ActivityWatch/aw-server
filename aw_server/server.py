import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from aw_datastore import Datastore

from .log import FlaskLogHandler


app_folder = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(app_folder, 'static')
print(static_folder)

app = Flask("aw-server",
            static_folder=static_folder, static_url_path='')
CORS(app)   # See: https://flask-cors.readthedocs.org/en/latest/

# The following will be set when started
app.db = None  # type: Datastore


@app.route("/")
def static_root():
    return app.send_static_file('index.html')
    return send_from_directory('/', 'index.html')


@app.route("/css/<path:path>")
def static_css(path):
    return send_from_directory(static_folder + '/css', path)


@app.route("/js/<path:path>")
def static_js(path):
    return send_from_directory(static_folder + '/js', path)


# Only to be called from aw_server.main function!
def _start(storage_method, port=5600, testing=False):
    app.db = Datastore(storage_method, testing=testing)
    app.run(debug=testing, port=port, request_handler=FlaskLogHandler)
