import datetime
import requests
import pytz
import os
from heyoo import WhatsApp
from dotenv import load_dotenv
from flask import Flask, request, make_response, jsonify
from datetime import datetime as dt
from flask_cors import CORS, cross_origin
from flask_mail import Mail, Message
import pymysql
from pymysql import OperationalError
import re
from werkzeug.utils import secure_filename, escape
app = Flask(__name__)
load_dotenv()
ist_tz = pytz.timezone('Asia/Kolkata')
db_user = os.environ.get('CLOUD_SQL_USERNAME')
db_password = os.environ.get('CLOUD_SQL_PASSWORD')
db_name = os.environ.get('CLOUD_SQL_DATABASE_NAME')
db_connection_name = os.environ.get('CLOUD_SQL_CONNECTION_NAME')
db_host = os.environ.get('DB_HOST')
token = os.environ.get('TOKEN')
print(db_connection_name)
phone_number_id = os.environ.get('PHONE_NUMBER_ID')
messenger = WhatsApp(token=token, phone_number_id=phone_number_id)
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
    cnx = connect()
    data = request.get_json()
    print("Received webhook data: ", data)
    print('In here Part 2')
    changed_field = messenger.changed_field(data)
    if changed_field == "messages":
        print('In here Part 1')
        new_message = messenger.get_mobile(data)
        if new_message:
            print('In here Part 2')
            mobile = messenger.get_mobile(data)
            if check_blacklist(cnx, mobile):
                return 'OK', 200
            print('In here Part 3')
            name = messenger.get_name(data)
            message_type = messenger.get_message_type(data)
            cust = Customer(name, mobile)
            print("In here part 4")
            print(f"New Message; sender:{mobile} name:{name} type:{message_type}")
            if message_type == "text":
                message = messenger.get_message(data)
                print("Message: %s", message)
                if message is not None:
                    message = message.lower()
                    if message == 'hi':
                        if cust.check_cust_exist(cnx):
                            resp_id = '0A'
                            db_message_logger(cnx, message, resp_id, mobile)
                            messenger.send_message(
                                f"Hi {cust.cust_name}!!! Welcome back to Plumberwala.\n"
                                f"Please Choose from the below option which best matches your need.",
                                mobile)
                            print('Before Sending Custom Interactive Message')
                            messenger.send_message('Test Message', mobile)
                            send_custom_interactive_message(messenger, mobile, '0')
                            return 'OK', 200
                        else:

                            resp_id = '0B'
                            db_message_logger(cnx, message, resp_id, mobile)
                            messenger.send_message(
                                f"Hi {cust.cust_name}!!! Welcome to Plumbing wala. "
                                f"Please choose from the below options to continue", mobile)
                            print('Before Sending Custom Interactive Message')
                            send_custom_interactive_message(messenger, mobile, '0')
                            print('After Sending Custom Interactive Message')
                            return 'OK', 200
                    else:
                        res = get_prev_resp_id(cnx, mobile)
                        if res is not None:
                            messenger.send_message("Hello World", mobile)
                        else:
                            messenger.send_message(
                                f"Hi {cust.cust_name},This is an automated whatsapp chatbot, please type Hi/HI/hi/hI to"
                                f" start a conversation!", mobile)
                            return 'ok', 200
                        resp_id = '0C'
                        db_message_logger(cnx, message, resp_id, mobile)
                        messenger.send_message("Hello World", mobile)
                    send_custom_interactive_message(messenger, mobile, '0')
                    print('In here Part 8')
                    return 'ok', 200
                print('In here Part 5')
                return 'OK', 200
            elif message_type == "interactive":
                message_response = messenger.get_interactive_response(data)
                intractive_type = message_response.get("type")
                message_id = message_response[intractive_type]["id"]
                message_text = message_response[intractive_type]["title"]
                print(f"Interactive Message; {message_id}: {message_text}")
                resp_id = message_id
                message = message_text
                db_message_logger(cnx, message_text, resp_id, mobile)
                send_custom_interactive_message(messenger, mobile, resp_id, message)
                # messenger.send_message(get_response(resp_id, message_text, cnx, cust), mobile)
            else:
                messenger.send_message(f"Oops!! Only text and interactive message supported", mobile)
        else:
            print('No New Message')
    return 'OK', 200


