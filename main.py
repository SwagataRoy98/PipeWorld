from flask import Flask, request, make_response
import pymysql
import os
from dotenv import load_dotenv
from heyoo import WhatsApp

app = Flask(__name__)
load_dotenv()
db_user = os.environ.get('CLOUD_SQL_USERNAME')
db_password = os.environ.get('CLOUD_SQL_PASSWORD')
db_name = os.environ.get('CLOUD_SQL_DATABASE_NAME')
db_connection_name = os.environ.get('CLOUD_SQL_CONNECTION_NAME')
db_host = os.environ.get('DB_HOST')
token = os.environ.get('TOKEN')
phone_number_id = os.environ.get('PHONE_NUMBER_ID')
messenger = WhatsApp(token=token, phone_number_id=phone_number_id)
unix_socket = '/cloudsql/{}'.format(db_connection_name)
try:
    print('Trying with local socket')
    cnx = pymysql.connect(host=db_host, user=db_user, password=db_password, database=db_name,
                          charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
    print('Connected successfully to the database using host.')

except pymysql.MySQLError as e:
    print('Trying with self load balancer because of:', str(e))
    unix_socket = 'your_unix_socket_path'

    cnx = pymysql.connect(user=db_user, password=db_password, unix_socket=unix_socket, db=db_name)
    print('Connected successfully to the database using socket.')
verify_token = os.environ.get('VERIFY_TOKEN')


@app.route('/', methods=["GET", "POST"])
def db_setup():
    if request.method == 'GET':
        print('Username : ' + db_user)
        cnx = connect()
        with cnx.cursor() as cursor:
            sql = 'select @@version'
            cursor.execute(sql)
            result = cursor.fetchone()

    return f"Hello World! DB Connection successful. Mysql version : {result}"


@app.route('/hook', methods=["GET", "POST"])
def hook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == verify_token:
            print("Verified Webhook")
            response = make_response(request.args.get("hub.challenge"), 200)
            response.mimetype = "text/plain"
            return response
        return "Hello World"

def connect():
    try:
        print('Trying with local socket')
        cnx = pymysql.connect(host=db_host, user=db_user, password=db_password, database=db_name,
                              charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        print('Connected successfully to the database using host.')
        return cnx
    except pymysql.MySQLError as e:
        print('Trying with self load balancer because of:', str(e))
        unix_socket = 'your_unix_socket_path'

        cnx = pymysql.connect(user=db_user, password=db_password, unix_socket=unix_socket, db=db_name)
        print('Connected successfully to the database using socket.')
        return cnx


if __name__ == '__main__':
    app.run()
