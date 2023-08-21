import datetime
import requests
import pytz
import os
import logging

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
    print("Received webhook data: %s", data)
    changed_field = messenger.changed_field(data)
    if changed_field == "messages":
        new_message = messenger.get_mobile(data)
        if new_message:
            mobile = messenger.get_mobile(data)
            if check_blacklist(cnx, mobile):
                return 'OK', 200
            name = messenger.get_name(data)
            time = messenger.get_message_timestamp(data)
            message_type = messenger.get_message_type(data)
            cust = Customer(name, mobile)
            print("In here part 4")
            print(f"New Message; sender:{mobile} name:{name} type:{message_type}")
            if message_type == "text":
                message = messenger.get_message(data)
                name = messenger.get_name(data)
                print("Message: %s", message)
                if message is not None:
                    message = message.lower()
                    if message == 'hi':
                        if cust.check_cust_exist(cnx):
                            resp_id = '0A'
                            db_message_logger(cnx, message, resp_id, mobile)
                            messenger.send_message(
                                f"Hi {cust.cust_name}!!! Welcome back to Cure and Care Physiotherapy. Hooghly Branch.\n Please visit our website http://www.cacprc.com",
                                mobile)
                            send_custom_interactive_message(messenger, mobile, '0')
                        else:
                            resp_id = '0B'
                            db_message_logger(cnx, message, resp_id, mobile)
                            messenger.send_message(
                                f"Hi {cust.cust_name}!!! Welcome to Cure and Care Physiotherapy. Hooghly Branch.\n Please visit our website http://www.cacprc.com"
                                f"Please Enter your address to continue.", mobile)

                    else:
                        res = get_prev_resp_id(cnx, mobile)
                        if res is not None:
                            messenger.send_message("Hello World", mobile)
                        else:
                            res = {0: 0}
                            messenger.send_message(
                                f"Hello World",
                                mobile)
                            return 'ok', 200
                        resp_id = '0C'
                        db_message_logger(cnx, message, resp_id, mobile)
                        messenger.send_message("Hello World", mobile)
                    send_custom_interactive_message(messenger, mobile, 0)
                    return 'ok', 200


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
                    sql = "INSERT INTO `Customer_Details` (`cust_name`, `phone_number`, `cust_address`,`InsertTS`) VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql, (self.cust_name, self.mobile, self.address, dt.now(ist_tz).strftime('%Y-%m-%d %H:%M:%S'),))
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