def connect():
    print('Trying with self load balancer')
    unix_socket = '/cloudsql/{}'.format(db_connection_name)
    cnx = pymysql.connect(user=db_user, password=db_password, unix_socket=unix_socket, db=db_name)
    print('Connected successfully to the database using host.')
    return cnx


class Customer:
    cust_name = None
    company_name = None
    phone_number = None
    cust_address = None
    cust_email = None
    cust_category = None

    def __init__(self, cust_name, mobile, address=None):
        self.cust_name = cust_name
        self.mobile = mobile
        self.address = address

    def service_cust_ins(self, cnx):
        with cnx.cursor() as cursor:
            try:
                sql = "SELECT * FROM `Customer_Details` WHERE `phone_number`= %s"
                cursor.execute(sql, self.mobile)
                result_one = cursor.fetchone()
                if result_one is None:
                    print("In here part 1")
                    sql = "INSERT INTO `Customer_Details` (`cust_name`, `phone_number`, `cust_address`,`InsertTS`) " \
                          "VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql, (self.cust_name, self.mobile, self.address, dt.now(ist_tz).
                                         strftime('%Y-%m-%d %H:%M:%S'),))
                    cnx.commit()
                    return False
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return True

    def check_cust_exist(self, cnx):
        with cnx.cursor() as cursor:
            try:
                sql = "SELECT * FROM `Customer_Details` WHERE `phone_number`= %s"
                cursor.execute(sql, self.mobile)
                result_one = cursor.fetchone()
                if result_one is None:
                    print("In here part 1")
                    sql = "INSERT INTO `Customer_Details` (`cust_name`, `phone_number`,`insertts`) VALUES (%s, %s, %s)"
                    cursor.execute(sql, (self.cust_name, self.mobile, dt.now(ist_tz).strftime('%Y-%m-%d %H:%M:%S'),))
                    cnx.commit()
                    return False
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return True

    def set_address(self, cnx, address=None):
        self.address = address
        with cnx.cursor() as cursor:
            try:
                sql = "UPDATE Customer_Details SET cust_address = %s where phone_number = %s"
                cursor.execute(sql, (self.address, self.mobile))
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
            return None

    def set_company_name(self, cnx, company_name=None):
        self.company_name = company_name
        with cnx.cursor() as cursor:
            try:
                sql = "UPDATE Customer_Details SET company_name = %s where phone_number = %s"
                cursor.execute(sql, (self.company_name, self.mobile))
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
            return None


def db_message_logger(cnx, message, resp_id, mobile):
    with cnx.cursor() as cursor:
        try:
            sql = "INSERT INTO `chat_log` (`phone_number`, `chat_desc`, `res_id`, `insertts`) values (%s, %s, %s, %s)"
            cursor.execute(sql, (mobile, message, resp_id, dt.now(ist_tz).strftime('%Y-%m-%d %H:%M:%S'),))
            cnx.commit()

        except OperationalError as err:
            print(str(err))
            return None
        except Exception as e:
            print("Exception occurred : " + str(e))
            return None
        return None


def get_prev_resp_id(cnx, mobile):
    with cnx.cursor() as cursor:
        try:
            sql = "select `res_id`,`chat_desc` from `chat_log` where `phone_number` = %s and `log_id` = " \
                  "(select max(`log_id`) from `chat_log` where `phone_number` = %s)"
            cursor.execute(sql, (mobile, mobile))
            res = cursor.fetchone()
        except OperationalError as err:
            print(str(err))
            return None
        except Exception as e:
            print("Exception occurred : " + str(e))
            return None
        return res


def check_blacklist(cnx, mobile):
    with cnx.cursor() as cursor:
        sql = "select count(*) from black_list_no where `black_phone_no` = %s"
        cursor.execute(sql, mobile)
        res = cursor.fetchone()
        if res[0] == 0:
            return False
        else:
            return True