def send_custom_interactive_message(messenger, mobile, resp_id):
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
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose from the below options."
                },
                "action": {
                    "button": "Options",
                    "sections": [
                        {
                            "title": "Treatment Purpose",
                            "rows": [
                                {
                                    "id": "1A",
                                    "title": "Orthopedic",
                                    "description": "Service from 7 am to 7 pm, 7 days a week."
                                },
                                {
                                    "id": "1B",
                                    "title": "Neuro",
                                    "description": "Service from 7 am to 7 pm, 7 days a week."
                                },
                                {
                                    "id": "1C",
                                    "title": "Hydro / aqua",
                                    "description": "Service from 7 am to 7 pm, 7 days a week."
                                },
                                {
                                    "id": "1D",
                                    "title": "Fitness and swimming",
                                    "description": "Service from 7 am to 7 pm, 7 days a week."
                                },
                                {
                                    "id": "1E",
                                    "title": "Paediatric Physiotherapy",
                                    "description": "Service from 7 am to 7 pm, 7 days a week."
                                }
                            ]
                        },
                        {
                            "title": "Academic Purpose",
                            "rows": [
                                # {
                                #     "id": "2A",
                                #     "title": "Free Course",
                                #     "description": "APT"
                                # },
                                {
                                    "id": "2B",
                                    "title": "Paid Course",
                                    "description": "DPT Or BPT"
                                }
                            ]
                        }
                    ]
                }
            }
        }
    elif resp_id == '1':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose from the below options."
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "3A",
                                "title": "Home Visit"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "3B",
                                "title": "Clinic Visit"
                            }
                        }
                    ]
                }
            }
        }
    elif resp_id == '2':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose from the below options."
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "4A",
                                "title": "With Surgery"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "4B",
                                "title": "Without Surgery"
                            }
                        }
                    ]
                }
            }
        }
    elif resp_id == '3':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose from the below dates."
                },
                "action": {
                    "button": "Choose Date",
                    "sections": [
                        {
                            "title": "Dates",
                            "rows": [
                                {
                                    "id": "D1",
                                    "title": (dt.now(ist_tz) + datetime.timedelta(days=1)).strftime(
                                        '%Y-%m-%d')

                                },
                                {
                                    "id": "D2",
                                    "title": (dt.now(ist_tz) + datetime.timedelta(days=2)).strftime(
                                        '%Y-%m-%d')
                                },
                                {
                                    "id": "D3",
                                    "title": (dt.now(ist_tz) + datetime.timedelta(days=3)).strftime(
                                        '%Y-%m-%d')
                                },
                                {
                                    "id": "D4",
                                    "title": (dt.now(ist_tz) + datetime.timedelta(days=4)).strftime(
                                        '%Y-%m-%d')
                                },
                                {
                                    "id": "D5",
                                    "title": (dt.now(ist_tz) + datetime.timedelta(days=5)).strftime(
                                        '%Y-%m-%d')
                                },
                                {
                                    "id": "D6",
                                    "title": (dt.now(ist_tz) + datetime.timedelta(days=6)).strftime(
                                        '%Y-%m-%d')
                                },
                                {
                                    "id": "D7",
                                    "title": (dt.now(ist_tz) + datetime.timedelta(days=7)).strftime(
                                        '%Y-%m-%d')
                                }
                            ]
                        }
                    ]
                }
            }
        }
    elif resp_id == '4':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose from the below time slots."
                },
                "action": {
                    "button": "Choose Time",
                    "sections": [
                        {
                            "title": "Time Slots",
                            "rows": [
                                {
                                    "id": "T1",
                                    "title": "7 a.m. - 9 a.m."

                                },
                                {
                                    "id": "T2",
                                    "title": "9 a.m. - 11 a.m."
                                },
                                {
                                    "id": "T3",
                                    "title": "11 a.m. - 1 p.m."
                                },
                                {
                                    "id": "T4",
                                    "title": "1 p.m. - 3 p.m."
                                },
                                {
                                    "id": "T5",
                                    "title": "3 p.m. - 5 p.m."
                                },
                                {
                                    "id": "T6",
                                    "title": "5 p.m. - 7 p.m."
                                }
                            ]
                        }
                    ]
                }
            }
        }

    elif resp_id == '5':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Do you want to confirm your booking ?"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "5A",
                                "title": "YES"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "5B",
                                "title": "NO"
                            }
                        }
                    ]
                }
            }
        }
    elif resp_id == '6':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose from the below options."
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "6A",
                                "title": "Morning Slot"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "6B",
                                "title": "Evening Slot"
                            }
                        }
                    ]
                }
            }
        }
    elif resp_id == '7':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Paid Course Details:"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "7A",
                                "title": "DPT"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "7B",
                                "title": "BPT"
                            }
                        }
                    ]
                }
            }
        }
    elif resp_id == '8':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose from the below time slots."
                },
                "action": {
                    "button": "Choose Time",
                    "sections": [
                        {
                            "title": "Time Slots",
                            "rows": [
                                {
                                    "id": "HT01",
                                    "title": "7 a.m. - 8 a.m."
                                },
                                {
                                    "id": "HT02",
                                    "title": "8 a.m. - 9 a.m."
                                },
                                {
                                    "id": "HT03",
                                    "title": "9 a.m. - 10 a.m."
                                },
                                {
                                    "id": "HT04",
                                    "title": "10 a.m. - 11 a.m."
                                },
                                {
                                    "id": "HT05",
                                    "title": "11 a.m. - 12 p.m."
                                },
                                {
                                    "id": "HT06",
                                    "title": "12 p.m. - 1 p.m."
                                }
                            ]
                        }
                    ]
                }
            }
        }
    elif resp_id == '9':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose from the below time slots."
                },
                "action": {
                    "button": "Choose Time",
                    "sections": [
                        {
                            "title": "Time Slots",
                            "rows": [
                                {
                                    "id": "HT07",
                                    "title": "1 p.m. - 2 p.m."
                                },
                                {
                                    "id": "HT08",
                                    "title": "2 p.m. - 3 p.m."
                                },
                                {
                                    "id": "HT09",
                                    "title": "3 p.m. - 4 p.m."
                                },
                                {
                                    "id": "HT10",
                                    "title": "4 p.m. - 5 p.m."
                                },
                                {
                                    "id": "HT11",
                                    "title": "5 p.m. - 6 p.m."
                                },
                                {
                                    "id": "HT12",
                                    "title": "6 p.m. - 7 p.m."
                                },
                                {
                                    "id": "HT13",
                                    "title": "7 p.m. - 8 p.m."
                                }
                            ]
                        }
                    ]
                }
            }
        }
    elif resp_id == '10':
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": mobile,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "Cure and Care Physiotherapy"
                },
                "body": {
                    "text": "Please choose your preferred mode:"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "9A",
                                "title": "Online"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "9B",
                                "title": "Offline"
                            }
                        }
                    ]
                }
            }
        }

    requests.post(messenger.url, headers=messenger.headers, json=payload)
    return None


if __name__ == '__main__':
    app.run()