def send_custom_interactive_message(messenger, mobile, resp_id, message=None):
    print('Beginning of SCIM')
    payload = None
    if resp_id == '0':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Plumbing Wala"
                },
                "body": {
                    "text": "Please choose from below categories: "
                },
                "action": {
                    "button": "Options",
                    "sections": [
                        {
                            "title": "Pipes",
                            "rows": [
                                {
                                    "id": "1A",
                                    "title": "PVC Pipes"
                                },
                                {
                                    "id": "1B",
                                    "title": "CPVC Pipes"
                                },
                                {
                                    "id": "1C",
                                    "title": "Other Pipes"
                                }
                            ]
                        },
                        {
                            "title": "Fittings",
                            "rows": [
                                {
                                    "id": "1D",
                                    "title": "CP Fittings"
                                },
                                {
                                    "id": "1E",
                                    "title": "Bath Fittings"
                                },
                                {
                                    "id": "1F",
                                    "title": "Fittings"
                                }
                            ]
                        },
                        {
                            "title": "Others",
                            "rows": [
                                {
                                    "id": "1G",
                                    "title": "Water Tanks"
                                },
                                {
                                    "id": "1H",
                                    "title": "Other Plumbing Acc."
                                }
                            ]
                        }
                    ]
                }
            }
        }
    elif resp_id == '1A':

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Plumbing Wala"
                },
                "body": {
                    "text": "Please choose from below Brands:"
                },
                "action": {
                    "button": "Options",
                    "sections": [
                        {
                            "title": "Brands",
                            "rows": [
                                {
                                    "id": "2A",
                                    "title": "Prince Pipes"
                                },
                                {
                                    "id": "2B",
                                    "title": "Supreme Pipes"
                                },
                                {
                                    "id": "2C",
                                    "title": "Other Economic Pipes"
                                }
                            ]
                        },
                    ]
                }
            }
        }
    elif resp_id == '2A':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Plumbing Wala"
                },
                "body": {
                    "text": "Please choose from below types:"
                },
                "action": {
                    "button": "Options",
                    "sections": [
                        {
                            "title": "Category",
                            "rows": [
                                {
                                    "id": "3A",
                                    "title": "SWR Pipes"
                                },
                                {
                                    "id": "3B",
                                    "title": "UPVC Pipes"
                                },
                                {
                                    "id": "3C",
                                    "title": "Agriculture Pipe"
                                },
                                {
                                    "id": "3D",
                                    "title": "Gutter Pipe"
                                }
                            ]
                        },
                    ]
                }
            }
        }
    elif resp_id == '4A' or resp_id == '4B' or resp_id == '4C' or resp_id == '4D':
        messenger.send_message("Please Enter the Quantity", mobile)
        cnx = connect()
        db_message_logger(cnx, message, "5A", mobile)
        return None
    print('Payload Prepared in send custom interactive message')
    requests.post(messenger.url, headers=messenger.headers, json=payload)
    print('Request sent in send custom interactive message')
    return None


def fetch_cart_no(cust):
    cnx = connect()
    with cnx.cursor() as cursor:
        try:
            sql = "SELECT *  FROM `Customer_Details` " \
                  "WHERE phone_number = %s AND order_id = (select max(order_id) from `Customer_Details` where " \
                  "phone_number = %s and order_stat = 'P')"
            cursor.execute(sql, (cust.mobile, cust.mobile))
            result = cursor.fetchone()
        except OperationalError as err:
            print(str(err))
            return None
        except Exception as e:
            print("Exception occurred : " + str(e))
            return None
        return result


class Order:

    cart_no = None
    phone_number = None
    category = None
    cust = None

    # def __init__(self, phone_number):
    #     self.phone_number = phone_number
    #     cnx = connect()
    #     with cnx.cursor() as cursor:
    #         sql = f"select "

    def __init__(self, phone_number, category, cust):
        self.phone_number = phone_number
        self.category = category
        self.cust = cust

    def create_order_line(self):
        cnx = connect()
        with cnx.cursor() as cursor:
            try:
                sql = f"insert into `order_log` (`cart_no`,`phone_no`, `order_cat`, `order_stat`) " \
                      f"values ({},{self.phone_number}, {self.category}, 'O')"
                cursor.execute(sql)
                cnx.commit()
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return None

    def update_order_line_details(self, col_name, col_val):
        cnx = connect()
        with cnx.cursor() as cursor:
            try:
                sql = f"update order_log set {col_name} = {col_val} where phone_number = {self.phone_number}"
                cursor.execute(sql)
                cnx.commit()
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return None

    def confirm_order(self):
        cnx = connect()
        with cnx.cursor() as cursor:
            try:
                sql = f"update `order_log` set order_stat = 'P' where order_no = {self.order_no} and "
                cursor.execute(sql)
                cnx.commit()
            except OperationalError as err:
                print(str(err))
                return None
            except Exception as e:
                print("Exception occurred : " + str(e))
                return None
        return None


if __name__ == '__main__':
    app.run()
